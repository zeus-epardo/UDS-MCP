# UDS-MCP

**An MCP server for ISO 14229 (UDS) automotive diagnostics.**

UDS-MCP exposes Unified Diagnostic Services as [Model Context Protocol](https://modelcontextprotocol.io) tools, so any MCP client (Claude Desktop, an IDE agent, a custom test runner) can run diagnostics against a real ECU on a CAN bus — or against the built-in simulator — without touching the hardware directly.

> Status: **early development**. The MCP server, UDS client core and ECU simulator work end to end on a virtual CAN bus — try it with no hardware. Hardware backends are wired but not yet validated, and claim/release access control is next. See the [roadmap](#roadmap).

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
| ISO 14229 client services (0x10, 0x11, 0x14, 0x19, 0x22, 0x27, 0x2E, 0x31, 0x3E, raw) | ✅ built on [udsoncan](https://github.com/pylessard/python-udsoncan) |
| ISO 15765-2 (ISO-TP) transport over CAN / CAN FD | ✅ built on [can-isotp](https://github.com/pylessard/python-can-isotp) |
| Virtual CAN bus (no hardware, used by tests) | ✅ |
| PCAN · Intrepid neoVI / ValueCAN 4 · Vector XL · SocketCAN | 🧪 wired through python-can, not yet validated on hardware |
| MCP server (stdio) with UDS tools and a TesterPresent keep-alive | ✅ |
| MCP over HTTP (streamable) | 🧪 starts, no access control yet |
| Claim / release model for shared DUT access | 🔜 next |
| Live traffic reader with message classification | 🔜 planned |
| Software ECU simulator, configured from TOML (sessions, S3, security, DIDs, routines, DTCs, 0x78) | ✅ |
| Simulator on Raspberry Pi 5 + Waveshare 2-CH CAN FD HAT (SocketCAN) | 🧪 runs via `python -m uds_mcp.sim`, not yet validated on hardware |
| Test-plan execution with Excel report export | 🔜 planned |

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

### Run the simulator

The simulator answers like a real ECU, configured by the `[sim]` section of the demo ECU
[`uds_mcp/sim/demo_ecu.toml`](uds_mcp/sim/demo_ecu.toml): sessions with S3 timeout, seed/key
security access, session- and security-gated DIDs and routines, DTCs and response-pending (0x78).
`uds-mcp --interface sim` starts it in-process automatically. To run it as a standalone ECU,
for example on a Raspberry Pi with a CAN HAT:

```bash
python -m uds_mcp.sim --interface socketcan --channel can0
```

### Run the server

```bash
# Against the built-in simulator (no hardware)
uds-mcp --interface sim

# Against a real ECU through PCAN, with your own ECU config
uds-mcp --interface pcan --channel PCAN_USBBUS1 --config config/my-ecu.local.toml
```

The server speaks MCP over stdio (default) or streamable HTTP (`--transport http`).
While the ECU is outside the default session, it sends TesterPresent (0x3E 80) in the
background so the session survives the pauses of a person or an LLM.

To see a full scripted session (read VIN, extended session, security access, write,
routine, DTCs) without any MCP client installed:

```bash
python examples/demo_client.py
```

### Connect an MCP client

Claude Code:

```bash
claude mcp add uds -- uds-mcp --interface sim
```

Claude Desktop (`claude_desktop_config.json`, use the full path to `uds-mcp` from your venv):

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
open an extended session, unlock security level 1 and change the VIN to UDSMCP12345678901
```

## MCP tools

IDs and payloads are hex strings (`"F190"`, `"0xF190"`, `"22 F1 90"`). Every UDS tool returns
the same JSON shape: `{service, ok, request, response, nrc, nrc_name, error, data}`. A
negative response is a normal result (`ok: false`, `nrc_name: "SecurityAccessDenied"`), so
the agent can reason about it.

| Tool | Description | Status |
|---|---|---|
| `get_ecu_info` | ECU addresses, current session, known DIDs, routines, security levels | ✅ |
| `diagnostic_session_control` | 0x10 — `default`, `programming`, `extended`, `safety` or a number | ✅ |
| `ecu_reset` | 0x11 — `hard`, `key_off_on`, `soft` or a number | ✅ |
| `read_data_by_identifier` | 0x22 — one or more DIDs, decoded by the ECU config | ✅ |
| `write_data_by_identifier` | 0x2E — value as hex or ASCII | ✅ |
| `security_access` | 0x27 — seed/key with the key algorithm configured for the level | ✅ |
| `routine_control` | 0x31 — `start` / `stop` / `results` | ✅ |
| `read_dtc_information` | 0x19 02 — DTCs by status mask | ✅ |
| `clear_diagnostic_information` | 0x14 | ✅ |
| `tester_present` | 0x3E (a background keep-alive already runs) | ✅ |
| `send_raw` | Any UDS request as hex, raw response back (handles 0x78) | ✅ |
| `claim_dut` / `release_dut` | Acquire or release exclusive write access to the DUT | 🔜 |
| `read_traffic` | Stream classified bus traffic (diagnostic / non-diagnostic / unknown) | 🔜 |
| `run_test_plan` | Execute a test plan file and export results | 🔜 |

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

1. **Access control** — claim/release access manager for shared DUTs over HTTP.
2. **Multi-interface** — validate PCAN, neoVI / ValueCAN 4, Vector XL and SocketCAN on hardware.
3. **Live traffic reader** — passive bus capture with classification against a configurable rule database.
4. **Simulator on hardware** — validate the software simulator on a Raspberry Pi 5 + Waveshare 2-CH CAN FD HAT.
5. **Test plans** — a test-plan runner with Excel report export.

## Scope and disclaimer

This project implements publicly available standards (ISO 14229, ISO 15765) and contains **no proprietary OEM or supplier data**: no vendor-specific DIDs, routines, security algorithms, ECU configurations or test results. Everything specific to a given vehicle program must be supplied by the user through configuration files that are not part of this repository.

Use at your own risk. Writing to or reprogramming an ECU can brick it. Always test against the simulator first.

## Contributing

Issues and pull requests are welcome. Please open an issue before large changes so we can agree on the design. Run `ruff` and `pytest` before submitting.

## License

MIT — see [LICENSE](LICENSE).

## Credits

UDS-MCP is created by **[Zeus Epardo](https://github.com/zeus-epardo)** and co-created with
**[Claude](https://www.anthropic.com/claude)** (Anthropic) through Claude Code: design,
implementation and docs are built together, and Claude's commits carry a `Co-Authored-By` trailer.

Built on the shoulders of [python-can](https://github.com/hardbyte/python-can),
[can-isotp](https://github.com/pylessard/python-can-isotp),
[udsoncan](https://github.com/pylessard/python-udsoncan) and the
[Model Context Protocol](https://modelcontextprotocol.io) SDK.
