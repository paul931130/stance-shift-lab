"""Terminal UI for `stance-shift`: arrow-key questions and a live dashboard.

Questions use questionary and the run is drawn with rich, in the style of the
TradingAgents CLI. When stdin/stdout are not a terminal (pipes, CI, tests)
both fall back to plain text, so scripted use keeps working unchanged.
"""
from __future__ import annotations

from collections import deque
from getpass import getpass
import sys

from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

DOMAIN_NAMES = {"technical": "技術面", "fundamental": "基本面", "sentiment": "情緒面", "macro": "總經面"}
GROUP_NAMES = {"A": "單次判斷", "B": "獨立投票", "C": "固定立場辯論", "D": "立場交換辯論"}
STANCE = {"BULL": "看多", "BEAR": "看空", "NEUTRAL": "中立"}
ACTION_STYLE = {"Buy": "bold green", "Sell": "bold red", "Hold": "yellow", "NoTrade": "dim"}
ACCENT = "cyan"

console = Console(highlight=False)


def is_interactive():
    return sys.stdin.isatty() and sys.stdout.isatty()


# ---------- Questions ----------

class Prompter:
    """Arrow-key questions in a terminal, numbered text questions otherwise."""

    def __init__(self, fancy=None):
        self.fancy = is_interactive() if fancy is None else fancy
        self.step = 0

    def header(self, title, hint=""):
        self.step += 1
        if self.fancy:
            body = Text(hint, style="dim") if hint else Text("")
            console.print(Panel(body, title=f"[bold {ACCENT}]步驟 {self.step}：{title}", title_align="left",
                                border_style=ACCENT, box=box.ROUNDED, padding=(0, 1)))
        elif hint:
            print(hint)

    def select(self, label, choices, default=None):
        """``choices`` is a list of (value, text). Returns the chosen value."""
        values = [value for value, _ in choices]
        default = default if default in values else values[0]
        if self.fancy:
            import questionary

            options = [questionary.Choice(text, value=value) for value, text in choices]
            answer = questionary.select(label, choices=options, default=next(o for o in options if o.value == default),
                                        qmark="›", instruction="（方向鍵選擇，Enter 確認）").ask()
            if answer is None:
                raise KeyboardInterrupt
            return answer
        return _plain(label, default, [str(value) for value in values])

    def text(self, label, default=""):
        if self.fancy:
            import questionary

            answer = questionary.text(label, default=default or "", qmark="›").ask()
            if answer is None:
                raise KeyboardInterrupt
            return answer.strip() or default
        return _plain(label, default)

    def secret(self, label, current=""):
        """A key; Enter keeps ``current``. Never echoes the value."""
        if self.fancy:
            import questionary

            hint = "（已設定，直接 Enter 保留）" if current else "（Enter 略過）"
            answer = questionary.password(f"{label}{hint}", qmark="›").ask()
            if answer is None:
                raise KeyboardInterrupt
            return answer.strip() or current
        return _plain(label, current, secret=True)

    def confirm(self, label, default=True):
        if self.fancy:
            import questionary

            answer = questionary.confirm(label, default=default, qmark="›").ask()
            if answer is None:
                raise KeyboardInterrupt
            return answer
        return _plain(f"{label} y/n", "y" if default else "n", ["y", "n"]) == "y"


def _plain(label, default="", choices=None, secret=False):
    shown = f" [{default}]" if default and not secret else (" [已設定，Enter 保留]" if default else "")
    while True:
        try:
            answer = (getpass if secret else input)(f"{label}{shown}: ").strip()
        except EOFError:
            answer = ""
        answer = answer or default
        if choices is None or answer in choices:
            return answer
        print(f"  請輸入其中之一：{' / '.join(choices)}")


def banner():
    if not is_interactive():
        print("Stance Shift Research：多代理人立場交換回測（按 Enter 採用括號內的上次答案）")
        return
    console.print(Panel(Group(
        Text("Stance Shift Research", style=f"bold {ACCENT}", justify="center"),
        Text("多代理人立場交換辯論 × 可稽核股票回測", justify="center"),
        Text(""),
        Markdown("流程：**資料 Agent** → **研究 Agent** → **中立報告** → **A/B/C/D 四組決策** → **把關** → **回測**"),
        Text("上次的答案是預設值，直接按 Enter 沿用。Ctrl+C 可隨時離開，已完成的步驟都會保存。", style="dim"),
    ), border_style=ACCENT, box=box.DOUBLE, padding=(1, 2)))


def summary(rows):
    """The chosen settings before the run starts."""
    if not is_interactive():
        return
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column(style="bold")
    for label, value in rows:
        table.add_row(label, value)
    console.print(Panel(table, title=f"[bold {ACCENT}]本次設定", title_align="left", border_style=ACCENT))


def notice(message, style="yellow"):
    if is_interactive():
        console.print(Panel(Text(message), border_style=style))
    else:
        print(message)


# ---------- Live dashboard ----------

class Dashboard:
    """Live view of one case: agents, the four decision groups, progress and messages.

    ``update(phase, **event)`` takes the same progress events as the plain
    printer, so it plugs into StanceShiftResearch.collect/resume unchanged.
    """

    def __init__(self, title, calls=(), transient=False):
        self.title, self.transient = title, transient
        self.data = {domain: ("pending", "") for domain in DOMAIN_NAMES}
        self.research = {domain: ("pending", "") for domain in DOMAIN_NAMES}
        self.stages = {"coordinator": "pending", "report": "pending", "gate": "pending", "backtest": "pending"}
        self.calls = {call["key"]: {**call, "status": "pending", "output": None} for call in calls}
        self.messages = deque(maxlen=8)
        self.progress = Progress(TextColumn("[bold]{task.description}"), BarColumn(bar_width=None),
                                 MofNCompleteColumn(), expand=True)
        self.task = self.progress.add_task("A/B/C/D 決策", total=max(len(self.calls), 1))
        self.live = None

    def set_calls(self, calls):
        self.calls = {call["key"]: {**call, "status": "pending", "output": None} for call in calls}
        self.progress.update(self.task, total=max(len(self.calls), 1), completed=0)

    def __enter__(self):
        self.live = Live(self.render(), console=console, refresh_per_second=8, screen=False, transient=self.transient)
        self.live.__enter__()
        return self

    def __exit__(self, *exc):
        if self.live:
            self.live.update(self.render())
            self.live.__exit__(*exc)

    def log(self, message):
        self.messages.append(message)

    def update(self, phase, **event):
        if phase == "collect":
            self._collect(event)
        else:
            self._run(event)
        if self.live:
            self.live.update(self.render())

    def _collect(self, event):
        if event.get("stage") == "collecting":
            self.data = {domain: ("running", "") for domain in DOMAIN_NAMES}
            self.log("四個資料 Agent 開始蒐集")
        elif event.get("stage") == "finbert":
            self.log("FinBERT 正在分析新聞標題")
        for domain, agent in (event.get("agents") or {}).items():
            status = "done" if agent.get("status") == "complete" else "warn"
            if self.data.get(domain, ("",))[0] != status:
                self.log(f"{DOMAIN_NAMES.get(domain, domain)}：{agent.get('message', '')}")
            self.data[domain] = (status, agent.get("message", ""))

    def _run(self, event):
        node = event.get("node", "")
        if node == "coordinator":
            self.stages["coordinator"] = "done"
            self.research = {domain: ("running", "") for domain in DOMAIN_NAMES}
            self.log("協調者已鎖定證據與時間邊界")
        for domain, item in (event.get("research") or {}).items():
            status = {"complete": "done", "degraded": "warn", "missing": "skip"}.get(item.get("status"), "warn")
            note = {"degraded": "未通過來源驗證，改用來源摘錄", "missing": "無符合時間邊界的資料"}.get(item.get("status"), "")
            if self.research.get(domain, ("",))[0] != status:
                self.log(f"{DOMAIN_NAMES.get(domain, domain)}研究 Agent {'完成' if status == 'done' else note}")
            self.research[domain] = (status, note)
        if node == "neutral_report_locked":
            self.stages["report"] = "done"
            self.log("中立研究報告已鎖定，A/B/C/D 開始決策")
        for record in event.get("new_records") or []:
            call = self.calls.setdefault(record["key"], {**record})
            call.update(status="done", output=record.get("output", {}))
            output = record.get("output", {})
            self.log(f"{record['group']} {GROUP_NAMES[record['group']]} · {_who(record)} → {output.get('action')}")
        if event.get("total"):
            self.progress.update(self.task, total=event["total"], completed=event.get("completed", 0))
        if node == "gatekeeper_decisions_locked":
            self.stages["gate"] = "done"
            self.log("把關完成，開始回測")
        if node == "backtest_and_memory_write":
            self.stages["backtest"] = "done"
        self._mark_running()

    def _mark_running(self):
        for call in self.calls.values():
            if call["status"] == "running":
                call["status"] = "pending"
        if self.stages["report"] != "done" or self.stages["gate"] == "done":
            return
        # The next unfinished call in each group is the one the engine runs next.
        for group in "ABCD":
            pending = [c for c in self.calls.values() if c["group"] == group and c["status"] == "pending"]
            if pending:
                pending[0]["status"] = "running"
                if group == "B":
                    for call in pending[1:]:
                        call["status"] = "running"

    # ----- rendering -----

    def render(self):
        layout = Layout()
        layout.split_column(Layout(self._header(), size=3), Layout(name="body"),
                            Layout(self.progress, size=1), Layout(self._messages(), size=10))
        layout["body"].split_row(Layout(self._agents(), ratio=2), Layout(self._groups(), ratio=5))
        return layout

    def _header(self):
        return Panel(Text(self.title, style="bold", justify="center"), border_style=ACCENT, box=box.HEAVY)

    def _agents(self):
        table = Table(box=box.SIMPLE_HEAD, expand=True, show_edge=False)
        table.add_column("Agent")
        table.add_column("狀態", justify="right")
        for domain, name in DOMAIN_NAMES.items():
            table.add_row(f"資料 · {name}", _status(self.data[domain][0]))
        for domain, name in DOMAIN_NAMES.items():
            table.add_row(f"研究 · {name}", _status(self.research[domain][0]))
        table.add_row("協調者", _status(self.stages["coordinator"]))
        table.add_row("中立報告", _status(self.stages["report"]))
        table.add_row("把關", _status(self.stages["gate"]))
        table.add_row("回測", _status(self.stages["backtest"]))
        return Panel(table, title="Agent 狀態", border_style="blue")

    def _groups(self):
        columns = Table.grid(expand=True, padding=(0, 1))
        for _ in "ABCD":
            columns.add_column(ratio=1)
        panels = []
        for group in "ABCD":
            table = Table(box=None, show_header=False, expand=True, padding=(0, 0))
            table.add_column(no_wrap=True, overflow="ellipsis")
            table.add_column(justify="right", no_wrap=True)
            for call in (c for c in self.calls.values() if c["group"] == group):
                output = call.get("output") or {}
                action = output.get("action")
                if call["status"] == "done":
                    cell = Text(action or "—", style=ACTION_STYLE.get(action, ""))
                elif call["status"] == "running":
                    cell = Spinner("dots", style=ACCENT)
                else:
                    cell = Text("·", style="dim")
                table.add_row(_who(call), cell)
            panels.append(Panel(table, title=f"{group} {GROUP_NAMES[group]}", border_style="magenta" if group == "D" else "white"))
        columns.add_row(*panels)
        return Panel(columns, title="四組決策", border_style="blue")

    def _messages(self):
        text = Text("\n".join(self.messages) or "等待開始…", style="dim")
        return Panel(text, title="訊息", border_style="blue")


def _who(call):
    kind = call.get("kind")
    if kind == "debate":
        return f"R{call.get('round')} {STANCE.get(call.get('stance'), call.get('stance'))}"
    return {"decision": "決策", "sample": f"第 {call.get('sample')} 票", "adjudication": "裁決"}.get(kind, kind or "")


def _status(status):
    return {"pending": Text("等待", style="dim"), "running": Spinner("dots", text="執行中", style=ACCENT),
            "done": Text("✓ 完成", style="green"), "warn": Text("! 注意", style="yellow"),
            "skip": Text("— 無資料", style="dim")}.get(status, Text(status))


def result_table(result):
    """The four final decisions and the 60-day backtest as one colored table."""
    backtest = {row["group"]: row for row in result["backtest"]
                if row.get("horizon") == 60 and row.get("cost_model") == "zero"
                and row.get("decision_layer", "gated") == "gated"}
    table = Table(title=f"{result['ticker']} · {result['analysis_date']} · {result['model']}",
                  box=box.ROUNDED, header_style=f"bold {ACCENT}", title_style="bold")
    table.add_column("組別", no_wrap=True)
    table.add_column("決策", justify="center")
    table.add_column("預期報酬", justify="right")
    table.add_column("信心", justify="right")
    table.add_column("60 日回測", justify="center")
    table.add_column("把關原因")
    for group, item in result["decisions"].items():
        row = backtest.get(group, {})
        if row.get("status") == "pending":
            outcome = Text("尚未到期", style="dim")
        elif row:
            correct = row.get("correct")
            outcome = Text({True: "✓ 方向正確", False: "✗ 方向錯誤", None: "不計方向"}[correct],
                           style={True: "green", False: "red", None: "dim"}[correct])
        else:
            outcome = Text("—", style="dim")
        action = item["action"] or "—"
        table.add_row(f"{group} {item['name']}", Text(action, style=ACTION_STYLE.get(action, "")),
                      _pct(item["expected_return_pct"]), _num(item["confidence"]), outcome,
                      "、".join(item["gate_reasons"]) or "—")
    return table


def _pct(value):
    return "—" if value is None else f"{value:g}%"


def _num(value):
    return "—" if value is None else f"{value:g}"
