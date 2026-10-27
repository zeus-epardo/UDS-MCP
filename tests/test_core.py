import operator
import uuid
from pathlib import Path

import can
import pytest
from fake_ecu import DIDS, SEED, FakeEcu, key_for

from uds_mcp.core import EcuConfig, UdsClient, load_config, nrc_name
from uds_mcp.interfaces import open_bus

EXAMPLE_CONFIG = Path(__file__).parent.parent / "config" / "example.toml"


def make_config(**timing) -> EcuConfig:
    return EcuConfig.model_validate(
        {
            "timing": {"p2_ms": 1000, "p2_star_ms": 5000, "request_timeout_ms": 3000, **timing},
            "dids": {
                "0xF190": {"name": "VIN", "length": 17, "encoding": "ascii"},
                "0xF186": {"name": "ActiveDiagnosticSession", "length": 1},
            },
        }
    )


@pytest.fixture
def channel():
    return f"uds-mcp-test-{uuid.uuid4().hex}"


@pytest.fixture
def ecu(channel):
    fake = FakeEcu(channel).start()
    original = dict(DIDS)
    yield fake
    fake.stop()
    DIDS.clear()
    DIDS.update(original)


@pytest.fixture
def client(channel, ecu):
    bus = can.Bus(interface="virtual", channel=channel)
    with UdsClient(bus, make_config()) as uds:
        yield uds
    bus.shutdown()


# -- services --------------------------------------------------------------------------------


def test_session_control(client):
    result = client.diagnostic_session_control(3)
    assert result.ok
    assert result.response == "50 03 03 E8 01 F4"
    assert result.data == {"session": 3, "p2_server_max_s": 1.0, "p2_star_server_max_s": 5.0}


def test_ecu_reset(client):
    result = client.ecu_reset(1)
    assert result.ok
    assert result.data["reset_type"] == 1


def test_read_configured_dids(client):
    result = client.read_data_by_identifier([0xF190, 0xF186])
    assert result.ok
    assert result.data["0xF190"] == {
        "hex": DIDS[0xF190].hex(" ").upper(),
        "name": "VIN",
        "ascii": "WDB00000000000001",
    }
    assert result.data["0xF186"] == {"hex": "01", "name": "ActiveDiagnosticSession"}


def test_read_unconfigured_did_alone_returns_raw_bytes(client):
    result = client.read_data_by_identifier(0x0100)
    assert result.ok
    assert result.data == {"0x0100": {"hex": "DE AD BE EF"}}


def test_read_unconfigured_did_with_others_is_refused(client):
    result = client.read_data_by_identifier([0xF190, 0x0100])
    assert not result.ok
    assert "0x0100" in result.error


def test_read_unknown_did_returns_nrc(client):
    result = client.read_data_by_identifier(0xBEEF)
    assert not result.ok
    assert result.nrc == 0x31
    assert result.nrc_name == "RequestOutOfRange"
    assert result.response == "7F 22 31"


def test_write_did(client):
    vin = b"WDB99999999999999"
    assert client.write_data_by_identifier(0xF190, vin).ok
    assert client.read_data_by_identifier(0xF190).data["0xF190"]["ascii"] == vin.decode()


def test_write_did_checks_configured_length(client):
    result = client.write_data_by_identifier(0xF190, b"short")
    assert not result.ok
    assert "17 bytes" in result.error


def test_security_access_unlocks(client, ecu):
    result = client.security_access(1, key_algorithm=lambda level, seed: key_for(seed))
    assert result.ok
    assert result.data == {"seed": SEED.hex(" ").upper(), "level": 1, "unlocked": True}
    assert ecu.unlocked

    again = client.security_access(1, key_algorithm=lambda level, seed: key_for(seed))
    assert again.ok
    assert again.data["already_unlocked"] is True


def test_security_access_wrong_key(client):
    result = client.security_access(1, key_algorithm=lambda level, seed: seed)
    assert not result.ok
    assert result.nrc_name == "InvalidKey"


def test_security_access_without_algorithm(client):
    result = client.security_access(1)
    assert not result.ok
    assert "No key algorithm" in result.error


def test_routine_control(client):
    result = client.routine_control(0x0203, 1)
    assert result.ok
    assert result.data == {"routine_id": "0x0203", "control_type": 1, "status_record": "00"}


def test_read_dtcs(client):
    result = client.read_dtc_information(0x08)
    assert result.ok
    assert result.data["dtcs"] == [
        {"dtc": "0x123456", "status": "0x2F"},
        {"dtc": "0xC07300", "status": "0x08"},
    ]


def test_clear_dtcs(client):
    assert client.clear_diagnostic_information().ok


def test_tester_present(client):
    assert client.tester_present().ok


def test_send_raw(client):
    result = client.send_raw(bytes.fromhex("22F186"))
    assert result.ok
    assert result.request == "22 F1 86"
    assert result.response == "62 F1 86 01"


def test_send_raw_unsupported_service(client):
    result = client.send_raw(bytes.fromhex("BA00"))
    assert not result.ok
    assert result.nrc_name == "ServiceNotSupported"


def test_timeout_without_ecu(channel):
    bus = can.Bus(interface="virtual", channel=channel)
    with UdsClient(bus, make_config(p2_ms=100, request_timeout_ms=200)) as uds:
        result = uds.tester_present()
    bus.shutdown()
    assert not result.ok
    assert result.error.startswith("TimeoutException")


# -- config and bus --------------------------------------------------------------------------


def test_load_example_config():
    config = load_config(EXAMPLE_CONFIG)
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
