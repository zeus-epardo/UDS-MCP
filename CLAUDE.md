# CLAUDE.md

Context for Claude sessions working on UDS-MCP.

## Team

UDS-MCP is built by Zeus Epardo together with Claude. It is free, MIT-licensed and
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

- Work on a feature branch; one topic per PR.
- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`),
  ending with `Co-Authored-By: Claude <noreply@anthropic.com>` when Claude contributed.
- Before committing: `ruff check . && ruff format --check . && pytest`.
- Tests run on python-can's `virtual` bus; hardware tests must skip when the
  interface is absent. Update `CHANGELOG.md` under `[Unreleased]`.

## Layout

- `uds_mcp/core/` — `config.py` (ECU TOML → pydantic), `client.py` (`UdsClient`
  over udsoncan), `results.py` (structured responses incl. NRC names).
- `uds_mcp/interfaces/` — `open_bus()` maps our interface names to python-can.
- `uds_mcp/server/`, `classify/`, `testplan/`, `sim/` — not implemented yet.
