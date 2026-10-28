# 4. Change only what kaushal added

**Status:** Accepted  
**Date:** 2026-10-28

## Context

The files kaushal writes are the user's: `~/.claude.json` holds Claude Code's whole state, `config.toml` the user's Codex settings, and they may already have their own skills and MCP servers, some with the same names as kaushal's. A sync that rewrote those files, or removed what it didn't recognise, would destroy work.

## Decision

- kaushal records what it added to each agent (`~/.local/state/kaushal/state.json`) and only ever changes or removes that.
- In text files it writes only inside its own marked block; in JSON files only its own keys.
- A skill folder or server of the user's with the same name wins; one identical to kaushal's is adopted.
- Files are written atomically, keep their permissions, and a TOML file is parsed before it's written.
- `kaushal unsync` takes back everything it added.

## Consequences

- Syncing is safe to run any time, as often as wanted, and changes nothing when nothing changed.
- Removing a skill or server from kaushal removes it from every agent on the next sync.
- A user's own server of the same name means that agent keeps theirs; `kaushal doctor` notes it rather than failing.
