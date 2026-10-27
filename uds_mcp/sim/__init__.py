"""UDS ECU simulator configured from the ``[sim]`` section of an ECU config."""

from pathlib import Path

from uds_mcp.sim.ecu import SimulatedEcu
from uds_mcp.sim.server import SimulatorServer

DEMO_CONFIG = Path(__file__).with_name("demo_ecu.toml")
"""Generic demo ECU used by ``--interface sim`` and the tests."""

__all__ = ["DEMO_CONFIG", "SimulatedEcu", "SimulatorServer"]
