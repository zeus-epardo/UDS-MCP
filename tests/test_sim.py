"""SimulatedEcu logic, without a bus."""

from pathlib import Path

import pytest

from uds_mcp.core import load_config
from uds_mcp.core.config import EcuConfig
from uds_mcp.sim import SimulatedEcu
from uds_mcp.sim.demo_keys import xor_ff

CONFIG = Path(__file__).parent.parent / "config" / "sim.toml"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ecu(clock):
    config = load_config(CONFIG)
    config.sim.seed = "11223344"
    return SimulatedEcu(config, clock=clock)


def ask(ecu: SimulatedEcu, request: str) -> list[str]:
    return [payload.hex(" ").upper() for _, payload in ecu.handle(bytes.fromhex(request))]


def unlock(ecu: SimulatedEcu) -> None:
    ask(ecu, "1003")
    seed = ecu.handle(bytes.fromhex("2701"))[0][1][2:]
    assert ask(ecu, "2702" + xor_ff(1, seed).hex()) == ["67 02"]


def test_s3_timeout_returns_to_default_session(ecu, clock):
    unlock(ecu)
    clock.now += 4.9
    ecu.check_s3()
    assert ecu.session == 3
    clock.now += 5.1
    ecu.check_s3()
    assert ecu.session == 1
    assert ecu.unlocked == set()


def test_requests_keep_the_session_alive(ecu, clock):
    ask(ecu, "1003")
    for _ in range(3):
        clock.now += 4
        assert ask(ecu, "3E00") == ["7E 00"]
    assert ecu.session == 3


def test_suppress_positive_response(ecu):
    assert ask(ecu, "1083") == []
    assert ecu.session == 3
    assert ask(ecu, "3E80") == []


@pytest.mark.parametrize("request_hex", ["10", "1003FF", "22F1", "2EF190", "3E", "1401"])
def test_incorrect_message_length(ecu, request_hex):
    sid = request_hex[:2]
    assert ask(ecu, request_hex) == [f"7F {sid} 13"]


def test_unknown_service(ecu):
    assert ask(ecu, "BA00") == ["7F BA 11"]


def test_send_key_without_seed(ecu):
    ask(ecu, "1003")
    assert ask(ecu, "270200000000") == ["7F 27 24"]


def test_exceeded_number_of_attempts(ecu):
    ask(ecu, "1003")
    ask(ecu, "2701")
    assert ask(ecu, "270200000000") == ["7F 27 35"]
    assert ask(ecu, "270200000000") == ["7F 27 35"]
    assert ask(ecu, "270200000000") == ["7F 27 36"]
    # Even the right key is refused until the session is reset.
    assert ask(ecu, "2702" + xor_ff(1, bytes.fromhex("11223344")).hex()) == ["7F 27 36"]


def test_unlocked_level_returns_zero_seed(ecu):
    unlock(ecu)
    assert ask(ecu, "2701") == ["67 01 00 00 00 00"]


def test_session_change_relocks(ecu):
    unlock(ecu)
    ask(ecu, "1003")
    assert ecu.unlocked == set()


def test_long_routine_answers_response_pending_first(ecu):
    ask(ecu, "1003")
    replies = ecu.handle(bytes.fromhex("31010203"))
    assert [(delay, payload.hex(" ").upper()) for delay, payload in replies] == [
        (0.0, "7F 31 78"),
        (0.3, "71 01 02 03 00"),
    ]


def test_dtc_count_and_selective_clear(ecu):
    assert ask(ecu, "1901FF") == ["59 01 FF 01 00 02"]
    assert ask(ecu, "14012300") == ["54"]
    assert ask(ecu, "1901FF") == ["59 01 FF 01 00 01"]
    assert ask(ecu, "14AABBCC") == ["7F 14 31"]


def test_write_wrong_length(ecu):
    unlock(ecu)
    assert ask(ecu, "2EF190" + "41" * 5) == ["7F 2E 13"]


def test_sim_value_must_match_did_length():
    config = EcuConfig.model_validate(
        {
            "dids": {"0xF190": {"name": "VIN", "length": 17, "encoding": "ascii"}},
            "sim": {"dids": {"0xF190": {"value": "TOO-SHORT"}}},
        }
    )
    with pytest.raises(ValueError, match="expected 17"):
        SimulatedEcu(config)


def test_random_seed_is_never_zero():
    config = load_config(CONFIG)
    ecu = SimulatedEcu(config)
    ecu.handle(bytes.fromhex("1003"))
    seeds = {ecu.handle(bytes.fromhex("2701"))[0][1][2:] for _ in range(20)}
    assert all(any(seed) and len(seed) == 4 for seed in seeds)
