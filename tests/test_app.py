"""kaushal's newer pieces: turning things off, testing a tool, taking back one agent, and the app starting."""
import os
import pty
import select
import subprocess
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_kaushal import Home  # noqa: E402

FAKE_MCP = '''#!/usr/bin/env python3
import json, sys
for line in sys.stdin:
    m = json.loads(line)
    if m.get("method") == "initialize":
        print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": {"serverInfo": {"name": "fake"}}}), flush=True)
    elif m.get("method") == "tools/list":
        print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": {"tools": [{"name": "ping"}, {"name": "pong"}]}}), flush=True)
'''


class Off(unittest.TestCase):
    def test_off_and_on_again(self):
        h = Home()
        os.makedirs(h.path(".claude"))
        h.run("sync")
        h.run("off", "sandesh")
        self.assertNotIn("sandesh", h.json(".claude.json")["mcpServers"])
        h.run("off", "dsr")
        self.assertFalse(os.path.lexists(h.path(".claude/skills/dsr")))
        self.assertIn("(off)", h.run().stdout)
        h.run("on", "sandesh")
        h.run("on", "dsr")
        self.assertIn("sandesh", h.json(".claude.json")["mcpServers"])
        self.assertTrue(os.path.islink(h.path(".claude/skills/dsr")))
        self.assertEqual(h.run("doctor").returncode, 0)

    def test_unknown_name(self):
        self.assertEqual(Home().run("off", "nope", ok=False).returncode, 1)


class Probe(unittest.TestCase):
    def run_py(self, h, code):
        env = {"HOME": h.dir, "PATH": f"{h.bin}:/usr/bin:/bin"}
        r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {ROOT!r})\n{code}"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_a_working_server(self):
        h = Home(commands=())
        with open(os.path.join(h.bin, "fakemcp"), "w") as f:
            f.write(FAKE_MCP)
        os.chmod(os.path.join(h.bin, "fakemcp"), 0o755)
        h.write(".config/kaushal/mcp.toml", '[servers.fake]\ncommand = "fakemcp"\n')
        out = self.run_py(h, "from kaushal import ops, store\n"
                             "s = [x for x in store.servers() if x.name == 'fake'][0]\nprint(ops.probe(s))")
        self.assertIn("True", out)
        self.assertIn("['ping', 'pong']", out)

    def test_a_server_that_never_answers(self):
        h = Home(commands=())
        with open(os.path.join(h.bin, "silent"), "w") as f:
            f.write("#!/bin/sh\nsleep 30\n")
        os.chmod(os.path.join(h.bin, "silent"), 0o755)
        h.write(".config/kaushal/mcp.toml", '[servers.silent]\ncommand = "silent"\n')
        out = self.run_py(h, "from kaushal import ops, store\n"
                             "s = [x for x in store.servers() if x.name == 'silent'][0]\nprint(ops.probe(s, timeout=1))")
        self.assertIn("False", out)
        self.assertIn("no answer", out)


class TakeBackOne(unittest.TestCase):
    def test_only_that_agent(self):
        h = Home()
        os.makedirs(h.path(".claude"))
        h.run("sync")
        out = Probe.run_py(self, h, "from kaushal import ops\nt = [t for t in ops.targets() if t.agent.key == 'claude'][0]\n"
                                    "ops.sync(take_back=True, only=t.key)")
        self.assertEqual(out, "")
        self.assertEqual(h.json(".claude.json")["mcpServers"], {})
        self.assertIn("sandesh", h.json(".config/opencode/opencode.json")["mcp"])   # the others keep theirs


class App(unittest.TestCase):
    def test_starts_draws_and_quits(self):
        h = Home()
        os.makedirs(h.path(".claude"))
        pid, fd = pty.fork()
        if pid == 0:
            os.environ.update({"HOME": h.dir, "PATH": f"{h.bin}:/usr/bin:/bin", "TERM": "xterm-256color",
                               "LINES": "40", "COLUMNS": "140"})
            os.execv(sys.executable, [sys.executable, os.path.join(ROOT, "bin", "kaushal"), "ui"])
        import fcntl
        import struct
        import termios
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 140, 0, 0))
        seen, end = b"", time.time() + 10
        while time.time() < end and not (b"Skills" in seen and b"dsr" in seen):
            if select.select([fd], [], [], 0.5)[0]:
                try:
                    seen += os.read(fd, 65536)
                except OSError:
                    break
        os.write(fd, b"3")
        time.sleep(0.3)
        os.write(fd, b"q")
        _, status = os.waitpid(pid, 0)
        os.close(fd)
        self.assertIn(b"Skills", seen)
        self.assertIn(b"dsr", seen)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)


if __name__ == "__main__":
    unittest.main()
