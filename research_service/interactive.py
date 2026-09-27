"""Interactive terminal run: `stance-shift` with no arguments.

Asks for the ticker, analysis date and model source (arrow-key menus in a
terminal, see research_service.tui), remembers the answers as the next run's
defaults, then collects data and runs A/B/C/D on a live dashboard. Environment variables STANCE_SHIFT_TICKER, STANCE_SHIFT_DATE and
RESEARCH_MODEL skip their question.
"""
from __future__ import annotations

from datetime import date
import importlib.util
import json
import os
from pathlib import Path

from .protocol import QUARTER_DATES, STUDY_TICKERS

OVERRIDES = {"model_too_small": ("allow_small_model", "模型小於 14B"),
             "sentiment_quality": ("allow_low_quality_sentiment", "新聞品質未達正式門檻"),
             "fundamental_quality": ("allow_point_fundamental", "只有舊版 SEC 基本面")}
CLOUD = {"1": ("gemini", "GEMINI_API_KEY", "gemini/gemini-2.5-flash"),
         "2": ("openrouter", "OPENROUTER_API_KEY", "openrouter/qwen/qwen3-14b"),
         "3": ("openai", "OPENAI_API_KEY", "openai/gpt-4.1-mini")}
DOMAIN_NAMES = {"technical": "技術面", "fundamental": "基本面", "sentiment": "情緒面", "macro": "總經面"}
GROUP_NAMES = {"A": "單次判斷", "B": "獨立投票", "C": "固定立場辯論", "D": "立場交換辯論"}
STANCE = {"BULL": "看多", "BEAR": "看空", "NEUTRAL": "中立"}


def load_env_files(paths=(".env", ".env.research")):
    """Read KEY=VALUE files in the current folder; real environment variables win."""
    for name in paths:
        path = Path(name)
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            # research.env.example points Ollama at the Docker host; outside a
            # container that name does not resolve, so keep the local default.
            if key.strip() == "OLLAMA_BASE_URL" and "host.docker.internal" in value and not Path("/.dockerenv").exists():
                continue
            if value and key.strip() not in os.environ:
                os.environ[key.strip()] = value


class Remembered:
    """The previous run's answers, stored next to the research data."""

    def __init__(self, root):
        self.path = Path(root) / "private" / "cli_last.json"
        try:
            self.values = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.values = {}

    def get(self, key, default=""):
        return self.values.get(key, default)

    def save(self, **values):
        self.values.update(values)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.write_text(json.dumps(self.values, ensure_ascii=False), encoding="utf-8")


MODEL_CHOICES = {
    "gemini": ["gemini/gemini-2.5-flash", "gemini/gemini-3.1-pro-preview", "gemini/gemini-2.5-pro"],
    "openrouter": ["openrouter/qwen/qwen3-14b", "openrouter/qwen/qwen3-32b"],
    "openai": ["openai/gpt-4.1-mini", "openai/gpt-4.1"],
    "ollama": ["ollama/qwen3:14b", "ollama/qwen3:8b"],
}
CUSTOM = "__custom__"


def installed_ollama_models():
    """Models on the configured Ollama (local or GPUtw); empty when unreachable."""
    try:
        from types import SimpleNamespace

        from .web.ollama import _probe_ollama

        result = _probe_ollama(SimpleNamespace(demo_mode=False, demo_model_id=""))
        return [model for model in result.get("models", []) if model.startswith("ollama/")]
    except Exception:
        return []


def pick_model(prompter, options, default):
    choices = [(model, model) for model in dict.fromkeys([*options, default]) if model]
    choices.append((CUSTOM, "自己輸入其他模型名稱…"))
    model = prompter.select("模型", choices, default)
    if model == CUSTOM:
        model = prompter.text("模型名稱（LiteLLM 格式，例如 gemini/gemini-2.5-flash）", default)
    return model


def choose_model(settings, remembered, prompter):
    if os.getenv("STANCE_SHIFT_MODEL"):
        return os.environ["STANCE_SHIFT_MODEL"]
    prompter.header("模型來源", "雲端模型 API 最簡單；GPUtw 與本機 Ollama 可跑正式協議的 qwen3:14b。")
    source = prompter.select("模型要在哪裡執行？", [
        ("1", "雲端模型 API（Gemini／OpenRouter／OpenAI）"),
        ("2", "雲端租 GPU（GPUtw 遠端 Ollama）"),
        ("3", "自己電腦的 Ollama"),
    ], remembered.get("source", "1"))
    previous = remembered.get("model", "")
    if source == "1":
        number = prompter.select("哪一家？", [(key, value[0].capitalize() if key != "2" else "OpenRouter")
                                             for key, value in CLOUD.items()], remembered.get("provider", "1"))
        provider, key, suggested = CLOUD[number]
        values = {}
        secret = prompter.secret(f"{provider} API key", os.getenv(key, ""))
        if secret and secret != os.getenv(key, ""):
            values[key] = secret
        model = pick_model(prompter, MODEL_CHOICES[provider],
                           previous if previous.startswith(provider + "/") else suggested)
        # A leftover GPUtw address would otherwise take over ollama/ models later.
        settings.save(values, clear=["GPUTW_OLLAMA_BASE_URL"])
        remembered.save(source=source, provider=number)
    else:
        if source == "2":
            url = prompter.text("GPUtw 遠端 Ollama 位址（https://…）", os.getenv("GPUTW_OLLAMA_BASE_URL", ""))
            token = prompter.secret("遠端 Ollama 存取 key", os.getenv("GPUTW_OLLAMA_API_KEY", ""))
            settings.save({"GPUTW_OLLAMA_BASE_URL": url, "GPUTW_OLLAMA_API_KEY": token or ""})
        else:
            settings.save({}, clear=["GPUTW_OLLAMA_BASE_URL"])
        installed = installed_ollama_models() if prompter.fancy else []
        model = pick_model(prompter, installed or MODEL_CHOICES["ollama"],
                           previous if previous.startswith("ollama/") else "ollama/qwen3:14b")
        remembered.save(source=source)
    return model


def ask_data_keys(settings, prompter):
    missing = [key for key in ("SEC_USER_AGENT", "FRED_API_KEY", "ALPHA_VANTAGE_API_KEY") if not os.getenv(key)]
    if not missing:
        return
    prompter.header("資料來源金鑰", "都免費；略過的面向會標成資料缺口。之後在網頁「設定模型與金鑰」也能改。")
    labels = {"SEC_USER_AGENT": "SEC 研究名稱與聯絡信箱（例如 Your Name you@example.com）",
              "FRED_API_KEY": "FRED API key", "ALPHA_VANTAGE_API_KEY": "Alpha Vantage API key"}
    values = {key: (prompter.secret(labels[key]) if key.endswith("KEY") else prompter.text(labels[key]))
              for key in missing}
    settings.save({key: value for key, value in values.items() if value})


def show_collection(event):
    if event.get("stage") == "collecting":
        print("\n[資料] 四個資料 Agent 開始蒐集…")
    elif event.get("stage") == "finbert":
        print("[資料] FinBERT 分析新聞標題中…")
    for domain, agent in (event.get("agents") or {}).items():
        key = ("agent", domain, agent.get("status"))
        if key in show_collection.seen:
            continue
        show_collection.seen.add(key)
        mark = "✓" if agent.get("status") == "complete" else "!"
        print(f"  {mark} {DOMAIN_NAMES.get(domain, domain)}：{agent.get('message', '')}")


show_collection.seen = set()


def show_step(event):
    node = event.get("node", "")
    if node == "coordinator":
        print("\n[研究] 協調者已鎖定證據與時間邊界")
    elif node.startswith("parallel_research_agents"):
        for domain, item in event.get("research", {}).items():
            if ("research", domain) in show_step.seen:
                continue
            show_step.seen.add(("research", domain))
            status = {"complete": "✓", "degraded": "!（改用來源摘錄）", "missing": "—（無資料）"}.get(item.get("status"), item.get("status"))
            print(f"  {status} {DOMAIN_NAMES.get(domain, domain)}研究 Agent")
    elif node == "neutral_report_locked":
        print("\n[決策] 中立研究報告已鎖定，A/B/C/D 開始決策")
    first = event.get("completed", 0) - len(event.get("new_records", []))
    for number, record in enumerate(event.get("new_records", []), first + 1):
        output = record.get("output", {})
        who = {"decision": "決策", "sample": f"第 {record.get('sample')} 票", "adjudication": "裁決"}.get(record["kind"])
        if record["kind"] == "debate":
            who = f"第 {record.get('round')} 輪 {STANCE.get(record.get('stance'), record.get('stance'))}"
        print(f"  [{number:>2}/{event['total']}] {record['group']} {GROUP_NAMES[record['group']]} · {who}"
              f" → {output.get('action')}  預期 {output.get('expected_return_pct')}%  信心 {output.get('confidence')}")
    if node == "gatekeeper_decisions_locked":
        print("\n[把關] 最終決策已鎖定，開始回測")


show_step.seen = set()


def progress(phase, **event):
    (show_collection if phase == "collect" else show_step)(event)


def print_result(result):
    from .tui import console, is_interactive, result_table

    if is_interactive():
        console.print(result_table(result))
        if result["degraded_research_domains"]:
            console.print(f"[yellow]注意：{'、'.join(result['degraded_research_domains'])} 研究輸出未通過來源驗證，這個案例不適合放進正式分析。")
        console.print(f"實驗 ID：[bold]{result['job_id']}[/]")
        console.print("完整紀錄與四組比較：執行 [bold]stance-shift serve[/]，瀏覽器開 "
                      f"http://127.0.0.1:8000/?tab=runs&selected={result['job_id']}")
        return
    print(f"\n=== {result['ticker']} · {result['analysis_date']} · {result['model']} ===")
    print(f"{'組別':<14}{'決策':<9}{'預期報酬':>9}{'信心':>7}  把關原因")
    for group, item in result["decisions"].items():
        reasons = "、".join(item["gate_reasons"]) or "—"
        print(f"{group} {item['name']:<11}{item['action'] or '—':<9}{_num(item['expected_return_pct']):>8}%"
              f"{_num(item['confidence']):>7}  {reasons}")
    primary = [row for row in result["backtest"] if row.get("horizon") == 60 and row.get("cost_model") == "zero"
               and row.get("decision_layer", "gated") == "gated"]
    if primary:
        print("\n60 個交易日回測（不計成本）：")
        for row in primary:
            if row.get("status") == "pending":
                print(f"  {row['group']}  尚未到期（只有 {row.get('available_sessions')} 個交易日的未來行情）")
            else:
                outcome = {True: "方向正確", False: "方向錯誤", None: "不計方向"}[row.get("correct")]
                print(f"  {row['group']}  {outcome}  報酬 {row.get('net_return')}")
    if result["degraded_research_domains"]:
        print(f"\n注意：{'、'.join(result['degraded_research_domains'])} 研究輸出未通過來源驗證，這個案例不適合放進正式分析。")
    print(f"\n實驗 ID：{result['job_id']}")
    print("完整紀錄與四組比較：執行 stance-shift serve，瀏覽器開 http://127.0.0.1:8000/?tab=runs&selected="
          + result["job_id"])


def _num(value):
    return "—" if value is None else f"{value:g}"


def planned_calls(protocol=None):
    """The decision calls a job will make, for the dashboard's four columns."""
    from .protocol import StudyProtocol, decision_plan

    return [{"key": c.key, "group": c.group, "kind": c.kind, "stance": c.stance, "round": c.round, "sample": c.sample}
            for c in decision_plan(protocol or StudyProtocol())]


def run_case(research, job_id, title, data=None):
    """Run a stored job with the live dashboard in a terminal, plain lines otherwise."""
    from .engine import protocol_from
    from .tui import Dashboard, is_interactive

    if not is_interactive():
        return research.resume(job_id, progress=progress)
    board = Dashboard(title, planned_calls(protocol_from(research.store.get(job_id)["config"]["protocol"])))
    board.data = data or {domain: ("done", "") for domain in board.data}
    with board:
        return research.resume(job_id, progress=board.update)


def _demo(research):
    from .demo import DEMO_ANALYSIS_DATE
    from .tui import banner, notice

    banner()
    notice("展示模式（RESEARCH_DEMO_MODE=true）：使用內建合成 NVDA 資料與固定回應，不連網、不呼叫模型，也不是研究結果。")
    dataset_id = research.collect("NVDA", DEMO_ANALYSIS_DATE)["id"]
    job_id = research.start("NVDA", DEMO_ANALYSIS_DATE, dataset_id=dataset_id)
    print_result(run_case(research, job_id, f"NVDA · {DEMO_ANALYSIS_DATE} · {research.model}（展示模式）"))
    return 0


def interactive(data_dir=None):
    from . import StanceShiftResearch, ResearchRunError
    from .errors import PreflightError
    from .protocol import COMPANY_NAMES
    from .tui import Dashboard, Prompter, banner, is_interactive, notice, summary

    load_env_files()
    research = StanceShiftResearch(data_dir=data_dir)
    remembered = Remembered(research.store.root)
    if research.demo_mode:
        return _demo(research)
    prompter = Prompter()
    banner()

    ticker = os.getenv("STANCE_SHIFT_TICKER")
    if not ticker:
        prompter.header("股票", f"研究股票固定為 9 檔：{' '.join(STUDY_TICKERS)}")
        ticker = prompter.select("股票", [(t, f"{t:<6} {COMPANY_NAMES[t][0]}" if prompter.fancy else t) for t in STUDY_TICKERS],
                                 remembered.get("ticker", "NVDA"))
    today = date.today().isoformat()
    analysis_date = os.getenv("STANCE_SHIFT_DATE")
    if not analysis_date:
        prompter.header("分析日", f"2021–2025 的季末（例如 {QUARTER_DATES[-1]}），或今天 {today}（當下分析，不計入正式統計）")
        dates = [(d, d) for d in reversed(QUARTER_DATES)] + [(today, f"{today}（今天，當下分析）" if prompter.fancy else today)]
        analysis_date = prompter.select("分析日", dates, remembered.get("date", QUARTER_DATES[-1]))
    ask_data_keys(research.settings, prompter)
    model = choose_model(research.settings, remembered, prompter)
    finbert_installed = bool(importlib.util.find_spec("transformers"))
    use_finbert = False
    if finbert_installed:
        prompter.header("新聞情緒", "正式實驗需要用本機 FinBERT 為每則新聞標題評分；第一次會下載約 438 MB 的模型。")
        use_finbert = prompter.confirm("用 FinBERT 分析新聞標題？", remembered.get("finbert", "y") == "y")
    else:
        notice("未安裝 FinBERT，新聞不會評分，只能當測試；要正式實驗請 pip install \".[finbert]\"")
    remembered.save(ticker=ticker, date=analysis_date, model=model, finbert="y" if use_finbert else "n")
    summary([("股票", f"{ticker}  {COMPANY_NAMES[ticker][0]}"), ("分析日", analysis_date), ("模型", model),
             ("FinBERT", "是" if use_finbert else "否"), ("資料位置", str(research.store.root))])
    if prompter.fancy and not prompter.confirm("開始？", True):
        return 0

    title = f"{ticker} · {analysis_date} · {model}"
    # The collection view is transient; run_case redraws it with the decisions.
    board = Dashboard(title, planned_calls(), transient=True) if is_interactive() else None
    try:
        if board:
            with board:
                dataset_id = research.collect(ticker, analysis_date, use_finbert=use_finbert, progress=board.update)["id"]
        else:
            dataset_id = research.collect(ticker, analysis_date, use_finbert=use_finbert, progress=progress)["id"]
    except ValueError as error:
        notice(f"[資料蒐集失敗] {error}", "red")
        return 1
    options = {}
    while True:
        try:
            job_id = research.start(ticker, analysis_date, model=model, dataset_id=dataset_id, **options)
            break
        except PreflightError as error:
            notice(f"[未通過檢查] {error}", "red")
            flag = OVERRIDES.get(error.reason)
            if not flag or not prompter.confirm(f"要允許「{flag[1]}」例外、只當敏感性測試繼續嗎？", False):
                return 1
            options[flag[0]] = True
    try:
        result = run_case(research, job_id, title, board.data if board else None)
    except ResearchRunError as error:
        notice(f"[中斷] {error}\n進度已保存。排除問題後執行：stance-shift resume {error.job_id}", "red")
        return 1
    print_result(result)
    return 0
