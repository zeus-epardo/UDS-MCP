# CLAUDE.md

Context for Claude sessions working on UDS-MCP. Team-wide memory and the session ritual
live in Zeus's global `~/.claude/CLAUDE.md`; this file only holds what is specific to
this project. At the end of a session, update "Decisions" and "Next steps" here.

## Project

UDS-MCP is created by Zeus Epardo and co-created with Claude. It is free, MIT-licensed and
doubles as Zeus's public portfolio, so code quality, honest docs and a clean history matter.
Talk with Zeus in Spanish; keep code, comments, docs and commit messages in English.

## Ground rules

- **Clean room.** Everything here is written from scratch from public standards
  (ISO 14229, ISO 15765). Never add code, names, report formats or data from any
  employer or OEM/supplier: no proprietary DIDs, routines, seed/key algorithms,
  ECU configs, bus captures or test results.
- **Honest README.** The feature table only marks ✅ what is implemented and tested.
  Hardware backends stay 🧪 until validated on real hardware.
- Do not reimplement ISO-TP or UDS encoding: build on `can-isotp` and `udsoncan`.
  Our value is the layer on top (MCP tools, claim/release, traffic classification,
  simulator, test plans).

## Workflow

- Zeus and Claude are the whole team: work directly on `main`, no PRs. Use a short-lived
  branch only for experiments.
- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`),
  ending with a `Co-Authored-By: Claude ... <noreply@anthropic.com>` trailer when Claude contributed.
- Before committing: `ruff check . && ruff format --check . && pytest`.
- Tests run on python-can's `virtual` bus; hardware tests must skip when the
  interface is absent. Update `CHANGELOG.md` under `[Unreleased]`.

## Layout

- `uds_mcp/core/` — `config.py` (ECU TOML → pydantic), `client.py` (`UdsClient`
  over udsoncan), `results.py` (structured responses incl. NRC names).
- `uds_mcp/interfaces/` — `open_bus()` maps our interface names to python-can.
- `uds_mcp/sim/` — `ecu.py` (`SimulatedEcu`: pure request → replies logic, injectable
  clock), `server.py` (`SimulatorServer`: ISO-TP thread on any bus), `__main__.py`
  (standalone), `demo_keys.py` (public demo key algorithm only).
  `demo_ecu.toml` is the demo ECU used by tests and `--interface sim` (generic values only),
  exposed as `uds_mcp.sim.DEMO_CONFIG`.
- `uds_mcp/server/app.py` — `build_server(client)`: MCP tools (hex-string inputs, `UdsResult`
  JSON out; bad input raises `ToolError`). Built on MCP SDK 2.x (`MCPServer`, not FastMCP).
- `uds_mcp/cli.py` — `open_session()` wires bus, simulator (for `sim`), client with keep-alive
  and server; `main()` runs stdio or streamable HTTP.
- `examples/demo_client.py` — scripted MCP session against the simulator.
- `uds_mcp/classify/`, `testplan/` — not implemented yet.

## Decisions

- 2026-10-27 — Core built on `udsoncan` + `can-isotp`: mature, MIT, lets us focus on MCP.
- 2026-10-27 — Every service returns a `UdsResult` (JSON-friendly, named NRCs) and never
  raises UDS exceptions, so MCP tools can return it as is.
- 2026-10-27 — Simulator behaviour lives in the same TOML as the ECU config (`[sim]`), so
  one file describes what the client expects and what the simulator answers.
- 2026-10-27 — Simulator first, MCP server next, as separate steps.
- 2026-10-27 — MCP tools take hex strings and return `UdsResult` JSON; a negative response
  is a normal result, only bad input is a tool error.
- 2026-10-27 — `UdsClient` runs a TesterPresent keep-alive (0x3E 80) outside the default
  session, because an LLM between tool calls easily exceeds S3.

## Next steps

- [ ] Claim/release access manager together with the HTTP transport.
- [ ] Validate the simulator on the Raspberry Pi 5 + Waveshare CAN FD HAT.
- [ ] Validate the server against real ECUs through PCAN, neoVI and Vector.
- [ ] Record a demo (GIF) of Claude driving the simulator for the README.
