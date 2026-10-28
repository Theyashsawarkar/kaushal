"""Each agent kaushal knows: where it keeps skills, MCP servers and global
instructions, and how to put ours there without touching anything else.

  Claude Code  skills linked into <config>/skills; servers in the profile's
               .claude.json (~/.claude.json for ~/.claude); every vesha
               profile too. Reads skills itself: no instructions block.
  Codex        skills linked into ~/.codex/skills; servers in a marked
               block of ~/.codex/config.toml; index in ~/.codex/AGENTS.md
  Gemini CLI   servers in ~/.gemini/settings.json; index in GEMINI.md
  opencode     servers in ~/.config/opencode/opencode.json; tools in its
               AGENTS.md (it reads skills from ~/.agents/skills itself)
  any agent    skills linked into ~/.agents/skills, the shared folder of the
               open Agent Skills convention

An agent counts when its command is on PATH or its folder exists. What
kaushal added is recorded (state.json), so a skill or server removed from
kaushal is removed from the agents too, and nothing of yours is touched.
"""
import glob
import json
import os
import re
import tomllib

from .store import HOME, Server, Skill, which

BEGIN = "<!-- >>> kaushal: written by `kaushal sync`; change the skills, not this block >>> -->"
END = "<!-- <<< kaushal <<< -->"
TOML_BEGIN = "# >>> kaushal: written by `kaushal sync` >>>"
TOML_END = "# <<< kaushal <<<"


# ------------------------------------------------------------------ files

def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def write_text(path: str, text: str) -> None:
    """Atomically, keeping the file's mode (0600 config files stay 0600)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = os.stat(path).st_mode & 0o777 if os.path.exists(path) else 0o644
    tmp = f"{path}.kaushal-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def read_json(path: str) -> dict:
    text = read_text(path)
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a JSON object")
    return data


def write_json(path: str, data: dict) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def replace_block(text: str, begin: str, end: str, body: str) -> str:
    """Puts `body` between the markers (appending them if absent); an empty body removes the block."""
    pat = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.S)
    block = f"{begin}\n{body.rstrip()}\n{end}\n" if body.strip() else ""
    if pat.search(text):
        out = pat.sub(lambda _: block, text, count=1)
        if not block:  # taken out: no blank lines left where it was
            out = out.rstrip("\n") + "\n" if out.strip() else ""
    elif block:
        out = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block
    else:
        out = text
    return out


# ------------------------------------------------------------------ pieces

def index(skills: list[Skill], servers: list[Server]) -> str:
    """The instructions block for agents that don't read SKILL.md folders themselves."""
    if not skills and not servers:
        return ""
    lines = ["## Vayu: your tools and skills", ""]
    if servers:
        lines += ["Tools (MCP servers, connected in every session):", ""]
        lines += [f"- `{s.name}`: {s.description}" for s in servers]
        lines.append("")
    if skills:
        lines += ["Skills: step-by-step instructions for particular jobs. When a request matches one,",
                  "read its SKILL.md before doing anything else and follow it.", ""]
        lines += [f"- `{s.name}` ({s.file}): {s.description}" for s in skills]
    return "\n".join(lines)


def link_skills(skills_dir: str, skills: list[Skill], owned: list[str], dry: bool) -> tuple[list[str], list[str]]:
    """Links each skill into `skills_dir`; unlinks the ones kaushal added that are gone. (changes, now owned)"""
    changes, now = [], []
    want = {s.name: s.path for s in skills if not s.problems}
    for name, src in want.items():
        dst = os.path.join(skills_dir, name)
        if os.path.islink(dst):
            if os.path.realpath(dst) == os.path.realpath(src):
                now.append(name)
                continue
            if name not in owned:
                changes.append(f"skip skill {name}: {dst} is someone else's link")
                continue
        elif os.path.exists(dst):
            changes.append(f"skip skill {name}: {dst} is your own folder")
            continue
        changes.append(f"link skill {name}")
        now.append(name)
        if not dry:
            os.makedirs(skills_dir, exist_ok=True)
            if os.path.islink(dst):
                os.unlink(dst)
            os.symlink(src, dst)
    for name in owned:
        dst = os.path.join(skills_dir, name)
        if name not in want and os.path.islink(dst):
            changes.append(f"unlink skill {name}")
            if not dry:
                os.unlink(dst)
    return changes, now


def merge_servers(table: dict, wanted: dict[str, dict], owned: list[str]) -> tuple[list[str], list[str]]:
    """Sets `table[name]` for each wanted server, drops owned ones no longer wanted. (changes, now owned)"""
    changes, now = [], []
    for name, spec in wanted.items():
        if name in table and name not in owned and table[name] != spec:
            # Set up by the user (or another tool), differently: theirs wins.
            changes.append(f"skip server {name}: you have your own")
            continue
        now.append(name)
        if table.get(name) != spec:
            changes.append(f"{'update' if name in table else 'add'} server {name}")
            table[name] = spec
    for name in owned:
        if name not in wanted and name in table:
            changes.append(f"remove server {name}")
            del table[name]
    return changes, sorted(now)


# ------------------------------------------------------------------ agents

class Agent:
    key = ""
    label = ""
    command = ""
    home = ""

    def present(self) -> bool:
        return which(self.command) is not None or os.path.isdir(self.home)

    def targets(self) -> list[str]:
        """Places synced separately (Claude: one per profile)."""
        return [self.home]

    def sync(self, target: str, skills: list[Skill], servers: list[Server], owned: dict, dry: bool) -> tuple[list[str], dict]:
        raise NotImplementedError

    def server_spec(self, s: Server) -> dict:
        cmd, args, env = s.for_agent(self.key)
        return {"command": cmd, "args": args, "env": env}


class Shared(Agent):
    """~/.agents/skills: the folder agents following the Agent Skills convention read."""

    key, label = "agents", "Shared skills"
    home = os.path.join(HOME, ".agents")

    def present(self) -> bool:
        return True

    def sync(self, target, skills, servers, owned, dry):
        changes, sk = link_skills(os.path.join(target, "skills"), skills, owned.get("skills", []), dry)
        return changes, {"skills": sk}


class Claude(Agent):
    key, label, command = "claude", "Claude Code", "claude"
    home = os.path.join(HOME, ".claude")

    def targets(self) -> list[str]:
        out = [self.home]
        env = os.environ.get("CLAUDE_CONFIG_DIR")
        if env and os.path.realpath(env) != os.path.realpath(self.home):
            out.append(env)
        # vesha keeps every other account in a profile of its own.
        out += sorted(p.rstrip("/") for p in glob.glob(os.path.join(HOME, ".local/state/vesha/profiles/*/")))
        return out

    def config_file(self, target: str) -> str:
        # The default profile keeps its settings beside the folder, not in it.
        return os.path.join(HOME, ".claude.json") if target == self.home else os.path.join(target, ".claude.json")

    def server_spec(self, s: Server) -> dict:
        return {"type": "stdio", **super().server_spec(s)}

    def sync(self, target, skills, servers, owned, dry):
        changes, sk = link_skills(os.path.join(target, "skills"), skills, owned.get("skills", []), dry)
        path = self.config_file(target)
        data = read_json(path)
        table = data.setdefault("mcpServers", {})
        more, mc = merge_servers(table, {s.name: self.server_spec(s) for s in servers}, owned.get("mcp", []))
        if more and not dry:
            write_json(path, data)
        return changes + more, {"skills": sk, "mcp": mc}


class Codex(Agent):
    key, label, command = "codex", "Codex", "codex"
    home = os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")

    def sync(self, target, skills, servers, owned, dry):
        changes, sk = link_skills(os.path.join(target, "skills"), skills, owned.get("skills", []), dry)
        path = os.path.join(target, "config.toml")
        text = read_text(path)
        outside = tomllib.loads(replace_block(text, TOML_BEGIN, TOML_END, ""))
        theirs = set((outside.get("mcp_servers") or {}).keys())
        body = []
        for s in servers:
            if s.name in theirs:
                changes.append(f"skip server {s.name}: config.toml already has one")
                continue
            spec = self.server_spec(s)
            body.append(f"[mcp_servers.{s.name}]\ncommand = {json.dumps(spec['command'])}\n"
                        f"args = [{', '.join(json.dumps(a) for a in spec['args'])}]")
            if spec["env"]:
                body[-1] += "\nenv = { " + ", ".join(f"{k} = {json.dumps(v)}" for k, v in spec["env"].items()) + " }"
        new = replace_block(text, TOML_BEGIN, TOML_END, "\n\n".join(body))
        tomllib.loads(new)  # never write a config Codex can't read
        if new != text:
            changes.append("write servers to config.toml")
            if not dry:
                write_text(path, new)
        changes += instructions(os.path.join(target, "AGENTS.md"), skills, servers, dry)
        return changes, {"skills": sk, "mcp": [s.name for s in servers if s.name not in theirs]}


class Gemini(Agent):
    key, label, command = "gemini", "Gemini CLI", "gemini"
    home = os.path.join(HOME, ".gemini")

    def sync(self, target, skills, servers, owned, dry):
        path = os.path.join(target, "settings.json")
        data = read_json(path)
        changes, mc = merge_servers(data.setdefault("mcpServers", {}),
                                    {s.name: self.server_spec(s) for s in servers}, owned.get("mcp", []))
        if changes and not dry:
            write_json(path, data)
        changes += instructions(os.path.join(target, "GEMINI.md"), skills, servers, dry)
        return changes, {"mcp": mc}


class OpenCode(Agent):
    key, label, command = "opencode", "opencode", "opencode"
    home = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "opencode")

    def server_spec(self, s: Server) -> dict:
        cmd, args, env = s.for_agent(self.key)
        return {"type": "local", "command": [cmd, *args], "environment": env, "enabled": True}

    def sync(self, target, skills, servers, owned, dry):
        path = os.path.join(target, "opencode.json")
        data = read_json(path) or {"$schema": "https://opencode.ai/config.json"}
        changes, mc = merge_servers(data.setdefault("mcp", {}),
                                    {s.name: self.server_spec(s) for s in servers}, owned.get("mcp", []))
        if changes and not dry:
            write_json(path, data)
        # It finds the skills in ~/.agents/skills: list only the tools.
        changes += instructions(os.path.join(target, "AGENTS.md"), [], servers, dry)
        return changes, {"mcp": mc}


def instructions(path: str, skills: list[Skill], servers: list[Server], dry: bool) -> list[str]:
    text = read_text(path)
    new = replace_block(text, BEGIN, END, index([s for s in skills if not s.problems], servers))
    if new == text:
        return []
    if not dry:
        write_text(path, new)
    return [f"write the index to {os.path.basename(path)}"]


ALL: list[Agent] = [Shared(), Claude(), Codex(), Gemini(), OpenCode()]
