"""Command-line entry point for the UDS-MCP server."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager

from mcp.server.mcpserver import MCPServer

from uds_mcp import __version__
from uds_mcp.core.client import UdsClient
from uds_mcp.core.config import EcuConfig, load_config
from uds_mcp.interfaces import PYTHON_CAN_INTERFACES, open_bus
from uds_mcp.server import build_server
from uds_mcp.sim import DEMO_CONFIG, SimulatorServer

INTERFACES = tuple(PYTHON_CAN_INTERFACES)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uds-mcp", description="MCP server for ISO 14229 diagnostics"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--interface", choices=INTERFACES, default="sim", help="CAN backend")
    parser.add_argument("--channel", default=None, help="Vendor channel (e.g. PCAN_USBBUS1, can0)")
    parser.add_argument(
        "--bitrate", type=int, default=None, help="Arbitration bitrate (bit/s); default: config"
    )
    parser.add_argument("--fd", action="store_true", help="Enable CAN FD")
    parser.add_argument(
        "--config",
        default=None,
        help="ECU configuration file; default: the demo ECU for sim, standard OBD IDs otherwise",
    )
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    return parser


def resolve_config(args: argparse.Namespace) -> EcuConfig:
    if args.config:
        config = load_config(args.config)
    elif args.interface == "sim":
        config = load_config(DEMO_CONFIG)
    else:
        config = EcuConfig()
    if args.bitrate is not None:
        config.ecu.bitrate = args.bitrate
    if args.fd:
        config.ecu.can_fd = True
    return config


@contextmanager
def open_session(args: argparse.Namespace) -> Iterator[tuple[UdsClient, MCPServer]]:
    """Open the bus (plus the simulator for ``sim``), the UDS client and the MCP server."""
    config = resolve_config(args)
    ecu = config.ecu
    with ExitStack() as stack:
        if args.interface == "sim":
            channel = args.channel or f"uds-mcp-{os.getpid()}"
            sim_bus = open_bus("sim", channel)
            stack.callback(sim_bus.shutdown)
            stack.enter_context(SimulatorServer(sim_bus, config))
            bus = open_bus("sim", channel)
        else:
            bus = open_bus(args.interface, args.channel, ecu.bitrate, ecu.can_fd, ecu.data_bitrate)
        stack.callback(bus.shutdown)
        client = stack.enter_context(UdsClient(bus, config))
        client.start_keep_alive()
        yield client, build_server(client, interface=args.interface)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with open_session(args) as (client, server):
        ecu = client.config.ecu
        # stdout carries the MCP protocol over stdio: log to stderr only.
        print(
            f"uds-mcp {__version__}: {ecu.name!r} on {args.interface}, request 0x{ecu.request_id:X}"
            f" / response 0x{ecu.response_id:X}, transport={args.transport}",
            file=sys.stderr,
        )
        if args.transport == "http":
            print(
                "warning: no claim/release access control yet; anyone who reaches the HTTP "
                "endpoint can send requests to the ECU.",
                file=sys.stderr,
            )
            server.run("streamable-http")
        else:
            server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
