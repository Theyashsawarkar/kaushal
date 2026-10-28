# 5. Sync at login and on install

**Status:** Accepted  
**Date:** 2026-10-28

## Context

Skills and tools should be in every agent in every session without the user doing anything. What changes the picture: a new agent installed, a new Claude Code account (vesha profile), a tool installed or removed, a skill added. Watching every agent's start would need a wrapper around each of them (ADR 2 rejects that).

## Decision

`kaushal sync` runs:

- at every login, from `kaushal.service` (a oneshot user unit; Vayu starts it with the session's other units);
- on install and on every update, from `install.sh` and kosha's `reload`;
- whenever the user wants (`kaushal sync`), and `kaushal doctor` says when one is due.

## Consequences

- A new agent or account has everything by the next login at the latest; a new tool from the moment kosha installs it.
- Agent sessions already running keep the configuration they started with, as they always do.
