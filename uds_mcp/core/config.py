"""ECU configuration loaded from a TOML file (see ``config/example.toml``)."""

from __future__ import annotations

import importlib
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

KeyAlgorithm = Callable[[int, bytes], bytes]
"""Signature of a security-access key algorithm: ``(level, seed) -> key``."""


class EcuSettings(BaseModel):
    name: str = "ecu"
    request_id: int = 0x7E0
    response_id: int = 0x7E8
    functional_id: int | None = 0x7DF
    addressing: Literal["normal", "extended"] = "normal"
    can_fd: bool = False
    bitrate: int = 500_000
    data_bitrate: int = 2_000_000


class TimingSettings(BaseModel):
    p2_ms: int = 50
    p2_star_ms: int = 5000
    tester_present_interval_ms: int = 2000
    request_timeout_ms: int = 5000


class DidSpec(BaseModel):
    name: str
    length: int | None = Field(default=None, gt=0)
    encoding: Literal["hex", "ascii"] = "hex"


class SecurityLevel(BaseModel):
    seed_len: int | None = None
    key_algorithm: str = Field(description="Import path of the key function, 'pkg.module:func'")

    def load_algorithm(self) -> KeyAlgorithm:
        module_name, _, attr = self.key_algorithm.partition(":")
        if not module_name or not attr:
            raise ValueError(
                f"key_algorithm must look like 'pkg.module:func', got {self.key_algorithm!r}"
            )
        return getattr(importlib.import_module(module_name), attr)


def _int_keys(value: dict) -> dict:
    # TOML table keys are strings, so DIDs and routine IDs arrive as "0xF190".
    return {int(k, 0) if isinstance(k, str) else k: v for k, v in value.items()}


class SimDid(BaseModel):
    """Simulated DID. ``value`` is ASCII text for DIDs with ``encoding = "ascii"``, else hex."""

    value: str
    writable: bool = False
    read_sessions: list[int] | None = None
    write_sessions: list[int] | None = None
    write_security_level: int | None = None


class SimRoutine(BaseModel):
    name: str = ""
    sessions: list[int] | None = None
    security_level: int | None = None
    result: str = Field(default="", description="Hex status record returned by the routine")
    duration_ms: int = Field(default=0, ge=0, description="Answers 0x78 first when above P2")


class SimDtc(BaseModel):
    code: int
    status: int


class SimConfig(BaseModel):
    """Behaviour of the ECU simulator; ignored by the client."""

    sessions: list[int] = [1, 2, 3]
    reset_types: list[int] = [1, 2, 3]
    s3_ms: int = 5000
    seed: str | None = Field(default=None, description="Fixed hex seed; random when omitted")
    max_key_attempts: int = 3
    dids: dict[int, SimDid] = Field(default_factory=dict)
    routines: dict[int, SimRoutine] = Field(default_factory=dict)
    dtcs: list[SimDtc] = Field(default_factory=list)

    _parse_ids = field_validator("dids", "routines", mode="before")(_int_keys)


class EcuConfig(BaseModel):
    ecu: EcuSettings = Field(default_factory=EcuSettings)
    timing: TimingSettings = Field(default_factory=TimingSettings)
    dids: dict[int, DidSpec] = Field(default_factory=dict)
    security: dict[int, SecurityLevel] = Field(default_factory=dict)
    sim: SimConfig = Field(default_factory=SimConfig)

    _parse_did_keys = field_validator("dids", mode="before")(_int_keys)

    @field_validator("security", mode="before")
    @classmethod
    def _parse_security_keys(cls, value: dict) -> dict:
        # Accept "level_1", "1" or "0x01" as the key for security level 1.
        parsed = {}
        for key, spec in value.items():
            if isinstance(key, str):
                key = int(key.removeprefix("level_"), 0)
            parsed[key] = spec
        return parsed


def load_config(path: str | Path) -> EcuConfig:
    with open(path, "rb") as f:
        return EcuConfig.model_validate(tomllib.load(f))
