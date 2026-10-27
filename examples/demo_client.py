"""Scripted MCP session against the simulator, the same calls an LLM agent would make.

python examples/demo_client.py
"""

import asyncio
import json
import sys

from mcp import StdioServerParameters
from mcp.client import Client

STEPS = [
    ("get_ecu_info", {}),
    ("read_data_by_identifier", {"dids": ["F190", "F18C"]}),
    ("diagnostic_session_control", {"session": "extended"}),
    ("read_data_by_identifier", {"dids": ["0100"]}),
    ("write_data_by_identifier", {"did": "F190", "value_ascii": "UDSMCP12345678901"}),
    ("security_access", {"level": 1}),
    ("write_data_by_identifier", {"did": "F190", "value_ascii": "UDSMCP12345678901"}),
    ("routine_control", {"routine_id": "0203", "control": "start"}),
    ("read_dtc_information", {"status_mask": "FF"}),
    ("send_raw", {"request_hex": "22 F1 90"}),
]


async def main() -> None:
    server = StdioServerParameters(
        command=sys.executable, args=["-m", "uds_mcp.cli", "--interface", "sim"]
    )
    async with Client(server) as mcp:
        for tool, arguments in STEPS:
            result = await mcp.call_tool(tool, arguments)
            print(f"> {tool}({json.dumps(arguments)})")
            print(json.dumps(json.loads(result.content[0].text), indent=2), end="\n\n")


if __name__ == "__main__":
    asyncio.run(main())
