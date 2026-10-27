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
- `tests/fake_ecu.py` — scripted ECU for the core tests, to be replaced by the simulator.
- `uds_mcp/server/`, `classify/`, `testplan/`, `sim/` — not implemented yet.

## Decisions

- 2026-10-27 — Core built on `udsoncan` + `can-isotp`: mature, MIT, lets us focus on MCP.
- 2026-10-27 — Every service returns a `UdsResult` (JSON-friendly, named NRCs) and never
  raises UDS exceptions, so MCP tools can return it as is.

## Next steps

- [ ] Decide: simulator config in the ECU TOML (`[sim]` section) or in a separate file.
- [ ] Decide: simulator and MCP server as separate steps, or together up to the demo.
- [ ] Software simulator (`uds_mcp/sim/`) that replaces `tests/fake_ecu.py`; same code
      later runs on a Raspberry Pi 5 over SocketCAN.
- [ ] MCP server with FastMCP (stdio) and the first tools; `--interface sim` starts the
      simulator so the demo works without hardware.
- [ ] Claim/release access manager together with the HTTP transport.
