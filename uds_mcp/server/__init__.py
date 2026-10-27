"""MCP server exposing the UDS client as tools."""

from uds_mcp.server.app import build_server

__all__ = ["build_server"]
