# 7. Standard library only

**Status:** Accepted  
**Date:** 2026-10-28

## Context

kaushal runs at login, before anything else, on machines with nothing installed but Python; its skills' scripts run inside whatever agent the user has. A dependency would need installing first, and could break the login sync.

## Decision

kaushal and every skill's scripts use Python's standard library only (3.11, for `tomllib`). TOML is written by hand in kaushal's marked block and checked with `tomllib` before saving (ADR 4).

## Consequences

- `git clone` and run: nothing to install, nothing to keep up to date.
- Formats a library would handle (TOML writing, YAML front matter) are handled for the small subset kaushal needs.
