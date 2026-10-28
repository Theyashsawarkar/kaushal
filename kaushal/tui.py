"""The app (`kaushal ui`): every skill, tool and agent in one place.

  1 2 3 Tab   Skills, Tools, Agents        j k ↓ ↑ g G   move, first, last
  Enter       read a skill / test a tool / open an agent's folder
  e c         edit a skill / its settings  n   new skill of your own
  x           turn a skill or tool off (on) for every agent
  t           test a tool                  u   take back what kaushal added to an agent
  s d         sync / doctor                /   filter    ?  keys    q Esc  quit
"""
import curses
import os
import shutil
import subprocess
import textwrap
import threading
import time

from . import ops, theme
from .agents import ALL
from .store import NAME_RE, config_dir, set_off

# keybind: Kaushal/app | 1 / 2 / 3 | Switch to the Skills / Tools / Agents tab
# keybind: Kaushal/app | Tab / Shift+Tab | Switch to the next / previous tab
# keybind: Kaushal/app | j / k | Move down / up the list
# keybind: Kaushal/app | g / G | Jump to the first / last item
# keybind: Kaushal/app | Enter | Open the skill to read (a tool: test it; an agent: its folder)
# keybind: Kaushal/app | e | Edit the skill in your editor (Vayu's: your own copy)
# keybind: Kaushal/app | c | Edit the skill's settings (~/.config/kaushal/NAME.toml)
# keybind: Kaushal/app | n | Create a skill of your own
# keybind: Kaushal/app | x | Toggle the skill or tool off / on for every agent
# keybind: Kaushal/app | t | Run a test of the tool (start it, list its tools)
# keybind: Kaushal/app | u | Take back what kaushal added to the agent (asks)
# keybind: Kaushal/app | s | Run a sync of every agent now
# keybind: Kaushal/app | d | Run doctor (check every agent has everything)
# keybind: Kaushal/app | / | Search the list (Esc clears)
# keybind: Kaushal/app | r | Reload from disk
# keybind: Kaushal/app | ? | Show all keys
# keybind: Kaushal/app | q / Esc | Quit the app

PALETTE = {  # Catppuccin Mocha, as curses colour numbers 16+ (vesha's, so the family matches)
    "text": (205, 214, 244), "sub": (166, 173, 200), "dim": (127, 132, 156), "faint": (69, 71, 90),
    "peach": (250, 179, 135), "green": (166, 227, 161), "red": (243, 139, 168), "yellow": (249, 226, 175),
    "sky": (137, 220, 235), "mauve": (203, 166, 247), "teal": (148, 226, 213), "crust": (17, 17, 27),
    "selbg": (42, 43, 60), "surface": (49, 50, 68), "border": (88, 91, 112),
}
theme.apply(PALETTE, {"text": "text", "sub": "subtext0", "dim": "overlay1", "faint": "surface1", "peach": "peach",
                      "green": "green", "red": "red", "yellow": "yellow", "sky": "sky", "mauve": "mauve", "teal": "teal",
                      "crust": "crust", "selbg": ("base", "surface0", 0.5), "surface": "surface0", "border": "frame"})
FALLBACK = {"text": curses.COLOR_WHITE, "sub": curses.COLOR_WHITE, "dim": curses.COLOR_WHITE, "faint": curses.COLOR_BLACK,
            "peach": curses.COLOR_YELLOW, "green": curses.COLOR_GREEN, "red": curses.COLOR_RED, "yellow": curses.COLOR_YELLOW,
            "sky": curses.COLOR_CYAN, "mauve": curses.COLOR_MAGENTA, "teal": curses.COLOR_CYAN, "crust": curses.COLOR_BLACK,
            "selbg": curses.COLOR_BLACK, "surface": curses.COLOR_BLACK, "border": curses.COLOR_WHITE}
TABS = ["skills", "tools", "agents"]
HELP = [
    ("Move", [("1 2 3", "Skills, Tools, Agents"), ("Tab S-Tab", "next / previous tab"), ("j k ↓ ↑", "down / up"),
              ("g G", "first / last"), ("/", "filter (Esc clears)")]),
    ("Skills", [("Enter", "read it"), ("e", "edit it (Vayu's: your copy)"), ("c", "edit its settings"),
                ("n", "new skill of your own"), ("x", "off / on for every agent")]),
    ("Tools", [("Enter t", "test: start it, list its tools"), ("x", "off / on for every agent")]),
    ("Agents", [("Enter", "open its folder"), ("u", "take back kaushal's things")]),
    ("Everywhere", [("s", "sync every agent"), ("d", "doctor"), ("r", "reload"), ("?", "these keys"), ("q Esc", "quit")]),
]


def xterm256(rgb):
    """The nearest of the terminal's 256 standard colours, for terminals that can't redefine colours (tmux, mostly)."""
    steps = (0, 95, 135, 175, 215, 255)

    def near(v):
        return min(range(6), key=lambda i: abs(steps[i] - v))
    r, g, b = (near(v) for v in rgb)
    cube, cube_rgb = 16 + 36 * r + 6 * g + b, (steps[r], steps[g], steps[b])
    gray = max(0, min(23, round((sum(rgb) / 3 - 8) / 10)))

    def dist(c):
        return sum((x - y) ** 2 for x, y in zip(c, rgb, strict=True))
    return cube if dist(cube_rgb) <= dist((8 + 10 * gray,) * 3) else 232 + gray


def when(ts):
    if not ts:
        return "never"
    t = time.localtime(ts)
    return time.strftime("%H:%M" if time.strftime("%F", t) == time.strftime("%F") else "%d %b %H:%M", t)


class App:
    def __init__(self, scr):
        self.scr = scr
        self.tab = "skills"
        self.sel = dict.fromkeys(TABS, 0)
        self.filter = ""
        self.mode = "NORMAL"
        self.input = None     # (prompt, buffer, callback)
        self.confirm = None   # (question, callback)
        self.overlay = None   # (title, [(text, colour)]) or "help"
        self.busy = ""        # what runs in the background
        self.toast_msg, self.toast_at, self.toast_kind = "", 0.0, "ok"
        self.lock = threading.Lock()
        self.init_colors()
        self.reload()

    # ---------------------------------------------------------------- data
    def reload(self):
        results, w = ops.sync(dry=True)
        with self.lock:
            self.w, self.results, self.state = w, results, ops.load_state()
            self.absent = [a for a in ALL if not a.present()]
            self.synced = ops.synced_at()

    def has_skill(self, r, name):
        k = r.target.agent.key
        if name in self.w.off["skills"]:
            return False
        if k == "opencode":   # it reads ~/.agents/skills
            return any(x.target.agent.key == "agents" and name in self.state.get(x.target.key, {}).get("skills", [])
                       for x in self.results)
        if k == "gemini":     # through the index in GEMINI.md
            return not r.pending
        return name in self.state.get(r.target.key, {}).get("skills", [])

    def has_server(self, r, name):
        return name in self.state.get(r.target.key, {}).get("mcp", [])

    def tool_targets(self):
        return [r for r in self.results if r.target.agent.key != "agents"]

    def rows(self):
        """The current tab's items, filtered: skills, servers, or (result | absent agent)."""
        f = self.filter.lower()
        if self.tab == "skills":
            items = [s for s in self.w.all_skills if f in (s.name + " " + s.description).lower()]
            return items + ([None] if not f else [])   # None: the "+ new skill" row
        if self.tab == "tools":
            return [s for s in self.w.all_servers if f in (s.name + " " + s.description).lower()]
        items = list(self.results) + list(self.absent)
        return [i for i in items if f in (self.label(i) + " " + self.where(i)).lower()]

    def label(self, i):
        return i.target.agent.label if isinstance(i, ops.Result) else i.label

    def where(self, i):
        return i.target.where if isinstance(i, ops.Result) else ops.short(i.home)

    def current(self):
        rows = self.rows()
        if not rows:
            return None
        self.sel[self.tab] = max(0, min(self.sel[self.tab], len(rows) - 1))
        return rows[self.sel[self.tab]]

    # ---------------------------------------------------------------- colours
    def init_colors(self):
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        self.cp = {}
        custom = curses.can_change_color() and curses.COLORS >= 256
        for i, (name, rgb) in enumerate(PALETTE.items()):
            num = 16 + i
            if custom:
                try:
                    curses.init_color(num, *(round(v * 1000 / 255) for v in rgb))
                except curses.error:
                    custom = False
            self.cp[name] = num if custom else xterm256(rgb) if curses.COLORS >= 256 else FALLBACK[name]
        pairs, n = {}, 1
        for fg in PALETTE:
            pairs[fg] = n
            curses.init_pair(n, self.cp[fg], bg)
            n += 1
        for fg in ("text", "sub", "dim", "green", "red", "yellow", "peach", "mauve", "teal", "sky", "faint"):
            pairs["sel_" + fg] = n
            curses.init_pair(n, self.cp[fg], self.cp["selbg"])
            n += 1
        for name, fg, bgc in (("chip_peach", "crust", "peach"), ("chip_green", "crust", "green"), ("chip_yellow", "crust", "yellow"),
                              ("chip_teal", "crust", "teal"), ("chip_red", "crust", "red"), ("chip_sky", "crust", "sky"),
                              ("chip_mauve", "crust", "mauve"), ("chip_dim", "text", "surface"), ("key", "sub", "surface")):
            pairs[name] = n
            curses.init_pair(n, self.cp[fg], self.cp[bgc])
            n += 1
            pairs["cap_" + name] = n   # the rounded ends: the chip's colour on the background
            curses.init_pair(n, self.cp[bgc], bg)
            n += 1
        self.pairs = pairs

    def a(self, name, bold=False, sel=False):
        key = ("sel_" + name) if sel and ("sel_" + name) in self.pairs else name
        return curses.color_pair(self.pairs[key]) | (curses.A_BOLD if bold else 0)

    # ---------------------------------------------------------------- drawing
    def put(self, y, x, text, attr=0, maxw=None):
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return x
        limit = w - x if maxw is None else min(maxw, w - x)
        text = str(text)
        if len(text) > limit:
            text = text[: max(0, limit - 1)] + "…" if limit > 1 else text[:limit]
        try:
            self.scr.addstr(y, x, text, attr)
        except curses.error:
            pass   # the bottom-right cell: harmless
        return x + len(text)

    def box(self, y, x, h, w, title=()):
        if h < 2 or w < 4:
            return
        b = self.a("border")
        self.put(y, x, "╭" + "─" * (w - 2) + "╮", b)
        for i in range(1, h - 1):
            self.put(y + i, x, "│", b)
            self.put(y + i, x + w - 1, "│", b)
        self.put(y + h - 1, x, "╰" + "─" * (w - 2) + "╯", b)
        if title:
            tx = self.put(y, x + 2, " ", b)
            for text, color in title:
                tx = self.put(y, tx, text, self.a(color, color in ("yellow", "text")))
            self.put(y, tx, " ", b)

    def chip(self, y, x, text, pair):
        x = self.put(y, x, "", self.a("cap_" + pair))
        x = self.put(y, x, text, curses.color_pair(self.pairs[pair]) | curses.A_BOLD)
        return self.put(y, x, "", self.a("cap_" + pair)) + 1

    def section(self, y, x, w, title):
        x2 = self.put(y, x, "── ", self.a("faint"))
        x2 = self.put(y, x2, title, self.a("dim"))
        self.put(y, x2 + 1, "─" * max(0, x + w - x2 - 2), self.a("faint"))
        return y + 1

    def wrap(self, y, x, w, text, attr, bottom):
        for line in textwrap.wrap(text, max(10, w)) or [""]:
            if y >= bottom:
                break
            self.put(y, x, line, attr)
            y += 1
        return y

    def draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        if h < 18 or w < 76:
            self.put(0, 0, "kaushal needs a bigger window (76×18)", self.a("yellow", True))
            self.scr.refresh()
            return
        with self.lock:
            self.draw_strip(w)
            top, bottom = 3, h - 2
            if w >= 110:
                lw = max(56, w * 56 // 100)
                self.draw_list(top, 0, bottom - top + 1, lw)
                self.draw_side(top, lw + 1, bottom - top + 1, w - lw - 1)
            else:
                lh = min(len(self.rows()) + 5, (bottom - top + 1) // 2)
                self.draw_list(top, 0, lh, w)
                self.draw_side(top + lh, 0, bottom - top + 1 - lh, w)
            self.statusline()
            if self.overlay == "help":
                self.draw_help()
            elif self.overlay:
                self.draw_overlay(*self.overlay)
        self.scr.refresh()

    def draw_strip(self, w):
        self.box(0, 0, 3, w)
        x = self.put(1, 2, "kaushal", self.a("yellow", True))
        x = self.put(1, x + 1, "कौशल", self.a("dim")) + 3
        counts = {"skills": len(self.w.all_skills), "tools": len(self.w.all_servers),
                  "agents": len([r for r in self.results if r.target.agent.key != "agents"])}
        for tab in TABS:
            label = f"{tab.capitalize()}  {counts[tab]}"
            if tab == self.tab:
                x = self.chip(1, x, label, "chip_yellow") + 2
            else:
                x = self.put(1, x + 1, tab.capitalize(), self.a("sub"))
                x = self.put(1, x + 2, str(counts[tab]), self.a("dim")) + 3
        pending = sum(1 for r in self.results if r.pending or r.error)
        if self.busy:
            state = [(f"⟳ {self.busy}…", "teal")]
        elif pending:
            state = [(f"✗ {pending} agent(s) out of date: s syncs", "peach")]
        else:
            state = [("✓ every agent in sync", "green")]
        right = state + [(f"   synced {when(self.synced)}", "dim"), ("   ? keys", "dim")]
        width = sum(len(t) for t, _ in right)
        if x + width > w - 2:
            right = state + [("   ? keys", "dim")]
            width = sum(len(t) for t, _ in right)
        rx = max(x, w - 2 - width)
        for text, color in right:
            rx = self.put(1, rx, text, self.a(color))

    # ---- left: the list
    COLS = {"skills": (("skill", 16), ("from", 8), ("agents", 9), ("what it does", 0)),
            "tools": (("tool", 12), ("command", 16), ("agents", 9), ("what it gives agents", 0)),
            "agents": (("", 3), ("agent", 14), ("where", 24), ("state", 0))}

    def draw_list(self, y, x, h, w):
        rows = self.rows()
        names = {"skills": "skills", "tools": "tools", "agents": "agents"}
        sub = {"skills": "in every agent", "tools": "MCP servers", "agents": "found on this machine"}[self.tab]
        title = [("◆ ", "yellow"), (names[self.tab], "yellow"), (f" · {sub}", "dim")]
        if self.filter:
            title += [(f" · /{self.filter}", "sky")]
        self.box(y, x, h, w, title)
        cx, inner = x + 2, w - 4
        cols, hx = self.COLS[self.tab], x + 2
        for name, width in cols:
            self.put(y + 1, hx, name, self.a("dim"))
            hx += width
        self.put(y + 2, x + 1, "─" * (w - 2), self.a("faint"))
        visible = h - 4
        sel = self.sel[self.tab]
        start = max(0, min(sel - visible + 1, len(rows) - visible)) if len(rows) > visible else 0
        for i, item in enumerate(rows[start:start + visible]):
            ry, idx = y + 3 + i, start + i
            on = idx == sel
            if on:
                self.put(ry, x + 1, " " * (w - 2), self.a("text", sel=True))
                self.put(ry, x + 1, "▌", self.a("red", sel=True))
            cells = self.cells(item)
            px = cx
            for (_, width), (text, color) in zip(cols, cells, strict=True):
                room = width - 1 if width else inner - (px - cx)
                self.put(ry, px, text, self.a(color, color in ("yellow",), on), room)
                px += width
        if not rows:
            self.put(y + 3, cx, "nothing matches" if self.filter else "nothing here yet", self.a("dim"))

    def cells(self, item):
        if self.tab == "skills":
            if item is None:
                return [("+ new skill", "dim"), ("", "dim"), ("", "dim"), ("n starts one in ~/.config/kaushal/skills", "dim")]
            off = item.name in self.w.off["skills"]
            n = sum(self.has_skill(r, item.name) for r in self.results)
            agents = ("✗ broken", "red") if item.problems else ("off", "dim") if off else \
                (f"● {n}/{len(self.results)}", "green" if n == len(self.results) else "peach")
            return [(item.name, "dim" if off else "yellow"), (item.origin, "mauve" if item.origin == "vayu" else "teal"),
                    agents, (item.description, "dim")]
        if self.tab == "tools":
            off = item.name in self.w.off["servers"]
            tt = self.tool_targets()
            n = sum(self.has_server(r, item.name) for r in tt)
            agents = ("off", "dim") if off else ("not here", "red") if not item.installed() else \
                (f"● {n}/{len(tt)}", "green" if n == len(tt) else "peach")
            return [(item.name, "dim" if off else "yellow"), (f"{item.command} {' '.join(item.args)}", "dim"), agents,
                    (item.description, "dim")]
        if isinstance(item, ops.Result):
            if item.error:
                return [("✗", "red"), (self.label(item), "text"), (self.where(item), "dim"), (item.error, "red")]
            if item.pending:
                return [("✗", "peach"), (self.label(item), "text"), (self.where(item), "dim"),
                        (f"{len(item.pending)} change(s) to make: s syncs", "peach")]
            return [("✓", "green"), (self.label(item), "text"), (self.where(item), "dim"), ("up to date", "green")]
        return [("–", "dim"), (item.label, "dim"), (ops.short(item.home), "dim"), ("not installed", "dim")]

    # ---- right: details of what's selected
    def draw_side(self, y, x, h, w):
        item = self.current()
        bottom = y + h - 1
        cx, cw = x + 2, w - 4
        if self.tab == "skills":
            self.side_skill(item, y, x, h, w, cx, cw, bottom)
        elif self.tab == "tools":
            self.side_tool(item, y, x, h, w, cx, cw, bottom)
        else:
            self.side_agent(item, y, x, h, w, cx, cw, bottom)

    def keys_block(self, yy, cx, cw, bottom, keys):
        yy = self.section(yy, cx, cw, "what now")
        for k, d in keys:
            if yy >= bottom:
                break
            self.put(yy, cx, k, self.a("red", True))
            self.put(yy, cx + 7, d, self.a("text"), cw - 7)
            yy += 1
        return yy

    def side_skill(self, s, y, x, h, w, cx, cw, bottom):
        if s is None:
            self.box(y, x, h, w, [("new skill", "yellow")])
            yy = self.wrap(y + 2, cx, cw, "A skill is a folder with a SKILL.md: a description saying what it does and when to use "
                           "it, then the steps. n names one; kaushal creates it from a template in ~/.config/kaushal/skills, "
                           "opens it in your editor, and gives it to every agent.", self.a("sub"), bottom)
            self.keys_block(yy + 1, cx, cw, bottom, [("n", "new skill"), ("Enter", "the same")])
            return
        off = s.name in self.w.off["skills"]
        self.box(y, x, h, w, [(s.name, "yellow"), (" · skill", "dim")])
        hx = self.put(y + 1, cx, s.name, self.a("text", True)) + 1
        hx = self.chip(y + 1, hx, "BROKEN" if s.problems else "OFF" if off else "ON",
                       "chip_red" if s.problems else "chip_dim" if off else "chip_green")
        self.chip(y + 1, hx, s.origin.upper(), "chip_yellow" if s.origin == "vayu" else "chip_teal")
        yy = self.wrap(y + 3, cx, cw, s.description, self.a("sub"), bottom)
        for p in s.problems:
            yy = self.wrap(yy, cx, cw, "✗ " + p, self.a("red"), bottom)
        yy = self.section(yy + 1, cx, cw, "in agents")
        for r in self.results:
            if yy >= bottom - 7:
                break
            has = self.has_skill(r, s.name)
            self.put(yy, cx, "✓" if has else "–", self.a("green" if has else "dim"))
            self.put(yy, cx + 2, f"{self.label(r)} · {self.where(r)}", self.a("text" if has else "dim"), cw - 2)
            yy += 1
        if self.absent:
            self.put(yy, cx, "– " + ", ".join(a.label for a in self.absent) + ": not installed", self.a("dim"), cw)
            yy += 1
        settings = os.path.join(config_dir(), f"{s.name}.toml")
        files = sum(len(fs) for d, _, fs in os.walk(s.path) if "__pycache__" not in d)
        yy = self.section(yy + 1, cx, cw, "files")
        for k, v in (("folder", ops.short(s.path)), ("files", str(files)),
                     ("settings", ops.short(settings) + (" ✓" if os.path.exists(settings) else "  (none)"))):
            self.put(yy, cx, k, self.a("dim"))
            self.put(yy, cx + 10, v, self.a("text"), cw - 10)
            yy += 1
        self.keys_block(yy + 1, cx, cw, bottom, [("Enter", "read SKILL.md"),
                                                 ("e", "edit it" + ("  (makes your own copy)" if s.origin == "vayu" else "")),
                                                 ("c", f"edit its settings ({s.name}.toml)"),
                                                 ("x", ("turn on" if off else "turn off") + " for every agent")])

    def side_tool(self, s, y, x, h, w, cx, cw, bottom):
        if s is None:
            self.box(y, x, h, w, [("tools", "yellow")])
            return
        off = s.name in self.w.off["servers"]
        self.box(y, x, h, w, [(s.name, "yellow"), (" · MCP server", "dim")])
        hx = self.put(y + 1, cx, s.name, self.a("text", True)) + 1
        hx = self.chip(y + 1, hx, "OFF" if off else "ON", "chip_dim" if off else "chip_green")
        self.chip(y + 1, hx, "INSTALLED" if s.installed() else "NOT INSTALLED", "chip_green" if s.installed() else "chip_red")
        yy = self.wrap(y + 3, cx, cw, s.description, self.a("sub"), bottom)
        yy = self.section(yy + 1, cx, cw, "server")
        pairs = [("command", f"{s.command} {' '.join(s.args)}"), ("from", s.origin)]
        pairs += [("env", " ".join(f"{k}={v}" for k, v in s.env.items()))] if s.env else []
        for k, v in pairs:
            self.put(yy, cx, k, self.a("dim"))
            self.put(yy, cx + 10, v, self.a("text"), cw - 10)
            yy += 1
        yy = self.section(yy + 1, cx, cw, "in agents")
        for r in self.tool_targets():
            if yy >= bottom - 5:
                break
            has = self.has_server(r, s.name)
            self.put(yy, cx, "✓" if has else "–", self.a("green" if has else "dim"))
            self.put(yy, cx + 2, f"{self.label(r)} · {self.where(r)}", self.a("text" if has else "dim"), cw - 2)
            yy += 1
        self.keys_block(yy + 1, cx, cw, bottom, [("t", "test: start it and list its tools"),
                                                 ("x", ("turn on" if off else "turn off") + " for every agent")])

    def side_agent(self, item, y, x, h, w, cx, cw, bottom):
        if item is None:
            self.box(y, x, h, w, [("agents", "yellow")])
            return
        if not isinstance(item, ops.Result):
            self.box(y, x, h, w, [(item.label, "yellow"), (" · not installed", "dim")])
            yy = self.wrap(y + 2, cx, cw, f"{item.label} isn't on this machine (no `{item.command}` command or "
                           f"{ops.short(item.home)}). Install it and the next sync (at login, or s) gives it every skill and tool.",
                           self.a("sub"), bottom)
            return
        t = item.target
        self.box(y, x, h, w, [(t.agent.label, "yellow"), (f" · {t.where}", "dim")])
        hx = self.put(y + 1, cx, t.agent.label, self.a("text", True)) + 1
        self.chip(y + 1, hx, "ERROR" if item.error else "OUT OF DATE" if item.pending else "UP TO DATE",
                  "chip_red" if item.error else "chip_peach" if item.pending else "chip_green")
        yy = y + 3
        if item.error:
            yy = self.wrap(yy, cx, cw, item.error, self.a("red"), bottom)
        owned = self.state.get(t.key, {})
        yy = self.section(yy, cx, cw, "kaushal added")
        for k, label in (("skills", "skills"), ("mcp", "tools")):
            names = owned.get(k, [])
            self.put(yy, cx, label, self.a("dim"))
            self.put(yy, cx + 10, ", ".join(names) if names else "none", self.a("text" if names else "dim"), cw - 10)
            yy += 1
        if item.changes:
            yy = self.section(yy + 1, cx, cw, "a sync would")
            for c in item.changes:
                if yy >= bottom - 4:
                    break
                self.put(yy, cx, ("· " if c.startswith("skip ") else "→ ") + c, self.a("dim" if c.startswith("skip ") else "peach"), cw)
                yy += 1
        self.keys_block(yy + 1, cx, cw, bottom, [("s", "sync every agent"), ("Enter", "open its folder"),
                                                 ("u", "take back what kaushal added here")])

    def statusline(self):
        h, w = self.scr.getmaxyx()
        y = h - 1
        kind = {"NORMAL": "chip_peach", "FILTER": "chip_sky", "CONFIRM": "chip_red", "NEW": "chip_green"}.get(self.mode, "chip_peach")
        busy = self.busy and self.mode == "NORMAL"
        x = self.chip(y, 1, "BUSY" if busy else self.mode, "chip_teal" if busy else kind)
        if self.input:
            prompt, buf, _ = self.input
            x = self.put(y, x + 1, prompt, self.a("dim"))
            x = self.put(y, x, buf, self.a("text", True))
            self.put(y, x, "▏", self.a("peach", True))
            return
        if self.confirm:
            self.put(y, x + 1, self.confirm[0] + "  y / n", self.a("text", True))
            return
        if self.toast_msg and time.time() - self.toast_at < 4:
            self.put(y, x + 2, self.toast_msg, self.a({"ok": "green", "warn": "peach", "err": "red", "info": "sky"}[self.toast_kind]))
            return
        hints = {"skills": [("Enter", "read"), ("e", "edit"), ("n", "new"), ("x", "on/off")],
                 "tools": [("t", "test"), ("x", "on/off")], "agents": [("Enter", "open"), ("u", "take back")]}[self.tab]
        hx = x + 2
        for k, label in [("1-3", "tabs"), *hints, ("s", "sync"), ("d", "doctor"), ("?", "keys"), ("q", "quit")]:
            if hx + len(k) + len(label) + 4 > w - 2:
                break
            hx = self.chip(y, hx, k, "key")
            hx = self.put(y, hx, label, self.a("dim")) + 2

    def panel(self, title, lines, note):
        h, w = self.scr.getmaxyx()
        bw = min(w - 4, max(60, max((len(t) for t, _ in lines), default=0) + 6))
        bh = min(h - 2, len(lines) + 5)
        y0, x0 = max(1, (h - bh) // 2), max(1, (w - bw) // 2)
        for i in range(bh):
            self.put(y0 + i, x0, " " * bw, self.a("text", sel=True))
        self.put(y0, x0 + 2, f" {title} ", self.a("chip_yellow", True))
        for i, (text, color) in enumerate(lines[: bh - 4]):
            self.put(y0 + 2 + i, x0 + 2, text, self.a(color, sel=True), bw - 4)
        self.put(y0 + bh - 1, x0 + 2, note, self.a("dim", sel=True), bw - 4)

    def draw_overlay(self, title, lines):
        self.panel(title, lines, "Esc closes")

    def draw_help(self):
        lines = []
        for title, rows in HELP:
            lines.append((title.upper(), "peach"))
            lines += [(f"  {k:<11} {d}", "text") for k, d in rows]
        self.panel("Keys", lines, "? or Esc closes · kaushal help lists the commands")

    def toast(self, msg, kind="ok"):
        self.toast_msg, self.toast_at, self.toast_kind = msg, time.time(), kind

    # ---------------------------------------------------------------- actions
    def background(self, what, work, done):
        """Runs work() off the UI thread; done(result) after, with the data reloaded."""
        if self.busy:
            self.toast(f"wait: {self.busy}", "warn")
            return
        self.busy = what

        def go():
            try:
                result = work()
            except Exception as e:   # shown to the user; the app keeps running
                result = e
            self.reload()
            self.busy = ""
            done(result)
        threading.Thread(target=go, daemon=True).start()

    def act_sync(self):
        def done(res):
            if isinstance(res, Exception):
                return self.toast(f"sync failed: {res}", "err")
            results, w = res
            changed = sum(1 for r in results if r.pending)
            errors = [r for r in results if r.error]
            if errors:
                self.toast(f"✗ {errors[0].target.agent.label}: {errors[0].error}", "err")
            else:
                self.toast(f"✓ synced: {changed} agent(s) changed, {len(results)} checked" if changed else
                           f"✓ synced: nothing to change in {len(results)} agent(s)")
        self.background("syncing every agent", lambda: ops.sync(), done)

    def act_doctor(self):
        def done(res):
            if isinstance(res, Exception):
                return self.toast(f"doctor failed: {res}", "err")
            notes, problems, summary = res
            lines = [("✓ " + summary, "green")] if not problems else []
            lines += [("✗ " + p, "red") for p in problems] + [("· " + n, "dim") for n in notes]
            lines += [("– " + a.label + ": not installed (set up by the next sync once it is)", "dim") for a in self.absent]
            self.overlay = ("kaushal doctor", lines)
        self.background("checking every agent", ops.diagnose, done)

    def act_test(self, s):
        if s is None:
            return

        def done(res):
            if isinstance(res, Exception):
                return self.toast(f"test failed: {res}", "err")
            ok, msg, tools = res
            lines = [(f"$ {s.command} {' '.join(s.args)}", "dim"), (("✓ " if ok else "✗ ") + msg, "green" if ok else "red")]
            if ok:
                lines.append((f"✓ {len(tools)} tool(s):", "green"))
                lines += [("  " + ", ".join(tools[i:i + 4]), "text") for i in range(0, len(tools), 4)]
            self.overlay = (f"test {s.name}", lines)
        self.background(f"testing {s.name}", lambda: ops.probe(s), done)

    def act_toggle(self, item):
        if self.tab not in ("skills", "tools") or item is None:
            return
        kind = "skills" if self.tab == "skills" else "servers"
        now_off = item.name not in self.w.off[kind]
        set_off(kind, item.name, now_off)

        def done(res):
            if isinstance(res, Exception):
                return self.toast(str(res), "err")
            self.toast(f"{item.name} turned off: taken out of every agent" if now_off else f"{item.name} is back in every agent",
                       "warn" if now_off else "ok")
        self.background("syncing every agent", lambda: ops.sync(), done)

    def act_take_back(self, item):
        if not isinstance(item, ops.Result):
            return

        def yes():
            self.background(f"taking back from {item.target.agent.label}", lambda: ops.sync(take_back=True, only=item.target.key),
                            lambda res: self.toast(f"took back kaushal's things from {item.target.agent.label} "
                                                   f"({item.target.where}); s gives them back", "warn"))
        self.ask(f"Take back every skill and tool kaushal added to {item.target.agent.label} ({item.target.where})?", yes)

    def act_new(self):
        def create(name):
            name = name.strip().lower()
            if not NAME_RE.match(name):
                return self.toast("a skill's name is lowercase letters, digits and dashes", "err")
            from .cli import new_skill
            try:
                path = new_skill(name)
            except FileExistsError as e:
                return self.toast(str(e), "err")
            self.outside([editor(), path])
            self.reload()
            self.tab, self.filter = "skills", ""
            self.sel["skills"] = next((i for i, s in enumerate(self.rows()) if s and s.name == name), 0)
            self.act_sync()
        self.prompt("NEW", "new skill's name: ", "", create)

    def act_edit(self, s):
        if s is None:
            return self.act_new()
        if s.origin == "yours":
            self.outside([editor(), s.file])
            return self.reload()

        def copy():
            dst = os.path.join(config_dir(), "skills", s.name)
            if os.path.exists(dst):
                return self.toast(f"{ops.short(dst)} already exists", "err")
            shutil.copytree(s.path, dst, ignore=shutil.ignore_patterns("__pycache__"))
            self.outside([editor(), os.path.join(dst, "SKILL.md")])
            self.reload()
            self.act_sync()
        self.ask(f"{s.name} is Vayu's: make your own copy in ~/.config/kaushal/skills (it replaces Vayu's) and edit that?", copy)

    def act_settings(self, s):
        if s is None:
            return
        path = os.path.join(config_dir(), f"{s.name}.toml")
        example = os.path.join(s.path, "config.example.toml")
        if not os.path.exists(path):
            os.makedirs(config_dir(), exist_ok=True)
            if os.path.exists(example):
                shutil.copyfile(example, path)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"# Settings for the {s.name} skill (read by the skill itself).\n")
        self.outside([editor(), path])
        self.reload()

    def act_open(self, item):
        if self.tab == "skills":
            if item is None:
                return self.act_new()
            return self.outside([os.environ.get("PAGER") or "less", item.file])
        if self.tab == "tools":
            return self.act_test(item)
        if isinstance(item, ops.Result):
            path = item.target.path
            opener = shutil.which("xdg-open")
            if opener:
                subprocess.Popen([opener, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                self.toast(f"opened {ops.short(path)}", "info")

    def outside(self, argv):
        """Runs a program (editor, pager) full-screen, then comes back."""
        curses.def_prog_mode()
        curses.endwin()
        try:
            subprocess.run(argv)
        except OSError as e:
            self.toast(f"{argv[0]}: {e}", "err")
        curses.reset_prog_mode()
        self.scr.clear()
        curses.curs_set(0)

    def ask(self, question, cb):
        self.mode, self.confirm = "CONFIRM", (question, cb)

    def prompt(self, mode, text, initial, cb):
        self.mode, self.input = mode, (text, initial, cb)

    # ---------------------------------------------------------------- keys
    def key(self, ch):
        if self.overlay:
            if ch in (27, ord("q"), ord("?"), 10, 13):
                self.overlay = None
            return True
        if self.confirm:
            _, cb = self.confirm
            self.confirm, self.mode = None, "NORMAL"
            if ch in (ord("y"), ord("Y"), 10, 13):
                cb()
            return True
        if self.input:
            text, buf, cb = self.input
            if ch == 27:
                self.input, self.mode = None, "NORMAL"
                if text == "/":
                    self.filter = ""
            elif ch in (10, 13):
                self.input, self.mode = None, "NORMAL"
                if text != "/":
                    cb(buf)
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                self.input = (text, buf[:-1], cb)
            elif 32 <= ch < 0x110000 and ch not in (curses.KEY_RESIZE,):
                self.input = (text, buf + chr(ch), cb)
            if text == "/" and self.input:
                self.filter = self.input[1]
                self.sel[self.tab] = 0
            return True
        rows = self.rows()
        item = self.current()
        if ch in (ord("q"), 27):
            if ch == 27 and self.filter:
                self.filter = ""
                return True
            return False
        if ch in (ord("1"), ord("2"), ord("3")):
            self.tab = TABS[ch - ord("1")]
        elif ch in (9, ord("l")):
            self.tab = TABS[(TABS.index(self.tab) + 1) % 3]
        elif ch in (curses.KEY_BTAB, ord("h")):
            self.tab = TABS[(TABS.index(self.tab) - 1) % 3]
        elif ch in (ord("j"), curses.KEY_DOWN):
            self.sel[self.tab] = min(len(rows) - 1, self.sel[self.tab] + 1)
        elif ch in (ord("k"), curses.KEY_UP):
            self.sel[self.tab] = max(0, self.sel[self.tab] - 1)
        elif ch in (ord("g"), curses.KEY_HOME):
            self.sel[self.tab] = 0
        elif ch in (ord("G"), curses.KEY_END):
            self.sel[self.tab] = max(0, len(rows) - 1)
        elif ch in (10, 13, curses.KEY_ENTER):
            self.act_open(item)
        elif ch == ord("s"):
            self.act_sync()
        elif ch == ord("d"):
            self.act_doctor()
        elif ch == ord("t") and self.tab == "tools":
            self.act_test(item)
        elif ch == ord("x"):
            self.act_toggle(item)
        elif ch == ord("n"):
            self.act_new()
        elif ch == ord("e") and self.tab == "skills":
            self.act_edit(item)
        elif ch == ord("c") and self.tab == "skills":
            self.act_settings(item)
        elif ch == ord("u") and self.tab == "agents":
            self.act_take_back(item)
        elif ch == ord("/"):
            self.prompt("FILTER", "/", self.filter, None)
        elif ch == ord("r"):
            self.reload()
            self.toast("reloaded", "info")
        elif ch == ord("?"):
            self.overlay = "help"
        return True

    def loop(self):
        curses.curs_set(0)
        self.scr.timeout(150)
        self.scr.keypad(True)
        curses.set_escdelay(25)
        while True:
            self.draw()
            try:
                ch = self.scr.get_wch()
            except curses.error:
                continue
            except KeyboardInterrupt:
                return
            code = ord(ch) if isinstance(ch, str) else ch
            if code == curses.KEY_RESIZE:
                continue
            if not self.key(code):
                return


def editor() -> str:
    return os.environ.get("VISUAL") or os.environ.get("EDITOR") or shutil.which("nvim") or shutil.which("vim") or "vi"


def run() -> int:
    try:
        curses.wrapper(lambda scr: App(scr).loop())
    except KeyboardInterrupt:
        return 130
    return 0
