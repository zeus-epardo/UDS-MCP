# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- ECU simulator (`uds_mcp.sim`) driven by a `[sim]` config section: sessions with S3
  timeout, seed/key security access with attempt limit, session- and security-gated DIDs
  and routines, DTC read/clear and response-pending (0x78). Runs on any python-can bus,
  standalone via `python -m uds_mcp.sim`. Demo ECU in `config/sim.toml`.
- Core tests now run against the simulator.
- UDS client core (`uds_mcp.core.UdsClient`) on top of udsoncan and can-isotp: services
  0x10, 0x11, 0x14, 0x19, 0x22, 0x27, 0x2E, 0x31, 0x3E and raw requests, returning structured
  `UdsResult` objects with decoded NRC names.
- ECU configuration loader (`load_config`) for TOML files with DIDs, timing and security levels.
- `open_bus()` mapping interface names to python-can backends (virtual bus for `sim`).
- `CLAUDE.md` with project context and ground rules.
- Repository scaffold: package layout, CLI entry point, CI, contribution guidelines.
