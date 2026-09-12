"""Single-owner credentials: write-only API, private atomic storage, shared by both clients."""
import json
import os
from pathlib import Path
import threading

FIELDS = {
    "SEC_USER_AGENT": "SEC 研究名稱與聯絡信箱", "FRED_API_KEY": "FRED API key",
    "ALPHA_VANTAGE_API_KEY": "Alpha Vantage API key", "FINNHUB_API_KEY": "Finnhub API key",
    "OPENROUTER_API_KEY": "OpenRouter API key", "OPENAI_API_KEY": "OpenAI API key",
    "GEMINI_API_KEY": "Gemini API key", "RESEARCH_MODEL": "預設模型",
    "FNSPID_NEWS_PATH": "伺服器內 FNSPID CSV 路徑",
    "ALPHA_VANTAGE_NEWS_PATH": "伺服器內 Alpha Vantage 新聞快取 CSV 路徑（免消耗 API 額度）",
}


class Settings:
    def __init__(self, root):
        self.path = Path(root) / "private" / "settings.json"
        self.lock = threading.RLock()
        if self.path.exists():
            for key, value in self._read().items():
                if key in FIELDS:
                    os.environ[key] = value

    def _read(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def public(self):
        return {"fields": [{"name": key, "label": label, "configured": bool(os.getenv(key, "")),
                            "secret": key.endswith("KEY")} for key, label in FIELDS.items()],
                "storage": "server_private", "restart_required": False,
                "note": "留白保留原值；勾選清除才刪除。FinBERT 在本機執行，不需要 HF_TOKEN。"}

    def save(self, values, clear=()):
        if not isinstance(values, dict) or not isinstance(clear, list) or any(key not in FIELDS for key in [*values, *clear]):
            raise ValueError("設定包含不支援的欄位")
        changes = {}
        for key, value in values.items():
            if not isinstance(value, str) or len(value) > 2000 or any(c in value for c in ("\n", "\r", "\x00")):
                raise ValueError("設定值須為單行文字，且不超過 2000 字元")
            if value.strip():
                changes[key] = value.strip()
        changes.update({key: "" for key in clear})
        with self.lock:
            saved = self._read()
            saved.update(changes)
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = self.path.with_suffix(".tmp")
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(saved, handle, ensure_ascii=False)
            os.replace(temporary, self.path)
            for key, value in changes.items():
                os.environ[key] = value
        return self.public()
