"""MCP server exposing a :class:`UdsClient` as tools.

Tools take IDs and payloads as hex strings ("F190", "0xF190", "22 F1 90") because that is
how diagnostic engineers and LLMs write them, and return :class:`UdsResult` as JSON.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from uds_mcp import __version__
from uds_mcp.core.client import UdsClient
from uds_mcp.core.results import UdsResult

SESSIONS = {"default": 0x01, "programming": 0x02, "extended": 0x03, "safety": 0x04}
RESET_TYPES = {"hard": 0x01, "key_off_on": 0x02, "soft": 0x03}
ROUTINE_CONTROLS = {"start": 0x01, "stop": 0x02, "results": 0x03}

INSTRUCTIONS = """\
UDS-MCP runs ISO 14229 (UDS) diagnostics on one ECU over CAN.

- IDs and payloads are hex strings: "F190", "0xF190" or "22 F1 90".
- Every tool returns {service, ok, request, response, nrc, nrc_name, error, data}.
  ok=false with nrc_name is a negative response from the ECU; with error it is a
  local or transport problem.
- Start with get_ecu_info to see the ECU addresses, known DIDs and security levels.
- Many DIDs, routines and security access need the extended session first. A
  TesterPresent keep-alive holds non-default sessions open between calls.
- Writing DIDs, routines and resets change the ECU: confirm with the user first.
"""


def parse_hex(value: str | int, *, name: str = "value") -> int:
    """Parse an ID given as an int or as hex text, with or without ``0x``."""
    if isinstance(value, int):
        return value
    text = value.strip().replace(" ", "").removeprefix("0x").removeprefix("0X")
    try:
        return int(text, 16)
    except ValueError:
        raise ToolError(f"{name} must be hex, e.g. 'F190', got {value!r}") from None


def parse_bytes(value: str, *, name: str = "value") -> bytes:
    text = value.strip().replace(" ", "").removeprefix("0x").removeprefix("0X")
    try:
        return bytes.fromhex(text)
    except ValueError:
        raise ToolError(f"{name} must be hex bytes, e.g. '22 F1 90', got {value!r}") from None


def _ascii(value: str) -> bytes:
    try:
        return value.encode("ascii")
    except UnicodeEncodeError:
        raise ToolError(f"value_ascii must be ASCII text, got {value!r}") from None


def _named(value: str | int, names: dict[str, int], *, name: str) -> int:
    if isinstance(value, str) and value.lower() in names:
        return names[value.lower()]
    return parse_hex(value, name=name)


def build_server(client: UdsClient, *, interface: str = "sim") -> MCPServer:
    """Create the MCP server. ``client`` must be open; requests run in a worker thread."""
    server = MCPServer(
        name="uds-mcp",
        title="UDS-MCP",
        version=__version__,
        instructions=INSTRUCTIONS,
    )

    async def run(call: Callable[[], UdsResult]) -> dict[str, Any]:
        result = await anyio.to_thread.run_sync(call)
        return result.model_dump(exclude_none=True)

    @server.tool()
    async def get_ecu_info() -> dict[str, Any]:
        """Describe the connected ECU: interface, CAN IDs, current session, known DIDs,
        routines and configured security levels."""
        config = client.config
        ecu = config.ecu
        return {
            "name": ecu.name,
            "interface": interface,
            "request_id": f"0x{ecu.request_id:X}",
            "response_id": f"0x{ecu.response_id:X}",
            "can_fd": ecu.can_fd,
            "session": client.session,
            "dids": {
                f"0x{did:04X}": spec.model_dump(exclude_none=True)
                for did, spec in config.dids.items()
            },
            "security_levels": sorted(config.security),
            "routines": {f"0x{rid:04X}": spec.name for rid, spec in config.sim.routines.items()}
            if interface == "sim"
            else {},
        }

    @server.tool()
    async def diagnostic_session_control(session: str = "extended") -> dict[str, Any]:
        """0x10 DiagnosticSessionControl. session: default, programming, extended, safety
        or a hex number."""
        number = _named(session, SESSIONS, name="session")
        return await run(lambda: client.diagnostic_session_control(number))

    @server.tool()
    async def ecu_reset(reset_type: str = "hard") -> dict[str, Any]:
        """0x11 ECUReset. reset_type: hard, key_off_on, soft or a hex number. Returns the ECU
        to the default session. Confirm with the user before resetting."""
        number = _named(reset_type, RESET_TYPES, name="reset_type")
        return await run(lambda: client.ecu_reset(number))

    @server.tool()
    async def read_data_by_identifier(dids: list[str]) -> dict[str, Any]:
        """0x22 ReadDataByIdentifier. dids: list of hex DIDs, e.g. ["F190", "F18C"]. DIDs
        not known to the ECU config must be read one at a time."""
        numbers = [parse_hex(did, name="did") for did in dids]
        return await run(lambda: client.read_data_by_identifier(numbers))

    @server.tool()
    async def write_data_by_identifier(
        did: str, value_hex: str | None = None, value_ascii: str | None = None
    ) -> dict[str, Any]:
        """0x2E WriteDataByIdentifier. Give the value as value_hex ("00 64") or value_ascii
        (text). Usually needs the extended session and security access. Confirm with the
        user before writing."""
        if (value_hex is None) == (value_ascii is None):
            raise ToolError("Give exactly one of value_hex or value_ascii")
        number = parse_hex(did, name="did")
        value = (
            parse_bytes(value_hex, name="value_hex")
            if value_hex is not None
            else _ascii(value_ascii)
        )
        return await run(lambda: client.write_data_by_identifier(number, value))

    @server.tool()
    async def security_access(level: int = 1) -> dict[str, Any]:
        """0x27 SecurityAccess: request a seed for odd level and send the key computed by
        the key algorithm configured for that level. Needs a non-default session."""
        return await run(lambda: client.security_access(level))

    @server.tool()
    async def routine_control(
        routine_id: str,
        control: Literal["start", "stop", "results"] = "start",
        data_hex: str | None = None,
    ) -> dict[str, Any]:
        """0x31 RoutineControl on a hex routine_id, e.g. "0203". Routines act on the ECU:
        confirm with the user before starting one."""
        number = parse_hex(routine_id, name="routine_id")
        data = parse_bytes(data_hex, name="data_hex") if data_hex else None
        return await run(lambda: client.routine_control(number, ROUTINE_CONTROLS[control], data))

    @server.tool()
    async def read_dtc_information(status_mask: str = "FF") -> dict[str, Any]:
        """0x19 02 ReadDTCInformation: DTCs whose status matches status_mask (hex byte)."""
        mask = parse_hex(status_mask, name="status_mask")
        return await run(lambda: client.read_dtc_information(mask))

    @server.tool()
    async def clear_diagnostic_information(group: str = "FFFFFF") -> dict[str, Any]:
        """0x14 ClearDiagnosticInformation for a DTC group (FFFFFF = all). Confirm with the
        user before clearing."""
        number = parse_hex(group, name="group")
        return await run(lambda: client.clear_diagnostic_information(number))

    @server.tool()
    async def tester_present() -> dict[str, Any]:
        """0x3E TesterPresent. Rarely needed: a keep-alive already runs in the background."""
        return await run(client.tester_present)

    @server.tool()
    async def send_raw(request_hex: str) -> dict[str, Any]:
        """Send any UDS request as hex bytes, e.g. "22 F1 90", and get the raw response.
        Use it for services without a dedicated tool."""
        payload = parse_bytes(request_hex, name="request_hex")
        return await run(lambda: client.send_raw(payload))

    return server
