# kaushal -- notes for agents

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
- The website (docs/, GitHub Pages) is generated: after changing README.md, CHANGELOG.md, docs/adr/ or a skill, run `python3 scripts/site.py` (never build-site.py alone: it would drop the skill pages) and commit README.md and docs/ (CI checks both). The README's skills list is written from skills/ between its `<!-- skills -->` markers; don't edit it by hand. A significant design decision gets a new ADR in docs/adr/ (next number; supersede, never rewrite). scripts/build-site.py is shared by every Vayu tool: change it in one, copy it to all.
- The app is `kaushal/tui.py` (curses, the same helpers as vesha's switcher); what it does lives in `kaushal/ops.py`, shared with the CLI. Every key has a `# keybind: Kaushal/app | <keys> | <Verb> <object>` line in tui.py (Vayu's keybinding search reads them); the line, the `?` sheet (HELP) and the README's key table must agree. Test it on a throwaway tmux server with a throwaway HOME, never the user's agents.
