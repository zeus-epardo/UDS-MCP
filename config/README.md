# Configuration

Program-specific settings (request/response CAN IDs, DID catalogs, security-access
algorithms, routine definitions, classification rules) live here as **local files that
are not committed**. Files matching `*.local.*` and the `private/` folder are git-ignored.

Start from `example.toml` and copy it to `my-ecu.local.toml`.
