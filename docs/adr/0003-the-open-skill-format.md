# 3. Skills in the open Agent Skills format

**Status:** Accepted  
**Date:** 2026-10-28

## Context

A skill could be written for one agent (Claude Code's skills, Codex's prompts, opencode's commands), but the point of kaushal is that every agent has every skill. Claude Code, Codex and opencode all read the open [Agent Skills](https://agentskills.io) format: a folder with a `SKILL.md` whose front matter has a `name` and a `description`, and whose body is the instructions; `~/.agents/skills` is the folder the convention shares between agents.

## Decision

A kaushal skill is an Agent Skills folder: `name` equal to the folder's name, a `description` that says what it does and when to use it (agents choose skills by it), and helper scripts in `scripts/`, standard-library Python so any agent can run them. Nothing personal goes into a skill: addresses, names, thread ids and paths are found at run time or read from the user's `~/.config/kaushal/<skill>.toml`.

## Consequences

- One file works in every agent; agents without native support read it through the index (ADR 2).
- Vayu's skills can be public: the `dsr` skill finds the user's DSR thread in their sent mail instead of naming it.
- `kaushal doctor` checks every skill's front matter.
