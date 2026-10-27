# Contributing to UDS-MCP

Thanks for your interest. A few ground rules keep the project useful and safe to share.

## Ground rules

- **No proprietary data.** Do not submit OEM- or supplier-specific DIDs, routine IDs, seed/key algorithms, ECU configurations, bus captures or test results. Anything program-specific belongs in your own local config files (see `config/README.md`), never in this repository.
- Only publicly documented behaviour (ISO 14229, ISO 15765) is implemented here.
- Open an issue before starting a large change so the design can be discussed first.

## Development setup

```bash
git clone https://github.com/zeus-epardo/UDS-MCP.git
cd UDS-MCP
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Before pushing:

```bash
ruff check . && ruff format --check .
pytest
```

## Pull requests

- One topic per PR; keep them small.
- Add or update tests for behaviour changes. Hardware-dependent tests must be skipped automatically when the interface is not present.
- Update the README feature table if you change what is supported.
- Use conventional commit messages (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`).

## Reporting bugs

Include: interface and driver version, bitrate / CAN FD settings, the exact request sent, the raw response (or NRC) received, and whether the simulator reproduces it.
