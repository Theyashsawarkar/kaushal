"""What kaushal hands to agents: skills (folders with a SKILL.md) and MCP
servers (mcp.toml). Both come from the repo and from the user's own config
folder; the user's win on a name clash, and `enabled = false` drops one.
"""
import os
import re
import shutil
import tomllib
from dataclasses import dataclass, field

HOME = os.path.expanduser("~")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_dir() -> str:
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "kaushal")


def state_dir() -> str:
    return os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(HOME, ".local", "state"), "kaushal")


def skill_roots() -> list[tuple[str, str]]:
    """(origin, folder) pairs, later ones overriding earlier ones."""
    return [("vayu", os.path.join(REPO, "skills")), ("yours", os.path.join(config_dir(), "skills"))]


NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass
class Skill:
    name: str
    description: str
    path: str  # the folder
    origin: str
    problems: list[str] = field(default_factory=list)

    @property
    def file(self) -> str:
        return os.path.join(self.path, "SKILL.md")


def frontmatter(text: str) -> dict[str, str]:
    """The `key: value` lines between the leading `---` lines (folded `>` values joined)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    key = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            key, value = m.group(1), m.group(2).strip()
            out[key] = "" if value in (">", "|", ">-", "|-") else value.strip("'\"")
        elif key and line.strip():
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def load_skill(origin: str, folder: str) -> Skill:
    name = os.path.basename(folder)
    try:
        with open(os.path.join(folder, "SKILL.md"), encoding="utf-8") as f:
            meta = frontmatter(f.read())
    except OSError:
        return Skill(name, "", folder, origin, ["no SKILL.md"])
    s = Skill(meta.get("name", ""), meta.get("description", ""), folder, origin)
    if not s.name:
        s.name, s.problems = name, ["SKILL.md has no `name`"]
    elif s.name != name:
        s.problems.append(f"`name: {s.name}` differs from its folder {name}/")
    if not NAME_RE.match(s.name):
        s.problems.append("name must be lowercase letters, digits and dashes")
    if not s.description:
        s.problems.append("SKILL.md has no `description` (agents choose skills by it)")
    elif len(s.description) > 1024:
        s.problems.append("description is over 1024 characters")
    return s


def skills() -> list[Skill]:
    found: dict[str, Skill] = {}
    for origin, root in skill_roots():
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            folder = os.path.join(root, entry)
            if entry.startswith(".") or not os.path.isdir(folder):
                continue
            s = load_skill(origin, folder)
            found[s.name] = s
    return sorted(found.values(), key=lambda s: s.name)


@dataclass
class Server:
    name: str
    command: str
    args: list[str]
    env: dict[str, str]
    description: str
    origin: str

    def for_agent(self, agent: str) -> tuple[str, list[str], dict[str, str]]:
        """Command, args and env with `{agent}` filled in (ekatva labels its log with it)."""
        fill = lambda v: v.replace("{agent}", agent)
        return self.command, [fill(a) for a in self.args], {k: fill(v) for k, v in self.env.items()}

    def installed(self) -> bool:
        return which(self.command) is not None


def which(cmd: str) -> str | None:
    """Like shutil.which, with ~/.local/bin always looked in (a login unit's PATH lacks it)."""
    path = os.environ.get("PATH", "")
    extra = os.path.join(HOME, ".local", "bin")
    if extra not in path.split(os.pathsep):
        path = extra + os.pathsep + path
    return shutil.which(cmd, path=path)


def _read_toml(path: str) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def servers() -> list[Server]:
    merged: dict[str, tuple[str, dict]] = {}
    for origin, path in (("vayu", os.path.join(REPO, "mcp.toml")), ("yours", os.path.join(config_dir(), "mcp.toml"))):
        for name, spec in (_read_toml(path).get("servers") or {}).items():
            base = merged.get(name, (origin, {}))[1]
            merged[name] = (origin, {**base, **spec})
    out = []
    for name, (origin, spec) in sorted(merged.items()):
        if spec.get("enabled", True) is False or not spec.get("command"):
            continue
        out.append(Server(name, spec["command"], [str(a) for a in spec.get("args", [])],
                          {str(k): str(v) for k, v in (spec.get("env") or {}).items()},
                          spec.get("description", ""), origin))
    return out


# ------------------------------------------------------------------ off
# Skills and servers turned off for every agent (`kaushal off NAME`, x in
# the app): ~/.config/kaushal/off.toml, written by kaushal, yours to edit.

def off_file() -> str:
    return os.path.join(config_dir(), "off.toml")


def off() -> dict[str, set[str]]:
    data = _read_toml(off_file())
    return {k: {str(n) for n in data.get(k, [])} for k in ("skills", "servers")}


def set_off(kind: str, name: str, is_off: bool) -> None:
    """Turns a skill (kind "skills") or server ("servers") off or back on."""
    current = off()
    (current[kind].add if is_off else current[kind].discard)(name)
    lines = ["# Turned off for every agent: `kaushal on NAME` (or x in `kaushal ui`) turns one back on.",
             *(f"{k} = [{', '.join(json_str(n) for n in sorted(current[k]))}]" for k in ("skills", "servers"))]
    os.makedirs(config_dir(), exist_ok=True)
    tmp = off_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, off_file())


def json_str(s: str) -> str:
    import json
    return json.dumps(s)
