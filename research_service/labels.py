"""Human-readable terminal labels shared by the plain CLI and the rich TUI."""
from __future__ import annotations

import unicodedata

_GATE_LABELS = {
    "missing_research_domains": "資料面向不齊",
    "insufficient_valid_citations": "有效引用不足",
    "historical_accuracy_below_0.50": "過去準確率低於 50%",
    "insufficient_base_rate_history": "歷史基準率不足",
}


def gate_reason(code: str) -> str:
    """Translate a gatekeeper reason code; unknown codes are shown as-is."""
    if code in _GATE_LABELS:
        return _GATE_LABELS[code]
    if code.startswith("confidence_below_"):
        return f"信心低於 {code.rsplit('_', 1)[-1]}"
    if code.startswith("annual_volatility_above_"):
        return f"年化波動高於 {code.rsplit('_', 1)[-1]}"
    return code


def gate_reasons(codes) -> str:
    return "、".join(gate_reason(code) for code in codes) or "—"


def pct(value, digits=1, sign=False) -> str:
    """A number already in percent (e.g. expected_return_pct)."""
    if value is None:
        return "—"
    return f"{value:+.{digits}f}%" if sign else f"{value:.{digits}f}%"


def ratio_pct(value, digits=2) -> str:
    """A decimal return such as 0.0342 shown as +3.42%."""
    return "—" if value is None else f"{value * 100:+.{digits}f}%"


def width(text: str) -> int:
    """Terminal display width: CJK and other wide characters take two columns."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))


def ljust(text, cells: int) -> str:
    text = str(text)
    return text + " " * max(0, cells - width(text))


def rjust(text, cells: int) -> str:
    text = str(text)
    return " " * max(0, cells - width(text)) + text
