"""MCP tools end to end: MCP client -> server -> UdsClient -> virtual CAN -> simulator."""

import json
import sys
import time
import uuid

import pytest
from mcp import StdioServerParameters
from mcp.client import Client
from mcp.server.mcpserver.exceptions import ToolError

from uds_mcp.cli import build_parser, open_session
from uds_mcp.server.app import parse_bytes, parse_hex
from uds_mcp.sim import DEMO_CONFIG

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def config_path(tmp_path):
    # Demo ECU with relaxed P2 for slow CI machines and a short S3 to test the keep-alive.
    text = DEMO_CONFIG.read_text()
    text = text.replace("p2_ms = 50", "p2_ms = 200")
    text = text.replace("tester_present_interval_ms = 2000", "tester_present_interval_ms = 200")
    text = text.replace("s3_ms = 5000", "s3_ms = 800")
    path = tmp_path / "ecu.toml"
    path.write_text(text)
    return path


@pytest.fixture
def session(config_path):
    args = build_parser().parse_args(
        ["--interface", "sim", "--channel", f"uds-mcp-test-{uuid.uuid4().hex}"]
        + ["--config", str(config_path)]
    )
    with open_session(args) as (client, server):
        yield client, server


@pytest.fixture
def server(session):
    return session[1]


async def call(mcp: Client, tool: str, **arguments) -> dict:
    result = await mcp.call_tool(tool, arguments)
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


async def test_lists_tools(server):
    async with Client(server) as mcp:
        names = {tool.name for tool in (await mcp.list_tools()).tools}
    assert names == {
        "get_ecu_info",
        "diagnostic_session_control",
        "ecu_reset",
        "read_data_by_identifier",
        "write_data_by_identifier",
        "security_access",
        "routine_control",
        "read_dtc_information",
        "clear_diagnostic_information",
        "tester_present",
        "send_raw",
    }


async def test_get_ecu_info(server):
    async with Client(server) as mcp:
        info = await call(mcp, "get_ecu_info")
    assert info["request_id"] == "0x7E0"
    assert info["dids"]["0xF190"]["name"] == "VIN"
    assert info["security_levels"] == [1]
    assert info["routines"] == {"0x0203": "DemoSelfTest", "0x0204": "DemoLockedRoutine"}


async def test_demo_read_and_write_vin(server):
    async with Client(server) as mcp:
        vin = await call(mcp, "read_data_by_identifier", dids=["F190"])
        assert vin["data"]["0xF190"]["ascii"] == "UDSMCP00000000001"

        assert (await call(mcp, "diagnostic_session_control", session="extended"))["ok"]
        assert (await call(mcp, "security_access", level=1))["data"]["unlocked"]
        written = await call(
            mcp, "write_data_by_identifier", did="0xF190", value_ascii="UDSMCP12345678901"
        )
        assert written["ok"]

        vin = await call(mcp, "read_data_by_identifier", dids=["F190"])
        assert vin["data"]["0xF190"]["ascii"] == "UDSMCP12345678901"


async def test_negative_response_is_a_result_not_an_error(server):
    async with Client(server) as mcp:
        result = await call(mcp, "read_data_by_identifier", dids=["BEEF"])
    assert result == {
        "service": "ReadDataByIdentifier",
        "ok": False,
        "response": "7F 22 31",
        "nrc": 0x31,
        "nrc_name": "RequestOutOfRange",
        "data": {},
    }


async def test_keep_alive_holds_extended_session(session):
    client, server = session
    async with Client(server) as mcp:
        await call(mcp, "diagnostic_session_control", session="extended")
        time.sleep(1.5)  # longer than S3 (800 ms): only the keep-alive keeps the session
        result = await call(mcp, "read_data_by_identifier", dids=["0100"])
    assert result["ok"], result
    assert client.session == 3


async def test_routine_and_dtcs(server):
    async with Client(server) as mcp:
        await call(mcp, "diagnostic_session_control", session="03")
        routine = await call(mcp, "routine_control", routine_id="0203", control="start")
        assert routine["data"]["status_record"] == "00"
        dtcs = await call(mcp, "read_dtc_information", status_mask="08")
        assert len(dtcs["data"]["dtcs"]) == 2
        assert (await call(mcp, "clear_diagnostic_information"))["ok"]
        assert (await call(mcp, "read_dtc_information"))["data"]["dtcs"] == []


async def test_send_raw_and_reset(session):
    client, server = session
    async with Client(server) as mcp:
        raw = await call(mcp, "send_raw", request_hex="10 03")
        assert raw["response"].startswith("50 03")
        assert client.session == 3
        assert (await call(mcp, "ecu_reset", reset_type="soft"))["ok"]
        assert client.session == 1


async def test_bad_input_is_a_tool_error(server):
    async with Client(server) as mcp:
        bad_hex = await mcp.call_tool("read_data_by_identifier", {"dids": ["XYZ"]})
        both = await mcp.call_tool(
            "write_data_by_identifier", {"did": "F190", "value_hex": "00", "value_ascii": "A"}
        )
    assert bad_hex.is_error and "must be hex" in bad_hex.content[0].text
    assert both.is_error and "exactly one" in both.content[0].text


async def test_stdio_server_process(config_path):
    """The real entry point: an MCP client launches `uds-mcp --interface sim` over stdio."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "uds_mcp.cli", "--interface", "sim", "--config", str(config_path)],
    )
    async with Client(params) as mcp:
        vin = await call(mcp, "read_data_by_identifier", dids=["F190"])
    assert vin["data"]["0xF190"]["ascii"] == "UDSMCP00000000001"


def test_parse_hex():
    assert parse_hex("F190") == parse_hex("0xF190") == parse_hex(" f1 90 ") == 0xF190
    assert parse_hex(3) == 3
    assert parse_bytes("22 F1 90") == bytes.fromhex("22F190")
    with pytest.raises(ToolError, match="must be hex"):
        parse_hex("nope")
