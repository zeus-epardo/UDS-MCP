"""UdsClient against the simulator on a python-can virtual bus."""

import operator
import uuid
from pathlib import Path

import can
import pytest

from uds_mcp.core import EcuConfig, UdsClient, load_config, nrc_name
from uds_mcp.core.config import SimDid
from uds_mcp.interfaces import open_bus
from uds_mcp.sim import SimulatorServer

CONFIG_DIR = Path(__file__).parent.parent / "config"


def sim_config(**timing) -> EcuConfig:
    config = load_config(CONFIG_DIR / "sim.toml")
    config.timing = config.timing.model_copy(
        update={"p2_ms": 200, "request_timeout_ms": 3000, **timing}
    )
    # A DID the client has no length for, to exercise raw reads.
    config.sim.dids[0x0200] = SimDid(value="DEADBEEF")
    return config


@pytest.fixture
def channel():
    return f"uds-mcp-test-{uuid.uuid4().hex}"


@pytest.fixture
def config():
    return sim_config()


@pytest.fixture
def sim(channel, config):
    bus = can.Bus(interface="virtual", channel=channel)
    with SimulatorServer(bus, config) as server:
        yield server.ecu
    bus.shutdown()


@pytest.fixture
def client(channel, config, sim):
    bus = can.Bus(interface="virtual", channel=channel)
    with UdsClient(bus, config) as uds:
        yield uds
    bus.shutdown()


@pytest.fixture
def extended(client):
    assert client.diagnostic_session_control(3).ok
    return client


# -- sessions and reset ----------------------------------------------------------------------


def test_session_control(client, sim):
    result = client.diagnostic_session_control(3)
    assert result.ok
    assert result.response == "50 03 00 C8 01 F4"
    assert result.data == {"session": 3, "p2_server_max_s": 0.2, "p2_star_server_max_s": 5.0}
    assert sim.session == 3


def test_unsupported_session(client):
    result = client.diagnostic_session_control(0x40)
    assert result.nrc_name == "SubFunctionNotSupported"


def test_ecu_reset_returns_to_default_session(extended, sim):
    result = extended.ecu_reset(1)
    assert result.ok
    assert result.data["reset_type"] == 1
    assert sim.session == 1


# -- DIDs ------------------------------------------------------------------------------------


def test_read_configured_dids(client):
    result = client.read_data_by_identifier([0xF190, 0xF186])
    assert result.ok
    assert result.data["0xF190"]["ascii"] == "UDSMCP00000000001"
    assert result.data["0xF190"]["name"] == "VIN"
    assert result.data["0xF186"] == {"hex": "01", "name": "ActiveDiagnosticSession"}


def test_read_did_gated_by_session(client):
    assert client.read_data_by_identifier(0x0100).nrc_name == "RequestOutOfRange"
    client.diagnostic_session_control(3)
    result = client.read_data_by_identifier(0x0100)
    assert result.data["0x0100"] == {"hex": "00 64", "name": "DemoCalibrationValue"}


def test_read_unconfigured_did_alone_returns_raw_bytes(client):
    result = client.read_data_by_identifier(0x0200)
    assert result.ok
    assert result.data == {"0x0200": {"hex": "DE AD BE EF"}}


def test_read_unconfigured_did_with_others_is_refused(client):
    result = client.read_data_by_identifier([0xF190, 0x0200])
    assert not result.ok
    assert "0x0200" in result.error


def test_read_unknown_did_returns_nrc(client):
    result = client.read_data_by_identifier(0xBEEF)
    assert not result.ok
    assert result.nrc == 0x31
    assert result.nrc_name == "RequestOutOfRange"
    assert result.response == "7F 22 31"


def test_write_did_needs_session_and_security(client):
    vin = b"UDSMCP99999999999"
    assert client.write_data_by_identifier(0xF190, vin).nrc_name == "RequestOutOfRange"
    client.diagnostic_session_control(3)
    assert client.write_data_by_identifier(0xF190, vin).nrc_name == "SecurityAccessDenied"
    assert client.security_access(1).ok
    assert client.write_data_by_identifier(0xF190, vin).ok
    assert client.read_data_by_identifier(0xF190).data["0xF190"]["ascii"] == vin.decode()


def test_write_did_checks_configured_length(client):
    result = client.write_data_by_identifier(0xF190, b"short")
    assert not result.ok
    assert "17 bytes" in result.error


# -- security access -------------------------------------------------------------------------


def test_security_access_not_in_default_session(client):
    result = client.security_access(1)
    assert result.nrc_name == "ServiceNotSupportedInActiveSession"


def test_security_access_with_configured_algorithm(extended, sim):
    result = extended.security_access(1)
    assert result.ok
    assert result.data["unlocked"] is True
    assert sim.unlocked == {1}

    again = extended.security_access(1)
    assert again.ok
    assert again.data["already_unlocked"] is True


def test_security_access_wrong_key(extended):
    result = extended.security_access(1, key_algorithm=lambda level, seed: seed)
    assert not result.ok
    assert result.nrc_name == "InvalidKey"


def test_security_access_without_algorithm(extended):
    result = extended.security_access(3)
    assert not result.ok
    assert "No key algorithm" in result.error


# -- routines, DTCs, tester present ----------------------------------------------------------


def test_routine_with_response_pending(extended):
    # DemoSelfTest takes 300 ms, longer than P2 (200 ms): the simulator answers 0x78 first.
    result = extended.routine_control(0x0203, 1)
    assert result.ok
    assert result.data == {"routine_id": "0x0203", "control_type": 1, "status_record": "00"}


def test_routine_results_before_start(extended):
    assert extended.routine_control(0x0203, 3).nrc_name == "RequestSequenceError"


def test_routine_needs_security(extended):
    assert extended.routine_control(0x0204, 1).nrc_name == "SecurityAccessDenied"
    extended.security_access(1)
    assert extended.routine_control(0x0204, 1).ok


def test_read_and_clear_dtcs(client):
    result = client.read_dtc_information(0x08)
    assert result.ok
    assert result.data["dtcs"] == [
        {"dtc": "0x012300", "status": "0x2F"},
        {"dtc": "0xC07300", "status": "0x08"},
    ]
    assert client.read_dtc_information(0x01).data["dtcs"] == [{"dtc": "0x012300", "status": "0x2F"}]
    assert client.clear_diagnostic_information().ok
    assert client.read_dtc_information(0xFF).data["dtcs"] == []


def test_tester_present(client):
    assert client.tester_present().ok


# -- raw requests ----------------------------------------------------------------------------


def test_send_raw(client):
    result = client.send_raw(bytes.fromhex("22F186"))
    assert result.ok
    assert result.request == "22 F1 86"
    assert result.response == "62 F1 86 01"


def test_send_raw_waits_through_response_pending(extended):
    result = extended.send_raw(bytes.fromhex("31010203"))
    assert result.ok
    assert result.response == "71 01 02 03 00"


def test_send_raw_unsupported_service(client):
    result = client.send_raw(bytes.fromhex("BA00"))
    assert not result.ok
    assert result.nrc_name == "ServiceNotSupported"


def test_timeout_without_ecu(channel):
    bus = can.Bus(interface="virtual", channel=channel)
    with UdsClient(bus, sim_config(p2_ms=100, request_timeout_ms=200)) as uds:
        result = uds.tester_present()
    bus.shutdown()
    assert not result.ok
    assert result.error.startswith("TimeoutException")


# -- config and bus --------------------------------------------------------------------------


def test_load_example_config():
    config = load_config(CONFIG_DIR / "example.toml")
    assert config.ecu.request_id == 0x7E0
    assert config.ecu.response_id == 0x7E8
    assert config.dids[0xF190].length == 17
    assert config.dids[0xF190].encoding == "ascii"
    assert config.security[1].seed_len == 4


def test_load_key_algorithm():
    config = EcuConfig.model_validate({"security": {"level_1": {"key_algorithm": "operator:xor"}}})
    assert config.security[1].load_algorithm() is operator.xor


def test_extended_addressing_not_supported_yet(channel):
    bus = can.Bus(interface="virtual", channel=channel)
    config = EcuConfig.model_validate({"ecu": {"addressing": "extended"}})
    with pytest.raises(ValueError, match="not supported"):
        UdsClient(bus, config)
    bus.shutdown()


def test_open_bus_sim(channel):
    bus = open_bus("sim", channel=channel)
    assert isinstance(bus, can.BusABC)
    bus.shutdown()


def test_open_bus_unknown_interface():
    with pytest.raises(ValueError):
        open_bus("nope")


def test_nrc_name():
    assert nrc_name(0x78) == "RequestCorrectlyReceived_ResponsePending"
