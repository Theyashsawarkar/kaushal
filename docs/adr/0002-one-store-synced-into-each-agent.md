# 2. One store, written into each agent's own config

**Status:** Accepted  
**Date:** 2026-10-28

## Context

Every agent already has a way to load skills, MCP servers and global instructions, each in its own place and format: Claude Code reads `~/.claude/skills` and `~/.claude.json`, Codex `~/.codex/config.toml` and `AGENTS.md`, opencode `opencode.json` and `~/.agents/skills`, Gemini CLI `settings.json` and `GEMINI.md`. Keeping the same skills and tools in all of them by hand means copies that drift, and a new agent or account that has none of them.

kaushal could instead sit between the agents and the tools (one proxy MCP server, or a wrapper that injects things at start-up), but every agent is started from many places (terminals, editors, desktop apps), and a proxy is one more process to break.

## Decision

Skills and servers live in one store (the repository's `skills/` and `mcp.toml`, plus the user's `~/.config/kaushal/`). `kaushal sync` writes them into each agent's own configuration, in that agent's own format, through one small class per agent (`kaushal/agents.py`). Skills are linked, not copied. Agents that don't read skill folders get a short index (each skill's description and the path of its SKILL.md) in their instructions file.

## Consequences

- Each agent loads everything the way it always does, however it is started; nothing runs between an agent and its tools.
- Editing a skill takes effect at once everywhere (the agents read the linked folder); adding or removing one takes a sync.
- Supporting a new agent is one class: where its skills, servers and instructions live.
