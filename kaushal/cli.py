"""kaushal's commands."""
import json
import os
import sys

from . import VERSION
from .agents import ALL, Agent
from .store import REPO, Server, config_dir, servers, skills, state_dir

HELP = f"""kaushal {VERSION}: skills and tools for every AI agent on this machine

  kaushal                 what there is: skills, MCP servers, agents
  kaushal sync [-n]       give every agent all of it (-n: only say what would change)
  kaushal doctor          check every agent has everything; exit 1 if not
  kaushal unsync          take back everything kaushal added
  kaushal new NAME        start a skill of your own in {os.path.join(config_dir(), "skills")}
  kaushal path [NAME]     where the skills (or one skill) live

Skills are folders with a SKILL.md (the open Agent Skills format): Vayu's
ship in {os.path.join(REPO, "skills")}, yours go in {os.path.join(config_dir(), "skills")}.
MCP servers come from mcp.toml there and in {config_dir()}."""


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


def short(path: str) -> str:
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home) else path


def present() -> list[Agent]:
    return [a for a in ALL if a.present()]


def wanted() -> tuple[list, list[Server], list[Server]]:
    """Skills, servers to register (installed), servers left out (not installed)."""
    all_servers = servers()
    return skills(), [s for s in all_servers if s.installed()], [s for s in all_servers if not s.installed()]


def run_sync(dry: bool, quiet: bool, take_back: bool = False) -> int:
    sk, sv, missing = wanted()
    if take_back:
        sk, sv = [], []
    state = load_state()
    failed = 0
    for agent in present():
        for target in agent.targets():
            key = f"{agent.key}:{target}"
            try:
                changes, owned = agent.sync(target, sk, sv, state.get(key, {}), dry)
            except (OSError, ValueError) as e:
                print(f"{agent.label} ({short(target)}): {e}", file=sys.stderr)
                failed += 1
                continue
            if not dry:
                state[key] = owned
            if changes or not quiet:
                print(f"{agent.label} ({short(target)}): " + ("; ".join(changes) if changes else "up to date"))
    if not dry:
        save_state({k: v for k, v in state.items() if any(v.values())})
    if missing and not quiet and not take_back:
        print("not installed, so not given to agents: " + ", ".join(f"{s.name} ({s.command})" for s in missing))
    return 1 if failed else 0


def doctor() -> int:
    sk, sv, missing = wanted()
    problems = [f"skill {s.name}: {p}" for s in sk for p in s.problems]
    problems += [f"server {s.name}: `{s.command}` isn't installed" for s in missing]
    agents = present()
    if not [a for a in agents if a.key != "agents"]:
        problems.append("no agent found (claude, codex, gemini, opencode)")
    state = load_state()
    notes = []
    for agent in agents:
        for target in agent.targets():
            changes, _ = agent.sync(target, sk, sv, state.get(f"{agent.key}:{target}", {}), dry=True)
            pending = [c for c in changes if not c.startswith("skip ")]
            # Yours winning over kaushal's is how it should be: a note, not a fault.
            notes += [f"{agent.label} ({short(target)}): {c}" for c in changes if c.startswith("skip ")]
            if pending:
                problems.append(f"{agent.label} ({short(target)}): out of date ({'; '.join(pending)}); run `kaushal sync`")
    for n in notes:
        print("· " + n)
    for p in problems:
        print("✗ " + p)
    if not problems:
        print(f"✓ {len(sk)} skill(s) and {len(sv)} server(s) in every agent: " + ", ".join(a.label for a in agents))
    return 1 if problems else 0


def overview() -> int:
    sk, sv, missing = wanted()
    print("Skills:")
    for s in sk:
        flag = f"  ✗ {'; '.join(s.problems)}" if s.problems else ""
        print(f"  {s.name:<16} {s.origin:<6} {s.description[:90]}{'…' if len(s.description) > 90 else ''}{flag}")
    if not sk:
        print("  (none)")
    print("MCP servers:")
    for s in sv + missing:
        note = "" if s in sv else "  (not installed)"
        print(f"  {s.name:<16} {s.command} {' '.join(s.args)}{note}")
    print("Agents: " + (", ".join(a.label for a in present()) or "none found"))
    return 0


SKELETON = """---
name: {name}
description: What this skill does and when an agent should use it (agents pick skills by this line).
---

# {name}

Steps the agent follows, in order. Put helper scripts in scripts/ and refer
to them by path relative to this file.
"""


def new(name: str) -> int:
    folder = os.path.join(config_dir(), "skills", name)
    if os.path.exists(folder):
        print(f"kaushal: {short(folder)} already exists", file=sys.stderr)
        return 1
    os.makedirs(folder)
    with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(SKELETON.format(name=name))
    print(f"{short(os.path.join(folder, 'SKILL.md'))}: edit it, then `kaushal sync`")
    return 0


def main(argv: list[str]) -> int:
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd in ("-h", "--help", "help"):
        print(HELP)
        return 0
    if cmd == "--version":
        print(VERSION)
        return 0
    if "--help" in rest or "-h" in rest:
        print(HELP)
        return 0
    if cmd == "":
        return overview()
    if cmd == "sync":
        return run_sync(dry="-n" in rest or "--dry-run" in rest, quiet="-q" in rest or "--quiet" in rest)
    if cmd == "doctor":
        return doctor()
    if cmd == "unsync":
        return run_sync(dry="-n" in rest, quiet=False, take_back=True)
    if cmd == "new" and len(rest) == 1:
        return new(rest[0])
    if cmd == "path":
        if rest:
            match = [s for s in skills() if s.name == rest[0]]
            if not match:
                print(f"kaushal: no skill {rest[0]}", file=sys.stderr)
                return 1
            print(match[0].path)
        else:
            print(os.path.join(REPO, "skills"))
            print(os.path.join(config_dir(), "skills"))
        return 0
    print(f"kaushal: unknown command {cmd!r}\n\n{HELP}", file=sys.stderr)
    return 2
