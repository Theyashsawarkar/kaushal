#!/usr/bin/env python3
"""The user's commits on one day, across their git repositories: the raw
material of a Daily Status Report.

  dsr_commits.py [DATE] [--repos DIR...] [--author EMAIL...] [--json]

DATE: today (default), yesterday, YYYY-MM-DD or DD/MM/YYYY. Repositories are
found up to three folders deep under each DIR (default: `repos` in
~/.config/kaushal/dsr.toml, else ~/work ~/codes ~/projects ~/src). Authors:
--author, else `authors` in dsr.toml, else the git user.email of each
repository and the global one. A commit counts on the day its author wrote
it (author date, local time), on any branch, once.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tomllib

CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "kaushal", "dsr.toml")
SKIP = {"node_modules", ".venv", "venv", "vendor", "dist", "build", "target", ".cache"}


def settings() -> dict:
    try:
        with open(CONFIG, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def parse_day(text: str) -> dt.date:
    today = dt.date.today()
    if text in ("", "today"):
        return today
    if text == "yesterday":
        return today - dt.timedelta(days=1)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise SystemExit(f"dsr_commits: can't read the date {text!r} (YYYY-MM-DD or DD/MM/YYYY)")


def find_repos(roots: list[str]) -> list[str]:
    out = []
    for root in roots:
        root = os.path.expanduser(root)
        base = root.rstrip("/").count("/")
        for here, dirs, _ in os.walk(root):
            if ".git" in dirs:
                out.append(here)
            dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".") and here.count("/") - base < 3]
    return sorted(set(out))


def git(repo: str, *args: str) -> str:
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def commits(repo: str, day: dt.date, authors: set[str]) -> list[dict]:
    # Committer-date window a day wider each side, then the exact author date.
    since, until = day - dt.timedelta(days=2), day + dt.timedelta(days=3)
    raw = git(repo, "log", "--all", f"--since={since}", f"--until={until}",
              "--format=%H%x1f%aI%x1f%ae%x1f%P%x1f%s%x1f%b%x1e")
    out, seen = [], set()
    for rec in raw.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) < 6 or parts[0] in seen:
            continue
        sha, when, email, parents, subject, body = parts
        seen.add(sha)
        at = dt.datetime.fromisoformat(when).astimezone()
        if at.date() != day or (authors and email.lower() not in authors):
            continue
        stat = git(repo, "show", "--shortstat", "--format=", sha).strip().splitlines()
        out.append({"time": at.strftime("%H:%M"), "subject": subject, "merge": len(parents.split()) > 1,
                    "body": "\n".join(line for line in body.strip().splitlines() if not line.startswith("Co-Authored-By"))[:1500],
                    "stat": stat[-1].strip() if stat else ""})
    return sorted(out, key=lambda c: c["time"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("date", nargs="?", default="today")
    ap.add_argument("--repos", nargs="+")
    ap.add_argument("--author", nargs="+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cfg = settings()
    day = parse_day(a.date)
    roots = a.repos or cfg.get("repos") or ["~/work", "~/codes", "~/projects", "~/src"]
    repos = find_repos(roots)
    fixed = {e.lower() for e in (a.author or cfg.get("authors") or [])}
    me = git(os.path.expanduser("~"), "config", "--global", "user.email").strip().lower()
    result = {}
    for repo in repos:
        authors = fixed or {e for e in (me, git(repo, "config", "user.email").strip().lower()) if e}
        found = commits(repo, day, authors)
        if found:
            result[repo] = found
    if a.json:
        print(json.dumps({"date": day.isoformat(), "repos": result}, indent=2))
        return 0
    print(f"Commits on {day:%A %d/%m/%Y} ({len(repos)} repositories looked at under {', '.join(roots)})")
    if not result:
        print("none: ask the user what they worked on (meetings, reviews, debugging leave no commits)")
    for repo, found in result.items():
        print(f"\n== {repo.replace(os.path.expanduser('~'), '~')}")
        for c in found:
            print(f"{c['time']}  {'[merge] ' if c['merge'] else ''}{c['subject']}" + (f"  ({c['stat']})" if c["stat"] else ""))
            for line in c["body"].splitlines():
                print(f"        {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
