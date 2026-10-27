"""Run the simulator as a standalone ECU, e.g. on a Raspberry Pi with a CAN HAT.

python -m uds_mcp.sim --interface socketcan --channel can0 --config config/sim.toml
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

from uds_mcp.core.config import load_config
from uds_mcp.interfaces import PYTHON_CAN_INTERFACES, open_bus
from uds_mcp.sim.server import SimulatorServer

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "sim.toml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m uds_mcp.sim", description="UDS ECU simulator")
    parser.add_argument("--interface", choices=tuple(PYTHON_CAN_INTERFACES), default="sim")
    parser.add_argument("--channel", default=None)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)

    config = load_config(args.config)
    ecu = config.ecu
    bus = open_bus(args.interface, args.channel, ecu.bitrate, ecu.can_fd, ecu.data_bitrate)
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    with SimulatorServer(bus, config):
        print(
            f"Simulating {ecu.name!r} on {args.interface}: "
            f"request 0x{ecu.request_id:X}, response 0x{ecu.response_id:X}. Ctrl+C to stop.",
            file=sys.stderr,
        )
        stop.wait()
    bus.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
