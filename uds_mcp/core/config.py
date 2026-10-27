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


class EcuConfig(BaseModel):
    ecu: EcuSettings = Field(default_factory=EcuSettings)
    timing: TimingSettings = Field(default_factory=TimingSettings)
    dids: dict[int, DidSpec] = Field(default_factory=dict)
    security: dict[int, SecurityLevel] = Field(default_factory=dict)

    @field_validator("dids", mode="before")
    @classmethod
    def _parse_did_keys(cls, value: dict) -> dict:
        # TOML table keys are strings, so DIDs arrive as "0xF190".
        return {int(k, 0) if isinstance(k, str) else k: v for k, v in value.items()}

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
