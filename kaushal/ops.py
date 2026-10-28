"""What kaushal does, as data: the command line prints it, the app shows it."""
import json
import os
import select
import subprocess
import time
from dataclasses import dataclass, field

from . import VERSION
from .agents import ALL, Agent
from .store import Server, Skill, off, servers, skills, state_dir, which


def short(path: str) -> str:
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home) else path


# ------------------------------------------------------------------ state

def state_file() -> str:
    return os.path.join(state_dir(), "state.json")


def load_state() -> dict:
    try:
        with open(state_file(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    os.makedirs(state_dir(), exist_ok=True)
    tmp = state_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, state_file())


def synced_at() -> float | None:
    try:
        return os.path.getmtime(state_file())
    except OSError:
        return None


# ------------------------------------------------------------------ what to give

@dataclass
class Wanted:
    skills: list[Skill]          # valid and on: given to agents
    servers: list[Server]        # installed and on: given to agents
    missing: list[Server]        # on but not installed
    all_skills: list[Skill]      # everything, off and broken ones too
    all_servers: list[Server]
    off: dict[str, set[str]]


def wanted() -> Wanted:
    o = off()
    sk, sv = skills(), servers()
    return Wanted([s for s in sk if not s.problems and s.name not in o["skills"]],
                  [s for s in sv if s.installed() and s.name not in o["servers"]],
                  [s for s in sv if not s.installed() and s.name not in o["servers"]],
                  sk, sv, o)


# ------------------------------------------------------------------ agents

@dataclass
class Target:
    agent: Agent
    path: str

    @property
    def key(self) -> str:
        return f"{self.agent.key}:{self.path}"

    @property
    def where(self) -> str:
        vesha = os.path.join(os.path.expanduser("~"), ".local/state/vesha/profiles") + "/"
        return "vesha: " + self.path[len(vesha):] if self.path.startswith(vesha) else short(self.path)


def targets() -> list[Target]:
    return [Target(a, t) for a in ALL if a.present() for t in a.targets()]


@dataclass
class Result:
    target: Target
    changes: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def pending(self) -> list[str]:
        """Changes a sync would make (skips are the user's own things winning, not work to do)."""
        return [c for c in self.changes if not c.startswith("skip ")]


def sync(dry: bool = False, take_back: bool = False, only: str | None = None) -> tuple[list[Result], Wanted]:
    """Gives every agent (or only the target whose key is `only`) what kaushal has; take_back removes it."""
    w = wanted()
    sk, sv = ([], []) if take_back else (w.skills, w.servers)
    state = load_state()
    out = []
    for t in targets():
        if only and t.key != only:
            continue
        r = Result(t)
        try:
            r.changes, owned = t.agent.sync(t.path, sk, sv, state.get(t.key, {}), dry)
            if not dry:
                state[t.key] = owned
        except (OSError, ValueError) as e:
            r.error = str(e)
        out.append(r)
    if not dry:
        save_state({k: v for k, v in state.items() if any(v.values())})
    return out, w


def diagnose() -> tuple[list[str], list[str], str]:
    """(notes, problems, summary): what `kaushal doctor` reports."""
    results, w = sync(dry=True)
    problems = [f"skill {s.name}: {p}" for s in w.all_skills for p in s.problems]
    problems += [f"server {s.name}: `{s.command}` isn't installed" for s in w.missing]
    real = [r for r in results if r.target.agent.key != "agents"]
    if not real:
        problems.append("no agent found (claude, codex, gemini, opencode)")
    notes = []
    for r in results:
        label = f"{r.target.agent.label} ({short(r.target.path)})"
        if r.error:
            problems.append(f"{label}: {r.error}")
        # Yours winning over kaushal's is how it should be: a note, not a fault.
        notes += [f"{label}: {c}" for c in r.changes if c.startswith("skip ")]
        if r.pending:
            problems.append(f"{label}: out of date ({'; '.join(r.pending)}); run `kaushal sync`")
    agents = sorted({r.target.agent.label for r in results}, key=[a.label for a in ALL].index)
    summary = f"{len(w.skills)} skill(s) and {len(w.servers)} server(s) in every agent: " + ", ".join(agents)
    return notes, problems, summary


# ------------------------------------------------------------------ testing a server

def probe(server: Server, timeout: float = 15.0) -> tuple[bool, str, list[str]]:
    """Starts the MCP server, does the handshake and lists its tools: (ok, message, tool names)."""
    cmd, args, env = server.for_agent("kaushal")
    path = which(cmd)
    if not path:
        return False, f"`{cmd}` isn't installed", []
    started = time.monotonic()
    try:
        p = subprocess.Popen([path, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             env={**os.environ, **env}, text=True, bufsize=1)
    except OSError as e:
        return False, str(e), []
    try:
        def send(msg):
            p.stdin.write(json.dumps(msg) + "\n")
            p.stdin.flush()

        def answer(want_id):
            while True:
                left = timeout - (time.monotonic() - started)
                if left <= 0 or not select.select([p.stdout], [], [], left)[0]:
                    raise TimeoutError(f"no answer in {timeout:.0f} s")
                line = p.stdout.readline()
                if not line:
                    raise ConnectionError("it exited")
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == want_id:
                    if "error" in msg:
                        raise ConnectionError(msg["error"].get("message", "error"))
                    return msg.get("result") or {}

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "kaushal", "version": VERSION}}})
        info = answer(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = [t.get("name", "?") for t in answer(2).get("tools", [])]
        name = (info.get("serverInfo") or {}).get("name", server.name)
        return True, f"{name} answered in {time.monotonic() - started:.1f} s", tools
    except (TimeoutError, ConnectionError, OSError, ValueError) as e:
        return False, str(e), []
    finally:
        try:
            p.kill()
            p.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
