"""UDS client: ISO 14229 services over ISO-TP, returning structured results.

ISO-TP framing and UDS encoding come from ``can-isotp`` and ``udsoncan``; this module adds
configuration, raw-bytes DID handling and uniform :class:`UdsResult` outcomes so callers
(MCP tools, test plans) never have to deal with udsoncan exceptions.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import can
import isotp
import udsoncan
from udsoncan import DidCodec
from udsoncan.client import Client
from udsoncan.connections import PythonIsoTpConnection
from udsoncan.exceptions import (
    InvalidResponseException,
    NegativeResponseException,
    TimeoutException,
    UnexpectedResponseException,
)

from uds_mcp.core.config import EcuConfig, KeyAlgorithm
from uds_mcp.core.results import UdsResult, nrc_name


class _RawCodec(DidCodec):
    """Pass DID payloads through as bytes; ``length=None`` reads the rest of the response."""

    def __init__(self, length: int | None) -> None:
        self.length = length

    def encode(self, value: bytes) -> bytes:
        return bytes(value)

    def decode(self, payload: bytes) -> bytes:
        return bytes(payload)

    def __len__(self) -> int:
        if self.length is None:
            raise DidCodec.ReadAllRemainingData
        return self.length


def _hex(payload: bytes | None) -> str | None:
    return None if payload is None else payload.hex(" ").upper()


class UdsClient:
    """Physical-addressing UDS client for one ECU on an already opened CAN bus.

    The bus is owned by the caller; :meth:`close` only stops the ISO-TP and UDS layers.
    """

    def __init__(self, bus: can.BusABC, config: EcuConfig | None = None) -> None:
        self.config = config or EcuConfig()
        ecu = self.config.ecu
        if ecu.addressing != "normal":
            raise ValueError(f"Addressing mode {ecu.addressing!r} is not supported yet")

        mode = (
            isotp.AddressingMode.Normal_29bits
            if max(ecu.request_id, ecu.response_id) > 0x7FF
            else isotp.AddressingMode.Normal_11bits
        )
        address = isotp.Address(mode, txid=ecu.request_id, rxid=ecu.response_id)
        params = {
            "tx_padding": 0xCC,
            "can_fd": ecu.can_fd,
            "tx_data_length": 64 if ecu.can_fd else 8,
            "bitrate_switch": ecu.can_fd,
        }
        self._notifier = can.Notifier(bus, [])
        self._stack = isotp.NotifierBasedCanStack(
            bus, self._notifier, address=address, params=params
        )
        self._conn = PythonIsoTpConnection(self._stack)

        timing = self.config.timing
        client_config = dict(udsoncan.configs.default_client_config)
        client_config.update(
            p2_timeout=timing.p2_ms / 1000,
            p2_star_timeout=timing.p2_star_ms / 1000,
            request_timeout=timing.request_timeout_ms / 1000,
        )
        self._client = Client(self._conn, config=client_config)
        self._open = False
        # One request at a time: tool calls and the keep-alive thread share the connection.
        self._lock = threading.RLock()
        self.session = 1
        self._keep_alive_stop = threading.Event()
        self._keep_alive_thread: threading.Thread | None = None

    # -- lifecycle -------------------------------------------------------------------------

    def open(self) -> UdsClient:
        if not self._open:
            self._client.open()
            self._open = True
        return self

    def close(self) -> None:
        self.stop_keep_alive()
        if self._open:
            self._client.close()
            self._open = False
        self._notifier.stop()

    def __enter__(self) -> UdsClient:
        return self.open()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def start_keep_alive(self, interval_s: float | None = None) -> None:
        """Send TesterPresent (0x3E 80, no response) periodically while outside the default
        session, so a slow caller (a person, an LLM) does not lose the session to S3."""
        if self._keep_alive_thread is not None:
            return
        if interval_s is None:
            interval_s = self.config.timing.tester_present_interval_ms / 1000
        self._keep_alive_stop.clear()

        def loop() -> None:
            while not self._keep_alive_stop.wait(interval_s):
                if self.session != 1:
                    with self._lock:
                        self._conn.send(bytes([0x3E, 0x80]))

        self._keep_alive_thread = threading.Thread(target=loop, name="uds-keep-alive", daemon=True)
        self._keep_alive_thread.start()

    def stop_keep_alive(self) -> None:
        if self._keep_alive_thread is not None:
            self._keep_alive_stop.set()
            self._keep_alive_thread.join(timeout=2)
            self._keep_alive_thread = None

    # -- services --------------------------------------------------------------------------

    def diagnostic_session_control(self, session: int) -> UdsResult:
        """0x10 — switch to ``session`` (1 default, 2 programming, 3 extended, ...)."""

        def decode(resp: Any) -> dict[str, Any]:
            data: dict[str, Any] = {"session": resp.service_data.session_echo}
            timing = resp.service_data.p2_server_max, resp.service_data.p2_star_server_max
            if timing[0] is not None:
                data["p2_server_max_s"], data["p2_star_server_max_s"] = timing
            return data

        result = self._run(
            "DiagnosticSessionControl", lambda: self._client.change_session(session), decode
        )
        if result.ok:
            self.session = session
        return result

    def ecu_reset(self, reset_type: int = 1) -> UdsResult:
        """0x11 — reset the ECU (1 hard, 2 key off/on, 3 soft, ...)."""

        def decode(resp: Any) -> dict[str, Any]:
            data: dict[str, Any] = {"reset_type": resp.service_data.reset_type_echo}
            if resp.service_data.powerdown_time is not None:
                data["powerdown_time_s"] = resp.service_data.powerdown_time
            return data

        result = self._run("ECUReset", lambda: self._client.ecu_reset(reset_type), decode)
        if result.ok:
            self.session = 1
        return result

    def read_data_by_identifier(self, dids: int | list[int]) -> UdsResult:
        """0x22 — read one or more DIDs.

        DIDs listed in the config are decoded with their configured length and encoding.
        An unlisted DID is returned as raw bytes, which only works when it is read alone.
        """
        dids = [dids] if isinstance(dids, int) else list(dids)
        unknown = [d for d in dids if self._did_length(d) is None]
        if unknown and len(dids) > 1:
            return UdsResult(
                service="ReadDataByIdentifier",
                ok=False,
                error="DIDs without a configured length must be read one at a time: "
                + ", ".join(f"0x{d:04X}" for d in unknown),
            )
        self._set_codecs(dids)

        def decode(resp: Any) -> dict[str, Any]:
            return {
                f"0x{did:04X}": self._describe_did(did, value)
                for did, value in resp.service_data.values.items()
            }

        return self._run(
            "ReadDataByIdentifier", lambda: self._client.read_data_by_identifier(dids), decode
        )

    def write_data_by_identifier(self, did: int, value: bytes) -> UdsResult:
        """0x2E — write raw ``value`` bytes to ``did``."""
        length = self._did_length(did)
        if length is not None and len(value) != length:
            return UdsResult(
                service="WriteDataByIdentifier",
                ok=False,
                error=f"DID 0x{did:04X} expects {length} bytes, got {len(value)}",
            )
        self._set_codecs([did])
        return self._run(
            "WriteDataByIdentifier",
            lambda: self._client.write_data_by_identifier(did, value),
            lambda resp: {"did": f"0x{resp.service_data.did_echo:04X}"},
        )

    def security_access(self, level: int, key_algorithm: KeyAlgorithm | None = None) -> UdsResult:
        """0x27 — request a seed for odd ``level`` and answer it with the computed key.

        The key algorithm comes from ``key_algorithm`` or from ``[security]`` in the config.
        An all-zero seed means the level is already unlocked and no key is sent.
        """
        if key_algorithm is None:
            spec = self.config.security.get(level)
            if spec is None:
                return UdsResult(
                    service="SecurityAccess",
                    ok=False,
                    error=f"No key algorithm configured for security level {level}",
                )
            key_algorithm = spec.load_algorithm()

        seed_result = self._run(
            "SecurityAccess",
            lambda: self._client.request_seed(level),
            lambda resp: {"seed": _hex(resp.service_data.seed)},
        )
        if not seed_result.ok:
            return seed_result
        seed = bytes.fromhex(seed_result.data["seed"])
        if not any(seed):
            return seed_result.model_copy(
                update={"data": {**seed_result.data, "already_unlocked": True}}
            )

        key = key_algorithm(level, seed)
        result = self._run(
            "SecurityAccess",
            lambda: self._client.send_key(level + 1, key),
            lambda resp: {"level": level, "unlocked": True},
        )
        result.data = {"seed": seed_result.data["seed"], **result.data}
        return result

    def routine_control(
        self, routine_id: int, control_type: int = 1, data: bytes | None = None
    ) -> UdsResult:
        """0x31 — control a routine (1 start, 2 stop, 3 request results)."""
        return self._run(
            "RoutineControl",
            lambda: self._client.routine_control(routine_id, control_type, data),
            lambda resp: {
                "routine_id": f"0x{resp.service_data.routine_id_echo:04X}",
                "control_type": resp.service_data.control_type_echo,
                "status_record": _hex(resp.service_data.routine_status_record),
            },
        )

    def read_dtc_information(self, status_mask: int = 0xFF) -> UdsResult:
        """0x19 02 — report DTCs matching ``status_mask``."""
        return self._run(
            "ReadDTCInformation",
            lambda: self._client.get_dtc_by_status_mask(status_mask),
            lambda resp: {
                "dtcs": [
                    {"dtc": f"0x{dtc.id:06X}", "status": f"0x{dtc.status.get_byte_as_int():02X}"}
                    for dtc in resp.service_data.dtcs
                ]
            },
        )

    def clear_diagnostic_information(self, group: int = 0xFFFFFF) -> UdsResult:
        """0x14 — clear DTCs of ``group`` (0xFFFFFF = all groups)."""
        return self._run(
            "ClearDiagnosticInformation",
            lambda: self._client.clear_dtc(group),
            lambda resp: {"group": f"0x{group:06X}"},
        )

    def tester_present(self) -> UdsResult:
        """0x3E 00 — keep the current non-default session alive."""
        return self._run("TesterPresent", self._client.tester_present, lambda resp: {})

    def send_raw(self, payload: bytes) -> UdsResult:
        """Send an arbitrary UDS request and return the raw positive or negative response.

        Goes straight to the ISO-TP connection so services udsoncan does not know (including
        manufacturer-specific SIDs) work too. NRC 0x78 (response pending) extends the wait to P2*.
        """
        if not payload:
            return UdsResult(service="Raw", ok=False, error="Empty request")
        with self._lock:
            result = self._send_raw(payload)
        # Keep track of session changes made through raw requests too.
        if result.ok and result.response:
            response = bytes.fromhex(result.response)
            if response[0] == 0x50 and len(response) > 1:
                self.session = response[1]
            elif response[0] == 0x51:
                self.session = 1
        return result

    def _send_raw(self, payload: bytes) -> UdsResult:
        timing = self.config.timing
        self._conn.empty_rxqueue()
        self._conn.send(payload)
        timeout = timing.p2_ms / 1000
        while True:
            try:
                response = self._conn.wait_frame(timeout=timeout, exception=True)
            except udsoncan.exceptions.TimeoutException as e:
                return UdsResult(
                    service="Raw", ok=False, request=_hex(payload), error=f"TimeoutException: {e}"
                )
            if len(response) >= 3 and response[0] == 0x7F and response[1] == payload[0]:
                if response[2] == 0x78:
                    timeout = timing.p2_star_ms / 1000
                    continue
                return UdsResult(
                    service="Raw",
                    ok=False,
                    request=_hex(payload),
                    response=_hex(response),
                    nrc=response[2],
                    nrc_name=nrc_name(response[2]),
                )
            return UdsResult(
                service="Raw",
                ok=response[0] == (payload[0] | 0x40),
                request=_hex(payload),
                response=_hex(response),
            )

    # -- helpers ---------------------------------------------------------------------------

    def _run(
        self, service: str, call: Callable[[], Any], decode: Callable[[Any], dict]
    ) -> UdsResult:
        try:
            with self._lock:
                resp = call()
        except NegativeResponseException as e:
            return UdsResult(
                service=service,
                ok=False,
                response=_hex(e.response.get_payload()),
                nrc=e.response.code,
                nrc_name=e.response.code_name,
            )
        except (TimeoutException, InvalidResponseException, UnexpectedResponseException) as e:
            return UdsResult(service=service, ok=False, error=f"{type(e).__name__}: {e}")
        return UdsResult(
            service=service, ok=True, response=_hex(resp.get_payload()), data=decode(resp)
        )

    def _did_length(self, did: int) -> int | None:
        spec = self.config.dids.get(did)
        return spec.length if spec else None

    def _set_codecs(self, dids: list[int]) -> None:
        self._client.config["data_identifiers"] = {
            did: _RawCodec(self._did_length(did)) for did in dids
        }

    def _describe_did(self, did: int, value: bytes) -> dict[str, Any]:
        spec = self.config.dids.get(did)
        out: dict[str, Any] = {"hex": _hex(value)}
        if spec:
            out["name"] = spec.name
            if spec.encoding == "ascii":
                out["ascii"] = value.decode("ascii", errors="replace").rstrip("\x00")
        return out
