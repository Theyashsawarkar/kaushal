# Changelog

Newest first. Releases are tags (`vX.Y.Z`) with `VERSION` in kaushal/__init__.py.

## Unreleased

- **A Skills page** on the website: every skill as a card, and a page for
  each with its full instructions and files, linked from every page's top
  bar. The README's skills list is now written from skills/, so it never
  misses one (`scripts/site.py`, around the shared site generator).

- **prasar** joins the MCP servers: agents can check, draft and propose
  posts for X and LinkedIn; every post waits for the user's approval.

- **A website**: theyashsawarkar.github.io/kaushal, built from the README,
  this changelog and seven decision records (docs/adr/) by the generator
  every Vayu tool shares; a how-it-works diagram; the README explains how
  kaushal works in Vayu.

## v0.1.0 -- 2026-10-28

- **Skills for every agent.** Skills are folders with a SKILL.md (the open
  Agent Skills format): Vayu's ship in `skills/`, yours go in
  `~/.config/kaushal/skills/` (`kaushal new NAME`). `kaushal sync` links
  them into Claude Code (every vesha profile shares them), Codex and the
  shared `~/.agents/skills`, which opencode and other agents read; agents
  that don't read skill folders get an index in their instructions file.
- **Tools for every agent.** `mcp.toml` lists Vayu's MCP servers (anumati,
  ekatva, sandesh, sangam); sync registers the installed ones with Claude
  Code (every profile, vesha's included), Codex, Gemini CLI and opencode.
  `{agent}` in args or env becomes the agent's name. Yours go in
  `~/.config/kaushal/mcp.toml`; `enabled = false` leaves one out.
- **Never touches what isn't its own**: what it added is recorded, a
  skill or server removed from kaushal is removed from the agents, a
  folder or server of yours with the same name is left alone, and
  `kaushal unsync` takes everything back. `kaushal doctor` checks it all.
- **Synced at login** (`kaushal.service`) and on install, so a new agent
  or account gets everything without asking.
- **The `dsr` skill**: the Daily Status Report, from the day's commits to
  an HTML table sent as a reply-all in the DSR thread, with scripts that
  collect the commits (`dsr_commits.py`) and check and render the
  timetable (`dsr_render.py`).
