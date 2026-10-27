from uds_mcp import __version__
from uds_mcp.cli import build_parser


def test_version_is_set():
    assert __version__


def test_defaults():
    args = build_parser().parse_args([])
    assert args.interface == "sim"
    assert args.bitrate is None
    assert args.transport == "stdio"
