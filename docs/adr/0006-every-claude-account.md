# 6. Every Claude Code account gets the tools

**Status:** Accepted  
**Date:** 2026-10-28

## Context

vesha, Vayu's Claude Code account manager, keeps each account in its own profile (`CLAUDE_CONFIG_DIR`). It links the shared parts (settings, skills, instructions) from `~/.claude` into every profile, but MCP servers live in each profile's own `.claude.json`, beside its login, so they can't be shared that way. A second account had none of the tools the first one had.

## Decision

kaushal treats every Claude Code profile as a place to sync: `~/.claude` (whose servers are in `~/.claude.json`), `$CLAUDE_CONFIG_DIR` if set, and every vesha profile. It writes the profile's `.claude.json` directly rather than through `claude mcp add`, because `claude` may be vesha's wrapper, which picks a profile by folder.

## Consequences

- Every account has every tool and skill, whichever one a session runs on.
- A new vesha account gets them at the next sync (ADR 5).

vesha: https://github.com/Theyashsawarkar/vesha
