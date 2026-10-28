#!/usr/bin/env python3
"""Builds kaushal's website: the family's scripts/build-site.py (shared by
every Vayu tool, so not changed here) plus what only kaushal has, its
skills:

- the README's "Vayu's skills" list, regenerated from skills/ (between the
  <!-- skills --> markers), so it never misses one;
- docs/skills/index.html, every skill as a card, and docs/skills/<name>.html,
  each skill's full instructions and files;
- a "Skills" link in every page's top bar.

    python3 scripts/site.py           # write README.md's list and docs/
    python3 scripts/site.py --check   # exit 1 if either would change

Standard library only.
"""
import html
import importlib.util
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kaushal.store import load_skill  # noqa: E402

spec = importlib.util.spec_from_file_location("build_site", os.path.join(ROOT, "scripts", "build-site.py"))
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)

GH = f"{site.GH}/kaushal"
BEGIN, END = "<!-- skills: written by scripts/site.py from skills/ -->", "<!-- /skills -->"


def skills():
    root = os.path.join(ROOT, "skills")
    out = []
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        if not os.path.isfile(os.path.join(folder, "SKILL.md")):
            continue
        s = load_skill("vayu", folder)
        text = open(s.file, encoding="utf-8").read()
        body = re.sub(r"(?s)\A---\n.*?\n---\n", "", text).strip()
        files = sorted(os.path.relpath(os.path.join(d, f), folder) for d, _, fs in os.walk(folder) for f in fs
                       if "__pycache__" not in d and f != "SKILL.md")
        out.append((s, body, files))
    return out


def readme_list(found) -> str:
    cell = lambda t: t.replace("|", "\\|")
    rows = "\n".join(f"| [`{s.name}`](skills/{s.name}/SKILL.md) | {cell(s.description)} |" for s, _, _ in found)
    return (f"{BEGIN}\n{len(found)} skill{'s, each' if len(found) != 1 else ','} with its full instructions on the "
            f"[Skills page](https://theyashsawarkar.github.io/kaushal/skills/):\n\n| Skill | What it does, and when an agent uses it |\n"
            f"|---|---|\n{rows}\n{END}")


def update_readme(found, check: bool) -> bool:
    path = os.path.join(ROOT, "README.md")
    text = open(path, encoding="utf-8").read()
    if BEGIN not in text:
        raise SystemExit(f"README.md has no {BEGIN} marker")
    new = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: readme_list(found), text, count=1, flags=re.S)
    if new == text:
        return False
    if not check:
        open(path, "w", encoding="utf-8").write(new)
    return True


def files_list(s, files) -> str:
    items = [f'<li><a href="{GH}/blob/main/skills/{s.name}/SKILL.md"><code>SKILL.md</code></a> the instructions</li>']
    items += [f'<li><a href="{GH}/blob/main/skills/{s.name}/{html.escape(f)}"><code>{html.escape(f)}</code></a></li>' for f in files]
    return "<ul>" + "".join(items) + "</ul>"


def skill_pages(meta, found) -> dict[str, bytes]:
    pages = {}
    cards = []
    for s, body, files in found:
        scripts = [f for f in files if f.startswith("scripts/")]
        def link(u, s=s):
            if u.startswith(("http://", "https://", "#", "mailto:")):
                return u
            return f"{GH}/blob/main/skills/{s.name}/{u}"
        head = (f'<p class="n"><a href="index.html">← All skills</a></p>'
                f'<h2><code>{html.escape(s.name)}</code></h2><p class="lead">{html.escape(s.description)}</p>'
                f'<blockquote><p><b>Use it</b>: ask any agent in your own words. It picks this skill by the description '
                f'above, opens these instructions and follows them. Already in every agent kaushal syncs.</p></blockquote>'
                f"<h3>Files</h3>{files_list(s, files)}")
        doc = site.markdown(body, link, None, 1)
        pages[f"skills/{s.name}.html"] = site.page(meta, f"{s.name} · kaushal skills", head + doc, 1, "skills").encode()
        extra = f" · {len(scripts)} script{'s' if len(scripts) != 1 else ''}" if scripts else ""
        cards.append(f'<a class="card" href="{s.name}.html"><div class="n">{s.origin}{extra}</div>'
                     f"<h3><code>{html.escape(s.name)}</code></h3><p>{html.escape(s.description)}</p></a>")
    intro = ("<h2>Skills</h2><p>Every skill kaushal gives your agents: Claude Code on every account, Codex, opencode, "
             "Gemini CLI and any agent reading <code>~/.agents/skills</code>. A skill is a folder with a "
             '<a href="https://agentskills.io">SKILL.md</a>: its description says when to use it, its body how. '
             "Ask an agent for the job in your own words and it uses the skill. Your own skills (<code>kaushal new NAME</code>) "
             f'join these on your machine. Sources: <a href="{GH}/tree/main/skills">skills/</a>.</p>')
    grid = f'<div class="cards">{"".join(cards)}</div>'
    pages["skills/index.html"] = site.page(meta, "Skills · kaushal", intro + grid, 1, "skills").encode()
    return pages


def with_skills_link(rel: str, data: bytes) -> bytes:
    """Adds "Skills" to the top bar, before GitHub (the shared page() has no hook for it)."""
    if not rel.endswith(".html"):
        return data
    up = "../" * rel.count("/")
    on = "on" if rel.startswith("skills/") else ""
    return data.replace(b'<a class="gh" href=', f'<a href="{up}skills/index.html" class="{on}">Skills</a><a class="gh" href='.encode(), 1)


def main() -> int:
    check = "--check" in sys.argv
    found = skills()
    readme_changed = update_readme(found, check)
    import tomllib
    meta = tomllib.load(open(os.path.join(ROOT, "site.toml"), "rb"))
    shared_build = site.build

    def build():
        files = {**shared_build(), **skill_pages(meta, found)}
        files = {rel: with_skills_link(rel, data) for rel, data in files.items()}
        # The home page links skills to their pages here, not to GitHub.
        for s, _, _ in found:
            files["index.html"] = files["index.html"].replace(
                f'href="{GH}/blob/main/skills/{s.name}/SKILL.md"'.encode(), f'href="skills/{s.name}.html"'.encode())
        return files

    site.build = build
    code = site.main()
    if readme_changed:
        print("README.md's skills list is out of date; run python3 scripts/site.py" if check else "README.md: skills list updated")
        return 1 if check else code
    return code


if __name__ == "__main__":
    sys.exit(main())
