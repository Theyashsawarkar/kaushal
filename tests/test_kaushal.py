"""kaushal end to end in a throwaway HOME (fake agents and tools on PATH), and its pieces."""
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kaushal.agents import BEGIN, END, merge_servers, replace_block  # noqa: E402
from kaushal.store import frontmatter  # noqa: E402


class Home:
    """A throwaway HOME with fake `claude`, `codex`, `opencode` and tool commands on PATH."""

    def __init__(self, commands=("claude", "codex", "opencode", "sandesh", "sangam", "ekatva", "anumati")):
        self.dir = tempfile.mkdtemp()
        self.bin = os.path.join(self.dir, "fakebin")
        os.makedirs(self.bin)
        for c in commands:
            p = os.path.join(self.bin, c)
            with open(p, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(p, 0o755)

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def run(self, *args, ok=True):
        env = {"HOME": self.dir, "PATH": f"{self.bin}:/usr/bin:/bin"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "kaushal"), *args],
                           capture_output=True, text=True, env=env)
        if ok and r.returncode != 0:
            raise AssertionError(f"kaushal {' '.join(args)} failed:\n{r.stdout}{r.stderr}")
        return r

    def json(self, *parts):
        with open(self.path(*parts)) as f:
            return json.load(f)

    def text(self, *parts):
        with open(self.path(*parts)) as f:
            return f.read()

    def write(self, rel, text):
        p = self.path(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)


class Sync(unittest.TestCase):
    def test_every_agent_gets_skills_and_servers(self):
        h = Home()
        os.makedirs(h.path(".claude"))
        h.write(".claude.json", json.dumps({"numStartups": 7, "mcpServers": {"mine": {"command": "x"}}}))
        h.run("sync")
        # Claude: skills linked, servers added, the user's own settings and server kept.
        self.assertTrue(os.path.islink(h.path(".claude/skills/dsr")))
        cfg = h.json(".claude.json")
        self.assertEqual(cfg["numStartups"], 7)
        self.assertIn("mine", cfg["mcpServers"])
        self.assertEqual(cfg["mcpServers"]["sandesh"], {"type": "stdio", "command": "sandesh", "args": ["mcp"], "env": {}})
        self.assertEqual(cfg["mcpServers"]["ekatva"]["env"], {"EKATVA_AGENT": "claude"})
        # The shared folder of the Agent Skills convention.
        self.assertTrue(os.path.islink(h.path(".agents/skills/dsr")))
        # Codex: a valid config.toml with the servers, skills, an index.
        codex = tomllib.loads(h.text(".codex/config.toml"))
        self.assertEqual(codex["mcp_servers"]["ekatva"]["env"], {"EKATVA_AGENT": "codex"})
        self.assertTrue(os.path.islink(h.path(".codex/skills/dsr")))
        self.assertIn("`dsr`", h.text(".codex/AGENTS.md"))
        # opencode: servers in its format; tools listed, skills not (it reads ~/.agents/skills).
        oc = h.json(".config/opencode/opencode.json")
        self.assertEqual(oc["mcp"]["sangam"], {"type": "local", "command": ["sangam", "mcp"], "environment": {}, "enabled": True})
        agents_md = h.text(".config/opencode/AGENTS.md")
        self.assertIn("`sangam`", agents_md)
        self.assertNotIn("`dsr`", agents_md)
        # Gemini isn't installed: nothing written for it.
        self.assertFalse(os.path.exists(h.path(".gemini")))
        # A second sync changes nothing, and doctor agrees.
        self.assertNotIn("add server", h.run("sync").stdout)
        self.assertEqual(h.run("doctor").returncode, 0)

    def test_vesha_profiles_get_servers_too(self):
        h = Home()
        os.makedirs(h.path(".claude/skills"))
        prof = h.path(".local/state/vesha/profiles/work")
        os.makedirs(prof)
        os.symlink(h.path(".claude/skills"), os.path.join(prof, "skills"))
        h.write(".local/state/vesha/profiles/work/.claude.json", "{}")
        h.run("sync")
        self.assertIn("sandesh", h.json(".local/state/vesha/profiles/work/.claude.json")["mcpServers"])

    def test_missing_tools_are_left_out(self):
        h = Home(commands=("claude",))
        os.makedirs(h.path(".claude"))
        out = h.run("sync").stdout
        self.assertIn("not installed", out)
        self.assertFalse(os.path.exists(h.path(".claude.json")))  # nothing to write, nothing written
        self.assertEqual(h.run("doctor", ok=False).returncode, 1)

    def test_your_skills_and_overrides(self):
        h = Home()
        os.makedirs(h.path(".claude"))
        h.write(".config/kaushal/mcp.toml", '[servers.sangam]\nenabled = false\n\n[servers.mine]\ncommand = "sandesh"\nargs = ["x"]\n')
        h.run("new", "notes")
        h.run("sync")
        servers = h.json(".claude.json")["mcpServers"]
        self.assertNotIn("sangam", servers)
        self.assertEqual(servers["mine"]["args"], ["x"])
        self.assertTrue(os.path.islink(h.path(".claude/skills/notes")))

    def test_never_touches_your_own_skill_folder(self):
        h = Home()
        os.makedirs(h.path(".claude/skills/dsr"))
        out = h.run("sync").stdout
        self.assertIn("is your own folder", out)
        self.assertFalse(os.path.islink(h.path(".claude/skills/dsr")))

    def test_your_own_server_wins_and_an_identical_one_is_adopted(self):
        h = Home()
        os.makedirs(h.path(".claude"))
        same = {"type": "stdio", "command": "sandesh", "args": ["mcp"], "env": {}}
        h.write(".claude.json", json.dumps({"mcpServers": {"sangam": {"command": "my-sangam"}, "sandesh": same}}))
        self.assertIn("skip server sangam", h.run("sync").stdout)
        self.assertEqual(h.json(".claude.json")["mcpServers"]["sangam"], {"command": "my-sangam"})
        h.run("unsync")
        servers = h.json(".claude.json")["mcpServers"]
        self.assertEqual(servers, {"sangam": {"command": "my-sangam"}})  # adopted sandesh went, theirs stayed

    def test_codex_server_you_defined_wins(self):
        h = Home()
        h.write(".codex/config.toml", 'model = "x"\n\n[mcp_servers.sandesh]\ncommand = "my-sandesh"\n')
        h.run("sync")
        codex = tomllib.loads(h.text(".codex/config.toml"))
        self.assertEqual(codex["mcp_servers"]["sandesh"]["command"], "my-sandesh")
        self.assertEqual(codex["model"], "x")

    def test_unsync_takes_everything_back(self):
        h = Home()
        os.makedirs(h.path(".claude"))
        h.write(".codex/AGENTS.md", "# my notes\n")
        h.run("sync")
        h.run("unsync")
        self.assertFalse(os.path.lexists(h.path(".claude/skills/dsr")))
        self.assertFalse(os.path.lexists(h.path(".agents/skills/dsr")))
        self.assertEqual(h.json(".claude.json")["mcpServers"], {})
        self.assertEqual(h.text(".codex/AGENTS.md"), "# my notes\n")
        self.assertNotIn("mcp_servers", tomllib.loads(h.text(".codex/config.toml")))

    def test_dry_run_writes_nothing(self):
        h = Home()
        os.makedirs(h.path(".claude"))
        self.assertIn("add server", h.run("sync", "-n").stdout)
        self.assertFalse(os.path.exists(h.path(".claude.json")))

    def test_commands_answer(self):
        h = Home()
        self.assertIn("dsr", h.run().stdout)
        self.assertIn("kaushal sync", h.run("help").stdout)
        self.assertTrue(h.run("path", "dsr").stdout.strip().endswith("skills/dsr"))


class Pieces(unittest.TestCase):
    def test_frontmatter(self):
        meta = frontmatter("---\nname: dsr\ndescription: >\n  Write the\n  report.\n---\n# x\n")
        self.assertEqual(meta, {"name": "dsr", "description": "Write the report."})
        self.assertEqual(frontmatter("# no frontmatter"), {})

    def test_block_replaces_appends_and_removes(self):
        text = replace_block("# mine\n", BEGIN, END, "one")
        self.assertTrue(text.startswith("# mine\n\n" + BEGIN))
        again = replace_block(text, BEGIN, END, "two")
        self.assertEqual(again.count(BEGIN), 1)
        self.assertIn("two", again)
        self.assertEqual(replace_block(again, BEGIN, END, ""), "# mine\n")

    def test_merge_servers_only_removes_its_own(self):
        table = {"theirs": {"command": "a"}, "old": {"command": "b"}}
        changes, owned = merge_servers(table, {"new": {"command": "c"}}, ["old"])
        self.assertEqual(sorted(table), ["new", "theirs"])
        self.assertEqual(owned, ["new"])
        self.assertEqual(len(changes), 2)

    def test_every_vayu_skill_is_valid(self):
        from kaushal.store import load_skill
        root = os.path.join(ROOT, "skills")
        for name in os.listdir(root):
            s = load_skill("vayu", os.path.join(root, name))
            self.assertEqual(s.problems, [], name)


if __name__ == "__main__":
    unittest.main()
