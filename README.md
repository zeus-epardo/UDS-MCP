# UDS-MCP

**An MCP server for ISO 14229 (UDS) automotive diagnostics.**

UDS-MCP exposes Unified Diagnostic Services as [Model Context Protocol](https://modelcontextprotocol.io) tools, so any MCP client (Claude Desktop, an IDE agent, a custom test runner) can run diagnostics against a real ECU on a CAN bus — or against the built-in simulator — without touching the hardware directly.

> Status: **early development**. The UDS core and PCAN backend are functional; the MCP layer, additional interfaces and the simulator are in progress. See the [roadmap](#roadmap).

---

## Why

Diagnostic benches are usually a tower with a CAN interface and one device under test (DUT), physically owned by one person. UDS-MCP turns that tower into a service:

- A tester runs `read_did`, `routine_control` or a full test plan from a laptop on the other side of the building, through an MCP client.
- An LLM agent can drive an exploratory diagnostic session, interpret negative responses and log the results.
- Several people can share one DUT safely thanks to a **claim / release** model: only the client holding the claim can send requests; everyone else can read traffic.
- When there is no hardware at all, the **simulator** answers like an ECU would, so test plans and tooling can be developed and validated offline.

## Features

| Area | Status |
|---|---|
| ISO 14229 services (0x10, 0x11, 0x14, 0x19, 0x22, 0x27, 0x2E, 0x31, 0x3E, …) | ✅ core implemented |
| ISO 15765-2 (ISO-TP) transport over CAN / CAN FD | ✅ |
| PCAN (Peak) interface | ✅ |
| Intrepid neoVI / ValueCAN 4 interface | 🧪 implemented, untested on hardware |
| Vector (XL driver) interface | 🔜 planned |
| MCP tools and resources | 🚧 in progress |
| Claim / release model for shared DUT access | 🚧 in progress |
| Live traffic reader with message classification | 🔜 planned |
| ECU simulator (Raspberry Pi 5 + Waveshare 2-CH CAN FD HAT) | 🔜 planned |
| Test-plan execution with Excel report export | 🔜 port from existing GUI tool |

## Architecture

```
┌──────────────┐   MCP (stdio / HTTP)   ┌───────────────────────────┐
│  MCP client  │ ─────────────────────▶ │  UDS-MCP server           │
│ (Claude, IDE,│ ◀───────────────────── │  • tools: session, DIDs,  │
│  test runner)│                        │    routines, DTCs, raw    │
└──────────────┘                        │  • resources: traffic log │
                                        │  • access manager         │
                                        │    (claim / release)      │
                                        └─────────────┬─────────────┘
                                                      │ ISO 14229 / ISO-TP
                                        ┌─────────────┴─────────────┐
                                        │  CAN interface backend    │
                                        │  PCAN · neoVI · ValueCAN  │
                                        │  Vector · SocketCAN       │
                                        └─────────────┬─────────────┘
                                                      │ CAN / CAN FD
                                            ┌─────────┴─────────┐
                                            │  Real ECU (DUT)   │
                                            │  or UDS simulator │
                                            └───────────────────┘
```

## Quick start

### Requirements

- Python 3.11+
- A supported CAN interface with its vendor driver installed, **or** the simulator (no hardware needed)

### Install

```bash
git clone https://github.com/zeus-epardo/UDS-MCP.git
cd UDS-MCP
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Run the server

```bash
# Against a PCAN interface
uds-mcp --interface pcan --channel PCAN_USBBUS1 --bitrate 500000

# Against the simulator (no hardware)
uds-mcp --interface sim
```

### Connect an MCP client

Example for Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "uds": {
      "command": "uds-mcp",
      "args": ["--interface", "sim"]
    }
  }
}
```

Then, from the client:

```
claim the DUT, open an extended session on 0x7E0/0x7E8 and read DID 0xF190
```

## MCP tools (planned surface)

| Tool | Description |
|---|---|
| `claim_dut` / `release_dut` | Acquire or release exclusive write access to the DUT |
| `diagnostic_session_control` | 0x10 — switch session (default, programming, extended, …) |
| `ecu_reset` | 0x11 |
| `read_data_by_identifier` | 0x22 — read one or more DIDs |
| `write_data_by_identifier` | 0x2E |
| `security_access` | 0x27 — seed/key, with pluggable key algorithms |
| `routine_control` | 0x31 — start / stop / request results |
| `read_dtc_information` | 0x19 |
| `clear_diagnostic_information` | 0x14 |
| `tester_present` | 0x3E (also available as a background keep-alive) |
| `send_raw` | Send an arbitrary UDS request and get the decoded response |
| `read_traffic` | Stream classified bus traffic (diagnostic / non-diagnostic / unknown) |
| `run_test_plan` | Execute a test plan file and export results |

## Project layout

```
uds_mcp/
├── core/          # ISO 14229 services, NRC decoding, ISO-TP
├── interfaces/    # One backend per CAN vendor (pcan, intrepid, vector, socketcan, sim)
├── server/        # MCP server, tools, resources, access manager
├── classify/      # Traffic classification rules and database
├── testplan/      # Test-plan loader, runner and Excel reporter
└── sim/           # ECU simulator (host and Raspberry Pi targets)
tests/
docs/
```

## Roadmap

1. **MCP layer** — wrap the existing UDS core as MCP tools; claim/release access manager.
2. **Multi-interface** — validate neoVI / ValueCAN 4 on hardware; add Vector XL and SocketCAN.
3. **Live traffic reader** — passive bus capture with classification against a configurable rule database.
4. **Simulator** — a configurable UDS ECU on Raspberry Pi 5 + Waveshare 2-CH CAN FD HAT, plus a pure-software mode for CI.
5. **Test plans** — port the test-plan runner and Excel reporting from the existing GUI tool.

## Scope and disclaimer

This project implements publicly available standards (ISO 14229, ISO 15765) and contains **no proprietary OEM or supplier data**: no vendor-specific DIDs, routines, security algorithms, ECU configurations or test results. Everything specific to a given vehicle program must be supplied by the user through configuration files that are not part of this repository.

Use at your own risk. Writing to or reprogramming an ECU can brick it. Always test against the simulator first.

## Contributing

Issues and pull requests are welcome. Please open an issue before large changes so we can agree on the design. Run `ruff` and `pytest` before submitting.

## License

MIT — see [LICENSE](LICENSE).
