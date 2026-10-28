"""The dsr skill's scripts: collecting a day's commits, checking and rendering the table."""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "dsr", "scripts")
sys.path.insert(0, SCRIPTS)

import dsr_render  # noqa: E402

T = dsr_render.clock


def rows(*spec):
    return [(T(a), T(b), t) for a, b, t in spec]


class Check(unittest.TestCase):
    DAY = rows(("11:30 AM", "01:00 PM", "a"), ("01:00 PM", "02:00 PM", "Lunch Break"), ("02:00 PM", "09:00 PM", "b"))

    def test_a_good_day_passes(self):
        self.assertEqual(dsr_render.check(self.DAY, "11:30 AM", "9 PM", "01:00 PM to 02:00 PM", "Lunch Break"), [])

    def test_gaps_overlaps_and_bounds(self):
        bad = rows(("11:30 AM", "01:00 PM", "a"), ("01:30 PM", "03:00 PM", "b"), ("02:30 PM", "08:00 PM", "c"))
        problems = dsr_render.check(bad, "11:00 AM", "09:00 PM", "01:00 PM to 02:00 PM", "Lunch Break")
        text = " | ".join(problems)
        for want in ("a gap", "an overlap", "starts at 11:30 AM", "ends at 08:00 PM", "Lunch Break"):
            self.assertIn(want, text)

    def test_lunch_only_when_the_day_spans_it(self):
        morning = rows(("09:00 AM", "12:00 PM", "a"))
        self.assertEqual(dsr_render.check(morning, None, None, "01:00 PM to 02:00 PM", "Lunch Break"), [])

    def test_render_is_a_real_table(self):
        plain, page = dsr_render.render("26/10/2026", self.DAY, "Hello,")
        self.assertIn("Date : 26/10/2026", plain)
        self.assertIn("11:30 AM to 01:00 PM\ta", plain)
        self.assertEqual(page.count("<tr>"), 4)
        self.assertIn("<th", page)

    def test_tasks_are_escaped(self):
        _, page = dsr_render.render("26/10/2026", rows(("09:00 AM", "10:00 AM", "<b>&")), "Hello,")
        self.assertIn("&lt;b&gt;&amp;", page)

    def test_command_writes_both_files(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "rows.json"), "w") as f:
            json.dump({"date": "2026-10-26", "rows": [["11:30 AM", "01:00 PM", "a"], ["01:00 PM", "02:00 PM", "Lunch Break"],
                                                       ["02:00 PM", "09:00 PM", "b"]]}, f)
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "dsr_render.py"), os.path.join(d, "rows.json"),
                            "--start", "11:30 AM", "--end", "09:00 PM"],
                           capture_output=True, text=True, env={**os.environ, "XDG_CONFIG_HOME": d})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(d, "dsr.html")))


class Commits(unittest.TestCase):
    def test_finds_the_days_commits_by_author_date(self):
        root = tempfile.mkdtemp()
        repo = os.path.join(root, "work", "app")
        os.makedirs(repo)
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "XDG_CONFIG_HOME": root}

        def git(*a, when=None):
            e = dict(env)
            if when:
                e["GIT_AUTHOR_DATE"] = e["GIT_COMMITTER_DATE"] = when
            subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True, env=e)

        git("init", "-q")
        git("config", "user.email", "me@example.com")
        git("config", "user.name", "Me")
        day = dt.date(2026, 10, 26)
        git("commit", "-q", "--allow-empty", "-m", "built the thing", "-m", "the details", when=f"{day}T15:00:00")
        git("commit", "-q", "--allow-empty", "-m", "the day after", when=f"{day + dt.timedelta(days=1)}T10:00:00")
        git("-c", "user.email=someone@example.com", "commit", "-q", "--allow-empty", "-m", "not mine", when=f"{day}T16:00:00")
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "dsr_commits.py"), "26/10/2026", "--repos", root, "--json"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        found = json.loads(r.stdout)["repos"]
        subjects = [c["subject"] for c in found[repo]]
        self.assertEqual(subjects, ["built the thing"])
        self.assertEqual(found[repo][0]["body"], "the details")


if __name__ == "__main__":
    unittest.main()
