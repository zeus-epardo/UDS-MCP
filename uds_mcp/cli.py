"""Command-line entry point for the UDS-MCP server."""

from __future__ import annotations

import argparse
import sys

from uds_mcp import __version__

INTERFACES = ("sim", "pcan", "intrepid", "vector", "socketcan")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uds-mcp", description="MCP server for ISO 14229 diagnostics"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--interface", choices=INTERFACES, default="sim", help="CAN backend")
    parser.add_argument("--channel", default=None, help="Vendor channel (e.g. PCAN_USBBUS1, can0)")
    parser.add_argument("--bitrate", type=int, default=500_000, help="Arbitration bitrate (bit/s)")
    parser.add_argument("--fd", action="store_true", help="Enable CAN FD")
    parser.add_argument("--config", default=None, help="Path to an ECU configuration file")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # TODO: wire up interface backend, access manager and MCP server.
    print(
        f"uds-mcp {__version__}: interface={args.interface} channel={args.channel} "
        f"bitrate={args.bitrate} fd={args.fd} transport={args.transport}",
        file=sys.stderr,
    )
    print("MCP server not implemented yet - see README roadmap.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
