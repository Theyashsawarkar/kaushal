# kaushal -- notes for AI agents (same as CLAUDE.md)

Skills and MCP tools for every AI agent on the machine: a store (`skills/`,
`mcp.toml`, and the user's `~/.config/kaushal/`) and `kaushal sync`, which
puts them into each agent's own config. Its own repo, pulled into Vayu
(github.com/Theyashsawarkar/vayu, whose CLAUDE.md "Plugins" rules apply);
it must work without Vayu.

- `bin/kaushal` entry; `kaushal/cli.py` commands; `kaushal/store.py` skills
  and servers; `kaushal/agents.py` one class per agent (where it keeps
  skills, servers, instructions).
- **Never clobber the user's config**: change only what kaushal added (state
  in ~/.local/state/kaushal/state.json) and marked blocks; keep every other
  key, server and line; write atomically, keeping file modes; validate a
  TOML before writing it. A same-named folder or server of the user's wins.
- A new agent: a class in agents.py (where its skills, MCP servers and
  global instructions live), a test in tests/test_kaushal.py, a row in the
  README table.
- A new skill: `skills/<name>/SKILL.md` with `name` (the folder's) and a
  `description` saying what it does *and when to use it*; helper scripts in
  its `scripts/`, standard library only, tested in tests/. Nothing personal
  in a skill (addresses, names, thread ids): those go in the user's config
  (`~/.config/kaushal/<skill>.toml`) or are found at run time.
- Test with a throwaway HOME (the tests do), never by syncing the user's
  real agents unless asked.
- Standard library only. `ruff check .` and `python -m unittest discover -s tests` must pass.
- Every change: a CHANGELOG.md entry; releases are tags with `VERSION` bumped.
- The website (docs/, GitHub Pages) is generated: after changing README.md, CHANGELOG.md or docs/adr/, run `python3 scripts/build-site.py` and commit docs/ (CI checks it). A significant design decision gets a new ADR in docs/adr/ (next number; supersede, never rewrite). scripts/build-site.py is shared by every Vayu tool: change it in one, copy it to all.
