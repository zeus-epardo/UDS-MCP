"""ECU simulator logic: UDS requests in, responses out, no bus involved.

Behaviour comes from the ``[sim]`` section of an ECU config, so the same TOML file
describes both what the client expects and what the simulator answers.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable

from uds_mcp.core.config import EcuConfig

DEFAULT_SESSION = 0x01
SUPPRESS_POSITIVE_RESPONSE = 0x80

# Negative response codes used by the simulator (ISO 14229-1 Annex A).
SERVICE_NOT_SUPPORTED = 0x11
SUBFUNCTION_NOT_SUPPORTED = 0x12
INCORRECT_MESSAGE_LENGTH = 0x13
REQUEST_SEQUENCE_ERROR = 0x24
REQUEST_OUT_OF_RANGE = 0x31
SECURITY_ACCESS_DENIED = 0x33
INVALID_KEY = 0x35
EXCEEDED_NUMBER_OF_ATTEMPTS = 0x36
RESPONSE_PENDING = 0x78
SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION = 0x7F

Reply = tuple[float, bytes]
"""A response and the delay in seconds to wait before sending it."""


class NegativeResponseError(Exception):
    def __init__(self, code: int) -> None:
        self.code = code


class SimulatedEcu:
    def __init__(self, config: EcuConfig, clock: Callable[[], float] = time.monotonic) -> None:
        self.config = config
        self.sim = config.sim
        self.clock = clock
        self.dids = {
            did: self._decode_value(did, spec.value) for did, spec in self.sim.dids.items()
        }
        self.dtcs = {dtc.code: dtc.status for dtc in self.sim.dtcs}
        self._handlers: dict[int, Callable[[bytes], list[Reply]]] = {
            0x10: self._session_control,
            0x11: self._ecu_reset,
            0x14: self._clear_dtcs,
            0x19: self._read_dtcs,
            0x22: self._read_dids,
            0x27: self._security_access,
            0x2E: self._write_did,
            0x31: self._routine_control,
            0x3E: self._tester_present,
        }
        self._reset_state()

    # -- entry point -----------------------------------------------------------------------

    def handle(self, request: bytes) -> list[Reply]:
        """Answer one request; returns zero (suppressed), one or several (0x78) replies."""
        if not request:
            return []
        self.check_s3()
        self._last_activity = self.clock()
        sid = request[0]
        handler = self._handlers.get(sid)
        try:
            if handler is None:
                raise NegativeResponseError(SERVICE_NOT_SUPPORTED)
            return handler(request)
        except NegativeResponseError as e:
            return [(0.0, bytes([0x7F, sid, e.code]))]

    def check_s3(self) -> None:
        """Fall back to the default session when no request arrived within S3."""
        if self.session != DEFAULT_SESSION:
            if self.clock() - self._last_activity > self.sim.s3_ms / 1000:
                self._reset_state()

    # -- services --------------------------------------------------------------------------

    def _session_control(self, req: bytes) -> list[Reply]:
        self._require_length(req, 2)
        session = req[1] & ~SUPPRESS_POSITIVE_RESPONSE & 0xFF
        if session not in self.sim.sessions:
            raise NegativeResponseError(SUBFUNCTION_NOT_SUPPORTED)
        self._reset_state(session)
        timing = self.config.timing
        payload = (
            bytes([0x50, session])
            + timing.p2_ms.to_bytes(2, "big")
            + (timing.p2_star_ms // 10).to_bytes(2, "big")
        )
        return self._positive(req, payload)

    def _ecu_reset(self, req: bytes) -> list[Reply]:
        self._require_length(req, 2)
        reset_type = req[1] & ~SUPPRESS_POSITIVE_RESPONSE & 0xFF
        if reset_type not in self.sim.reset_types:
            raise NegativeResponseError(SUBFUNCTION_NOT_SUPPORTED)
        self._reset_state()
        return self._positive(req, bytes([0x51, reset_type]))

    def _clear_dtcs(self, req: bytes) -> list[Reply]:
        self._require_length(req, 4)
        group = int.from_bytes(req[1:4], "big")
        if group == 0xFFFFFF:
            self.dtcs.clear()
        elif group in self.dtcs:
            del self.dtcs[group]
        else:
            raise NegativeResponseError(REQUEST_OUT_OF_RANGE)
        return [(0.0, bytes([0x54]))]

    def _read_dtcs(self, req: bytes) -> list[Reply]:
        self._require_length(req, 3)
        subfunction, mask = req[1], req[2]
        matching = [(code, status) for code, status in self.dtcs.items() if status & mask]
        if subfunction == 0x01:
            # Format identifier 0x01 = ISO 14229-1 DTC format.
            return [(0.0, bytes([0x59, 0x01, 0xFF, 0x01]) + len(matching).to_bytes(2, "big"))]
        if subfunction == 0x02:
            records = b"".join(
                code.to_bytes(3, "big") + bytes([status]) for code, status in matching
            )
            return [(0.0, bytes([0x59, 0x02, 0xFF]) + records)]
        raise NegativeResponseError(SUBFUNCTION_NOT_SUPPORTED)

    def _read_dids(self, req: bytes) -> list[Reply]:
        if len(req) < 3 or len(req) % 2 == 0:
            raise NegativeResponseError(INCORRECT_MESSAGE_LENGTH)
        out = bytearray([0x62])
        for i in range(1, len(req), 2):
            did = int.from_bytes(req[i : i + 2], "big")
            spec = self.sim.dids.get(did)
            if spec is None or not self._session_allowed(spec.read_sessions):
                raise NegativeResponseError(REQUEST_OUT_OF_RANGE)
            out += req[i : i + 2] + self.dids[did]
        return [(0.0, bytes(out))]

    def _write_did(self, req: bytes) -> list[Reply]:
        if len(req) < 4:
            raise NegativeResponseError(INCORRECT_MESSAGE_LENGTH)
        did = int.from_bytes(req[1:3], "big")
        spec = self.sim.dids.get(did)
        if spec is None or not spec.writable or not self._session_allowed(spec.write_sessions):
            raise NegativeResponseError(REQUEST_OUT_OF_RANGE)
        expected = self.config.dids[did].length if did in self.config.dids else None
        if expected is not None and len(req) - 3 != expected:
            raise NegativeResponseError(INCORRECT_MESSAGE_LENGTH)
        self._require_unlocked(spec.write_security_level)
        self.dids[did] = bytes(req[3:])
        return [(0.0, bytes([0x6E]) + req[1:3])]

    def _security_access(self, req: bytes) -> list[Reply]:
        self._require_length(req, 2, exact=False)
        if self.session == DEFAULT_SESSION:
            raise NegativeResponseError(SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION)
        subfunction = req[1] & ~SUPPRESS_POSITIVE_RESPONSE & 0xFF
        level = subfunction if subfunction % 2 else subfunction - 1
        spec = self.config.security.get(level)
        if spec is None:
            raise NegativeResponseError(SUBFUNCTION_NOT_SUPPORTED)

        if subfunction % 2:  # requestSeed
            if level in self.unlocked:
                seed = bytes(spec.seed_len or 4)
            else:
                seed = self._new_seed(spec.seed_len or 4)
                self._pending_seed = (level, seed)
            return [(0.0, bytes([0x67, subfunction]) + seed)]

        # sendKey
        if self._pending_seed is None or self._pending_seed[0] != level:
            raise NegativeResponseError(REQUEST_SEQUENCE_ERROR)
        if self._failed_attempts >= self.sim.max_key_attempts:
            raise NegativeResponseError(EXCEEDED_NUMBER_OF_ATTEMPTS)
        expected = spec.load_algorithm()(level, self._pending_seed[1])
        if req[2:] != expected:
            self._failed_attempts += 1
            if self._failed_attempts >= self.sim.max_key_attempts:
                raise NegativeResponseError(EXCEEDED_NUMBER_OF_ATTEMPTS)
            raise NegativeResponseError(INVALID_KEY)
        self._pending_seed = None
        self._failed_attempts = 0
        self.unlocked.add(level)
        return [(0.0, bytes([0x67, subfunction]))]

    def _routine_control(self, req: bytes) -> list[Reply]:
        self._require_length(req, 4, exact=False)
        control_type = req[1] & ~SUPPRESS_POSITIVE_RESPONSE & 0xFF
        routine_id = int.from_bytes(req[2:4], "big")
        if control_type not in (1, 2, 3):
            raise NegativeResponseError(SUBFUNCTION_NOT_SUPPORTED)
        spec = self.sim.routines.get(routine_id)
        if spec is None or not self._session_allowed(spec.sessions):
            raise NegativeResponseError(REQUEST_OUT_OF_RANGE)
        self._require_unlocked(spec.security_level)
        if control_type in (2, 3) and routine_id not in self._started_routines:
            raise NegativeResponseError(REQUEST_SEQUENCE_ERROR)

        if control_type == 1:
            self._started_routines.add(routine_id)
        elif control_type == 2:
            self._started_routines.discard(routine_id)
        payload = bytes([0x71, control_type]) + req[2:4] + bytes.fromhex(spec.result)

        duration = spec.duration_ms / 1000
        if control_type == 1 and duration > self.config.timing.p2_ms / 1000:
            return [(0.0, bytes([0x7F, 0x31, RESPONSE_PENDING])), (duration, payload)]
        return [(duration, payload)]

    def _tester_present(self, req: bytes) -> list[Reply]:
        self._require_length(req, 2)
        if req[1] & ~SUPPRESS_POSITIVE_RESPONSE:
            raise NegativeResponseError(SUBFUNCTION_NOT_SUPPORTED)
        return self._positive(req, bytes([0x7E, 0x00]))

    # -- helpers ---------------------------------------------------------------------------

    def _reset_state(self, session: int = DEFAULT_SESSION) -> None:
        self.session = session
        self.unlocked: set[int] = set()
        self._pending_seed: tuple[int, bytes] | None = None
        self._failed_attempts = 0
        self._started_routines: set[int] = set()
        self._last_activity = self.clock()

    def _session_allowed(self, sessions: list[int] | None) -> bool:
        return sessions is None or self.session in sessions

    def _require_unlocked(self, level: int | None) -> None:
        if level is not None and level not in self.unlocked:
            raise NegativeResponseError(SECURITY_ACCESS_DENIED)

    @staticmethod
    def _require_length(req: bytes, length: int, exact: bool = True) -> None:
        if len(req) < length or (exact and len(req) != length):
            raise NegativeResponseError(INCORRECT_MESSAGE_LENGTH)

    @staticmethod
    def _positive(req: bytes, payload: bytes) -> list[Reply]:
        return [] if req[1] & SUPPRESS_POSITIVE_RESPONSE else [(0.0, payload)]

    def _new_seed(self, length: int) -> bytes:
        if self.sim.seed is not None:
            return bytes.fromhex(self.sim.seed)
        while True:
            seed = os.urandom(length)
            if any(seed):  # an all-zero seed would mean "already unlocked"
                return seed

    def _decode_value(self, did: int, value: str) -> bytes:
        spec = self.config.dids.get(did)
        data = value.encode("ascii") if spec and spec.encoding == "ascii" else bytes.fromhex(value)
        if spec and spec.length is not None and len(data) != spec.length:
            raise ValueError(
                f"[sim] DID 0x{did:04X} value has {len(data)} bytes, expected {spec.length}"
            )
        return data
