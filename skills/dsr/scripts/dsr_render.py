#!/usr/bin/env python3
"""Checks a Daily Status Report's timetable and writes it as plain text and
as an HTML table (email clients show the table; the text is its fallback).

  dsr_render.py ROWS.json [--start "11:30 AM"] [--end "09:00 PM"] [--out DIR]

ROWS.json: {"date": "26/10/2026", "rows": [["11:30 AM", "01:00 PM", "Worked on ..."], ...]}
(date also as YYYY-MM-DD). Checks, and exits 2 listing every problem, unless:
the rows run back to back with no gap or overlap, each ends after it starts,
the day starts at --start and ends at --end when given, and the lunch break
from ~/.config/kaushal/dsr.toml (default 01:00 PM to 02:00 PM) is a row of
its own when the day spans it. Writes DIR/dsr.txt and DIR/dsr.html (DIR
defaults to the folder of ROWS.json) and prints the table.
"""
import argparse
import datetime as dt
import html
import json
import os
import sys
import tomllib

CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "kaushal", "dsr.toml")
TD = "border:1px solid #999;padding:6px 10px;vertical-align:top;font-family:Arial,sans-serif;font-size:14px"
TH = TD.replace("vertical-align:top", "background:#f2f2f2;text-align:left")


def settings() -> dict:
    try:
        with open(CONFIG, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def clock(text: str) -> dt.datetime:
    t = " ".join(text.strip().upper().replace(".", "").split())
    for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            return dt.datetime.strptime(t, fmt)
        except ValueError:
            pass
    raise ValueError(f"can't read the time {text!r} (like 11:30 AM)")


def show(t: dt.datetime) -> str:
    return t.strftime("%I:%M %p")


def day_label(text: str) -> str:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).strftime("%d/%m/%Y")
        except ValueError:
            pass
    raise ValueError(f"can't read the date {text!r}")


def check(rows: list[tuple[dt.datetime, dt.datetime, str]], start: str | None, end: str | None, lunch: str | None,
          lunch_task: str) -> list[str]:
    problems = []
    if not rows:
        return ["no rows"]
    for i, (a, b, task) in enumerate(rows):
        if b <= a:
            problems.append(f"row {i + 1} ({show(a)} to {show(b)}) ends before it starts")
        if not task.strip():
            problems.append(f"row {i + 1} has no task")
        if i and rows[i - 1][1] != a:
            gap = "a gap" if rows[i - 1][1] < a else "an overlap"
            problems.append(f"{gap} between {show(rows[i - 1][1])} and {show(a)} (rows {i} and {i + 1})")
    if start and rows[0][0] != clock(start):
        problems.append(f"the day starts at {show(rows[0][0])}, not {show(clock(start))}")
    if end and rows[-1][1] != clock(end):
        problems.append(f"the day ends at {show(rows[-1][1])}, not {show(clock(end))}")
    if lunch:
        la, lb = (clock(x) for x in lunch.split(" to "))
        if rows[0][0] < la and rows[-1][1] > lb and not any(a == la and b == lb and t.strip() == lunch_task for a, b, t in rows):
            problems.append(f"no \"{lunch_task}\" row from {show(la)} to {show(lb)}")
    return problems


def render(date: str, rows, greeting: str) -> tuple[str, str]:
    plain = f"{greeting}\n\nDate : {date}\n\nTime\tTasks\n" + "".join(f"{show(a)} to {show(b)}\t{t}\n" for a, b, t in rows)
    trs = "\n".join(f'<tr><td style="{TD}" nowrap>{show(a)} to {show(b)}</td><td style="{TD}">{html.escape(t)}</td></tr>'
                    for a, b, t in rows)
    page = (f'<div style="font-family:Arial,sans-serif;font-size:14px">\n<p>{html.escape(greeting)}</p>\n'
            f"<p>Date : {date}</p>\n"
            f'<table style="border-collapse:collapse" cellpadding="0" cellspacing="0">\n'
            f'<tr><th style="{TH}">Time</th><th style="{TH}">Tasks</th></tr>\n{trs}\n</table>\n</div>\n')
    return plain, page


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("rows")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--out")
    a = ap.parse_args()
    cfg = settings()
    with open(a.rows, encoding="utf-8") as f:
        data = json.load(f)
    try:
        date = day_label(data["date"])
        rows = [(clock(r[0]), clock(r[1]), str(r[2])) for r in data["rows"]]
    except (KeyError, IndexError, ValueError) as e:
        print(f"dsr_render: {e}", file=sys.stderr)
        return 2
    lunch_task = cfg.get("lunch_task", "Lunch Break")
    problems = check(rows, a.start, a.end, cfg.get("lunch", "01:00 PM to 02:00 PM") or None, lunch_task)
    if problems:
        print("dsr_render: fix these and run it again:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 2
    plain, page = render(date, rows, cfg.get("greeting", "Hello,"))
    out = a.out or os.path.dirname(os.path.abspath(a.rows))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "dsr.txt"), "w", encoding="utf-8") as f:
        f.write(plain)
    with open(os.path.join(out, "dsr.html"), "w", encoding="utf-8") as f:
        f.write(page)
    width = max(len(f"{show(x)} to {show(y)}") for x, y, _ in rows)
    print(f"Date : {date}\n")
    for x, y, t in rows:
        print(f"{show(x)} to {show(y)}".ljust(width + 2) + t)
    print(f"\nwrote {os.path.join(out, 'dsr.txt')} and {os.path.join(out, 'dsr.html')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
