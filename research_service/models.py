"""Auditable JSON model calls. Never silently substitute simulated inference."""
from copy import deepcopy
import json
import os
import re
from decimal import Decimal, ROUND_HALF_UP
import threading
import time
from urllib.request import Request, urlopen

from .data import digest
from .protocol import DESIGNS, NUMERIC_CLAIM_VERSIONS, STRICT_VALIDATION_VERSIONS, SWITCH_ROUND, visible_history

_gputw_opener = None
_gputw_lock = threading.Lock()


def gputw_urlopen(request, timeout):
    """Open a request, passing a GPUtw `unlisted` port's password page when configured.

    GPUTW_OLLAMA_PASSWORD logs in once via GPUtw's share-login form and reuses
    the resulting cookie; without it this is a plain urlopen.
    """
    global _gputw_opener
    password = os.getenv("GPUTW_OLLAMA_PASSWORD", "").strip()
    match = re.match(r"https://(\d+)-([0-9a-f-]{36})\.gputw\.ai", request.full_url)
    if not password or not match:
        return urlopen(request, timeout=timeout)
    with _gputw_lock:
        if _gputw_opener is None:
            from http.cookiejar import CookieJar
            from urllib.parse import urlencode
            from urllib.request import HTTPCookieProcessor, build_opener
            jar = CookieJar()
            opener = build_opener(HTTPCookieProcessor(jar))
            # GPUtw's edge rejects Python's default urllib User-Agent with 403.
            opener.addheaders = [("User-Agent", "stance-shift-lab/1.0")]
            form = urlencode({"password": password, "instanceId": match.group(2), "port": match.group(1)}).encode()
            opener.open(Request("https://gputw.ai/api/share/login", data=form,
                                headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=timeout).close()
            # Cache only a real session, so one failed login is retried next call.
            if not len(jar):
                raise PermissionError("GPUtw 密碼頁登入失敗；請確認 GPUTW_OLLAMA_PASSWORD")
            _gputw_opener = opener
        opener = _gputw_opener
    return opener.open(request, timeout=timeout)


BACKTEST_HORIZONS = tuple(sorted({n for design in DESIGNS.values() for n in design["horizons"]}))


DEFAULT_MODEL_TIMEOUT_SECONDS = 240
DEFAULT_MODEL_CONTEXT_LENGTH = 8192


def _bounded_integer(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def model_timeout_seconds():
    """Return the provider timeout without allowing an unsafe/unbounded value."""
    return _bounded_integer("RESEARCH_MODEL_TIMEOUT_SECONDS", DEFAULT_MODEL_TIMEOUT_SECONDS, 10, 3600)


def model_context_length():
    """Return the explicit Ollama context length used for every chat request."""
    return _bounded_integer("RESEARCH_MODEL_CONTEXT_LENGTH", DEFAULT_MODEL_CONTEXT_LENGTH, 1024, 131072)


# The supplied SEC facts are point-in-time XBRL fields.  In particular,
# ``NetIncomeLoss`` is a taxonomy name and cannot be rewritten as a claim
# that the company made a loss.  These phrases need comparison evidence that
# the frozen fundamental input deliberately does not provide.
UNSUPPORTED_FINANCIAL_INTERPRETATION = re.compile(
    r"\b(?:net\s+(?:income\s+)?loss|net\s+profit|profitability|profitable|financial\s+(?:pressure|strength|health)|"
    r"(?:strong|weak|high|low|significant|large)\s+(?:revenue(?:s)?|cash\s+flow|fundamentals?|assets?|liabilit(?:y|ies)|net\s+income)|"
    r"(?:revenue(?:s)?|cash\s+flow|fundamentals?|assets?|liabilit(?:y|ies)|net\s+income)\s+"
    r"(?:growth|grew|increas(?:e|ed|ing)|decreas(?:e|ed|ing)|declin(?:e|ed|ing)|improv(?:e|ed|ing)|deteriorat(?:e|ed|ing))|"
    r"(?:increase|decrease|decline|improvement|deterioration)\s+in\s+"
    r"(?:revenue(?:s)?|cash\s+flow|fundamentals?|assets?|liabilit(?:y|ies)|net\s+income))\b", re.IGNORECASE)


def _short_text(value, limit):
    """Bound model-only text without changing the immutable source snapshot."""
    text = str(value or "")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _compact_evidence_item(item, *, sentiment_headline_limit=240, include_sentiment_labels=True,
                           decision_view=False):
    """Return the minimum auditable evidence needed in an LLM prompt.

    URLs, provider metadata, and long Alpha Vantage summaries remain in the
    immutable dataset and export.  They consume scarce local-model context but
    do not help a model cite a supplied evidence ID.  Sentiment work is
    deliberately title-level because FinBERT scores the headline.
    """
    domain = str(item.get("domain", ""))
    compact = {"evidence_id": item.get("evidence_id"), "domain": domain}
    if not decision_view:
        compact["available_at"] = item.get("available_at")
    if domain == "sentiment" and item.get("source_type") == "finbert_indicator":
        compact.update({"claim": item.get("claim"), "value": item.get("value"),
                        "evidence_scope": item.get("evidence_scope")})
    elif domain == "sentiment":
        compact.update({
            "headline": _short_text(item.get("headline") or item.get("claim"), sentiment_headline_limit),
            "evidence_scope": item.get("evidence_scope"),
            "sentiment_score": item.get("sentiment_score"),
        })
        if not decision_view:
            compact["relevance_score"] = item.get("relevance_score")
        if include_sentiment_labels:
            compact.update({"sentiment_label": item.get("sentiment_label"), "direction": item.get("direction")})
    else:
        # Financial claims are never abbreviated: their numbers, units, and
        # periods must be copied exactly by the research agent.
        claim = str(item.get("claim", ""))
        compact["claim"] = claim if domain == "fundamental" else _short_text(claim, 360)
        if domain == "technical" and "value" in item:
            compact["value"] = item["value"]
    number_fields = _numeric_source_fields(item)
    if number_fields:
        compact["numeric_fields"] = number_fields
    return {key: value for key, value in compact.items() if value not in (None, "")}


def _numeric_source_fields(item):
    """Expose typed source values so numeric claims can be checked by ID/metric/period/unit."""
    domain = item.get("domain")
    fields = []

    def add(metric, period, unit, value):
        if (isinstance(metric, str) and metric.strip() and isinstance(period, str) and period.strip()
                and isinstance(unit, str) and unit.strip() and isinstance(value, (int, float, Decimal))
                and not isinstance(value, bool)):
            fields.append({"metric": metric, "period": period, "unit": unit, "value": value})

    if domain == "fundamental":
        metric = str(item.get("metric", "")).strip()
        if metric:
            add(metric, str(item.get("current_period", "")), "USD", item.get("current_value"))
            add(metric, str(item.get("prior_period", "")), "USD", item.get("prior_value"))
            if item.get("change_pct") is not None and item.get("current_period") and item.get("prior_period"):
                add(f"{metric} year-over-year change", f"{item['prior_period']}..{item['current_period']}",
                    "percent", item.get("change_pct"))
        period = str(item.get("period_end", ""))
        if period:
            add("Assets", period, "USD", item.get("assets"))
            add("Liabilities", period, "USD", item.get("liabilities"))
            add("Liabilities-to-assets ratio", period, "percent", item.get("ratio_pct"))
    elif domain == "sentiment" and item.get("source_type") == "finbert_indicator":
        add(str(item.get("metric", "")), str(item.get("period", "")), str(item.get("unit", "")), item.get("value"))
    elif domain == "technical":
        metric = str(item.get("metric", "")).strip() or str(item.get("claim", "")).split("=", 1)[0].strip()
        unit = item.get("unit") or ("annualized_decimal_volatility" if metric == "volatility60_annual" else "decimal_return")
        add(metric, str(item.get("period") or item.get("available_at") or ""), str(unit), item.get("value"))
    elif domain == "macro":
        metric = str(item.get("metric", "")).strip()
        period = str(item.get("period", "")).strip()
        unit = str(item.get("unit", "")).strip()
        value = item.get("value")
        if not metric or not period or not unit or value is None:
            claim = str(item.get("claim", ""))
            metric = metric or claim.split(":", 1)[0].strip()
            period_match = re.search(r"觀測期間\s+(\d{4}-\d{2}-\d{2})", claim)
            period = period or (period_match.group(1) if period_match else "")
            raw_value = re.search(r":\s*(-?\d+(?:\.\d+)?)", claim)
            if value is None and raw_value:
                value = raw_value.group(1)
            unit = unit or {"FEDFUNDS": "percent_per_year", "CPIAUCSL": "index_points",
                            "UNRATE": "percent"}.get(metric, "")
        add(metric, period, unit, value)
    return fields


def compact_research_evidence(domain, items):
    """Build a bounded research-agent view while retaining full evidence for validation."""
    return [_compact_evidence_item(item) for item in items if item.get("domain") == domain]


def _compact_history(records):
    """Expose prior arguments, never their provider audit payloads, to a debate turn.

    v3-0927.1: earlier turns were cut to 60 characters and one citation, so the
    switched D round could not see the claim it must rebut and the Adjudicator
    could not check either side's evidence. Arguments are now shown whole (the
    schema already bounds them) with every citation.
    """
    compact = []
    for record in records:
        output = record.get("output", {})
        shown = {"action": output.get("action"), "expected_return_pct": output.get("expected_return_pct"),
                 "confidence": output.get("confidence"),
                 "rationale": _short_text(output.get("rationale"), 320),
                 "evidence_ids": output.get("evidence_ids", []),
                 "numeric_claims": output.get("numeric_claims", [])[:8],
                 "strongest_counterpoint": _short_text(output.get("strongest_counterpoint"), 240)}
        if output.get("rebutted_claim"):
            shown["rebutted_claim"] = _short_text(output.get("rebutted_claim"), 240)
        compact.append({"key": record.get("key"), "stance": record.get("stance"), "round": record.get("round"),
                        "output": {key: value for key, value in shown.items() if value is not None}})
    return compact


NUMBER_PATTERN = r'(?<![\w.])-?\d[\d,]*(?:\.\d+)?'
REDACTED_NUMBER = '[數值已移除]'


def validate_financial_numbers(result, evidence, context=None, redact=False):
    """Reject financial prose that introduces a number absent from the evidence it may use.

    v3-0929.1: with redact=True (last-resort after retries), unsupported numbers are
    replaced in the prose fields instead of raising, and recorded in
    result["redacted_numbers"] for audit. Decision fields are never touched.
    """
    def numbers(text):
        if not isinstance(text, str):
            return set()
        return {Decimal(value.replace(',', '')) for value in re.findall(NUMBER_PATTERN, text)}

    cited = set(result.get('evidence_ids', []))
    source = ' '.join(e['claim'] for e in evidence if e['evidence_id'] in cited)
    if not source:
        raise ValueError('財務摘要沒有可驗證的引用來源')
    text = " ".join([str(result.get("summary", "")), str(result.get("rationale", "")),
                     str(result.get("strongest_counterpoint", "")),
                     *(str(value) for value in result.get("risks", []))])
    # v3-0926.4: a number may come from any evidence the caller passed in
    # (the decision's allowed list), not only the cited items; at least one
    # real citation is still required above. v3-0926.3: a window length
    # inside an indicator name (return20 -> "20-day") and the protocol's own
    # backtest horizons are not invented numbers. Rounded or converted values
    # are still rejected.
    available = ' '.join(e['claim'] for e in evidence if isinstance(e.get('claim'), str))
    # v3-0926.7: context is everything the model was shown (the full prompt:
    # report, calibration, base rates, earlier rounds, memory). Numbers it
    # repeats from there, or from its own forecast fields, are not invented.
    if context is not None:
        available += ' ' + (context if isinstance(context, str) else json.dumps(context, ensure_ascii=False))
    supported = numbers(available)
    supported |= {Decimal(str(result[key])) for key in ("expected_return_pct", "confidence", "confidence_shift")
                  if isinstance(result.get(key), (int, float)) and not isinstance(result.get(key), bool)}
    supported |= {Decimal(value) for value in re.findall(r'(?<=[A-Za-z_])\d+(?![\d.])', available)}
    supported |= {Decimal(value) for value in BACKTEST_HORIZONS}
    # v3-0926.6: an exact fraction <-> percent conversion keeps the value
    # (0.500153 -> 50.0153%); any additional rounding is still rejected.
    supported |= {value * 100 for value in supported} | {value / 100 for value in supported}
    unsupported = numbers(text) - supported
    if unsupported and redact:
        def scrub(value):
            return re.sub(NUMBER_PATTERN, lambda m: REDACTED_NUMBER
                          if Decimal(m.group(0).replace(',', '')) in unsupported else m.group(0), value)
        for key in ("summary", "rationale", "strongest_counterpoint"):
            if isinstance(result.get(key), str):
                result[key] = scrub(result[key])
        if isinstance(result.get("risks"), list):
            result["risks"] = [scrub(risk) if isinstance(risk, str) else risk for risk in result["risks"]]
        result["redacted_numbers"] = sorted(format(value, 'f') for value in unsupported)
        return
    if unsupported:
        shown = ', '.join(sorted(format(value, 'f') for value in unsupported)[:5])
        raise ValueError(f'財務摘要包含來源未支持的數字（{shown}）；必須原樣保留數值、單位與期間')


# Words that rescale or relabel a number. Sources store raw values (USD, percent),
# so "100 billion USD" or "100%" can never be the source's "100 USD".
_SCALE_AFTER = re.compile(r"^\s*(?:thousand|million|billion|trillion|bn|mn|[kmbt]\b|千|萬|万|百萬|千萬|億|亿|兆)", re.I)
_PERCENT_AFTER = re.compile(r"^\s*(?:%|％|percent|pct\b|個百分點|百分點)", re.I)
_PERCENT_UNITS = {"percent", "percent_per_year"}
# Prose labels of the SEC metrics; a quote must not name a different metric than the one it binds.
_METRIC_WORDS = {
    "Revenue": ("revenue", "sales", "營收", "收入"),
    "NetIncomeLoss": ("net income", "net loss", "profit", "earnings", "淨利", "淨損", "盈餘", "獲利"),
    "OperatingCashFlow": ("operating cash", "cash flow", "營業現金", "現金流"),
    "Assets": ("total assets", "總資產"),
    "Liabilities": ("total liabilities", "總負債"),
}


def _strict_claim_problem(claim, quote, displayed):
    """Why a value-matching claim still misstates its source (v3-1001.x), or None."""
    for start, end, number, _ in _numeric_tokens(quote):
        if number != displayed:
            continue
        after = quote[end:end + 12]
        if _SCALE_AFTER.match(after):
            return "數字帶了倍數單位（例如 billion、億），來源是原始數值"
        if claim["unit"] in _PERCENT_UNITS and not _PERCENT_AFTER.match(after):
            return "百分比來源的數字必須寫成百分比"
        if claim["unit"] not in _PERCENT_UNITS and _PERCENT_AFTER.match(after):
            return "非百分比來源的數字被寫成百分比"
    base = claim["metric"].replace(" year-over-year change", "")
    own = _METRIC_WORDS.get(base)
    if own:
        lowered = quote.lower()
        named_other = any(word in lowered for metric, words in _METRIC_WORDS.items() if metric != base for word in words)
        if named_other and not any(word in lowered for word in own):
            return "引用的指標與文字描述的指標不同"
    return None


def validate_numeric_claims(result, evidence, redact=False, strict=False):
    """Bind narrative numbers to a cited evidence ID, metric, period, unit and source value.

    With ``strict`` (v3-1001.x) a bound number must also keep the source's scale,
    percent-ness and metric label in the quoted prose.
    """
    cited = set(result.get("evidence_ids", []))
    by_id = {item.get("evidence_id"): item for item in evidence if item.get("evidence_id")}
    prose_fields = [("summary", result.get("summary")), ("rationale", result.get("rationale")),
                    ("strongest_counterpoint", result.get("strongest_counterpoint")),
                    ("rebutted_claim", result.get("rebutted_claim"))]
    prose_fields.extend((f"risks[{index}]", value) for index, value in enumerate(result.get("risks", [])))
    prose_fields = [(name, value) for name, value in prose_fields if isinstance(value, str)]
    claims = result.get("numeric_claims", [])
    if not isinstance(claims, list):
        raise ValueError("numeric_claims 必須是陣列")

    expected_keys = {"evidence_id", "metric", "period", "unit", "value", "quote"}
    valid = []
    invalid_claim_count = 0
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != expected_keys:
            invalid_claim_count += 1
            continue
        evidence_id, quote = claim.get("evidence_id"), claim.get("quote")
        item = by_id.get(evidence_id)
        if (item is None or evidence_id not in cited or not isinstance(quote, str) or not quote
                or not any(quote in text for _, text in prose_fields)
                or not isinstance(claim.get("metric"), str) or not claim["metric"].strip()
                or not isinstance(claim.get("period"), str) or not claim["period"].strip()
                or not isinstance(claim.get("unit"), str) or not claim["unit"].strip()
                or isinstance(claim.get("value"), bool)
                or not isinstance(claim.get("value"), (int, float, Decimal))):
            invalid_claim_count += 1
            continue
        displayed = Decimal(str(claim["value"]))
        source_fields = item.get("numeric_fields") or _numeric_source_fields(item)
        supported = any(
            field.get("metric") == claim["metric"] and field.get("period") == claim["period"]
            and field.get("unit") == claim["unit"]
            and isinstance(field.get("value"), (int, float, Decimal))
            and not isinstance(field.get("value"), bool)
            and (_rounds_to_significant_figures(Decimal(str(field["value"])), displayed)
                 or (strict and _rounds_to_displayed_precision(Decimal(str(field["value"])), displayed)))
            for field in source_fields if isinstance(field, dict)
        )
        tokens = _numeric_tokens(quote)
        period_numbers = {number for _, _, number, _ in _numeric_tokens(claim["period"])}
        quote_values = [number for _, _, number, _ in tokens]
        has_claim_value = displayed in quote_values
        no_extra_values = all(number == displayed or number in period_numbers
                              or (strict and _is_label_number(quote, start, end, number))
                              for start, end, number, _ in tokens)
        if supported and has_claim_value and no_extra_values and not (
                strict and _strict_claim_problem(claim, quote, displayed)):
            valid.append(claim)
        else:
            invalid_claim_count += 1

    valid_quotes = [(claim["quote"], Decimal(str(claim["value"])),
                     {number for _, _, number, _ in _numeric_tokens(claim["period"])}) for claim in valid]
    unsupported = []
    for field_name, text in prose_fields:
        for start, end, number, raw in _numeric_tokens(text):
            if strict and _is_label_number(text, start, end, number):
                continue  # "20-day", "60 trading sessions", "2023": names a window or year, not a source value
            covered = False
            for quote, value, period_numbers in valid_quotes:
                quote_start = text.find(quote)
                if quote_start <= start and end <= quote_start + len(quote):
                    if number == value or number in period_numbers:
                        covered = True
                        break
            if not covered:
                unsupported.append({"field": field_name, "start": start, "end": end,
                                    "value": raw, "number": number})

    if (unsupported or invalid_claim_count) and not redact:
        values = {item["number"] for item in unsupported}
        if not values:
            values = {Decimal(0)}
        shown = ", ".join(format(value, "f") for value in sorted(values)[:5])
        raise ValueError(f"來源未支持的數字（{shown}）；每項需有有效 numeric_claims，並綁定 evidence_id、metric、period、unit、value 與 quote")

    if redact:
        by_field = {}
        for item in unsupported:
            if item["field"].startswith("risks["):
                match = re.fullmatch(r"risks\[(\d+)\]", item["field"])
                if match:
                    by_field.setdefault(("risk", int(match.group(1))), []).append(item)
            else:
                by_field.setdefault((item["field"], None), []).append(item)
        for (field, index), spans in by_field.items():
            text = result.get(field, "") if index is None else result.get("risks", [])[index]
            for item in sorted(spans, key=lambda row: row["start"], reverse=True):
                text = text[:item["start"]] + REDACTED_NUMBER + text[item["end"]:]
            if index is None:
                result[field] = text
            else:
                result["risks"][index] = text
        result["numeric_claims"] = valid
        result["numeric_claims_removed"] = invalid_claim_count
        result["redacted_numbers"] = sorted({item["value"] for item in unsupported})
        result["redacted_number_claims"] = [{"field": item["field"], "value": item["value"]}
                                            for item in unsupported]
    elif invalid_claim_count:
        # A schema-valid but unused claim is not evidence; never retain it as if validated.
        result["numeric_claims"] = valid


_WINDOW_AFTER = re.compile(r"^(?:-|\s)?(?:day|days|日|天|個交易日|交易日|session|sessions|trading|week|weeks|週|month|months|個月|月|quarter|quarters|季|year|years|年)", re.I)


def _is_label_number(text, start, end, number):
    """A window length or calendar year, which the source does not state as a value."""
    if number == number.to_integral_value() and 1990 <= number <= 2035:
        return True
    return number == number.to_integral_value() and 0 < number <= 365 and bool(_WINDOW_AFTER.match(text[end:end + 16]))


def _rounds_to_displayed_precision(source, displayed):
    """v3-1001.x: the source rounded half-up to the decimals the prose shows (-58.9912 -> -58.99 or -59)."""
    if displayed == 0 and source != 0:
        return False
    quantum = Decimal(1).scaleb(displayed.as_tuple().exponent)
    return source.quantize(quantum, rounding=ROUND_HALF_UP) == displayed


def _rounds_to_significant_figures(source, displayed, figures=3):
    """Accept exact values or standard half-up rounding to at most 3 significant figures."""
    if source == displayed:
        return True
    if source == 0:
        return False
    quantum = Decimal(1).scaleb(source.copy_abs().adjusted() - figures + 1)
    return source.quantize(quantum, rounding=ROUND_HALF_UP) == displayed


def _numeric_tokens(text):
    return [(match.start(), match.end(), Decimal(match.group(0).replace(",", "")), match.group(0))
            for match in re.finditer(NUMBER_PATTERN, str(text or ""))]


def validate_financial_interpretation(result, evidence=None):
    """Reject qualitative direction claims from uncomparable SEC point facts."""
    if evidence is not None:
        cited = set(result.get("evidence_ids", []))
        financial = [item for item in evidence
                     if item.get("domain") == "fundamental" and item.get("evidence_id") in cited]
        if not financial:
            return
        if all(item.get("comparative") is True for item in financial):
            return
    text = " ".join([str(result.get("summary", "")),
                     *(str(value) for value in result.get("risks", [])),
                     str(result.get("rationale", "")),
                     str(result.get("strongest_counterpoint", ""))])
    match = UNSUPPORTED_FINANCIAL_INTERPRETATION.search(text)
    if match:
        raise ValueError("財務點時欄位被改寫為未支持的品質、盈虧或趨勢判斷：" + match.group(0))


def _compact_calibration(calibration):
    """Keep deterministic directional inputs, not explanatory text repeated in the system prompt."""
    technical = calibration.get("technical", {})
    sentiment = calibration.get("sentiment", {}).get("target", {})
    compact = {
        "technical": {key: technical.get(key) for key in
                      ("return20", "mean20_vs_mean60", "annual_volatility", "direction", "strength")
                      if technical.get(key) is not None},
        "sentiment_target": {key: sentiment.get(key) for key in
                              ("count", "scored_count", "mean_score", "positive_share", "negative_share", "direction")
                              if sentiment.get(key) is not None},
    }
    if calibration.get("rules_version") == "finbert-indicators-v1":
        context = calibration.get("sentiment", {}).get("context", {})
        if context.get("mean_score") is not None:
            compact["sentiment_context"] = {"mean_score": context["mean_score"]}
    return compact


def _compact_base_rates(base_rates):
    return {key: base_rates.get(key) for key in
            ("horizon_sessions", "hold_band_pct", "horizon_sigma_pct", "basis", "positive_rate", "median_return_pct")
            if base_rates.get(key) is not None}


def evidence_aliases(evidence):
    """Short prompt-only IDs (E1, E2, ...) for the evidence a call may cite.

    v3-0927.1: models copied long IDs such as ``alpha-news-4593362d3e0499d6dc44``
    or SEC accession-number IDs with dropped or altered characters, which was the
    most common validation failure. Prompts now show these aliases and every
    answer is mapped back to the real IDs before validation and storage, so the
    stored and exported citations are unchanged.
    """
    ids = list(dict.fromkeys(item["evidence_id"] for item in evidence))
    return {evidence_id: f"E{index}" for index, evidence_id in enumerate(ids, 1)}


def alias_messages(messages, aliases):
    """Replace each quoted real evidence ID in the prompt with its alias."""
    ordered = sorted(aliases, key=len, reverse=True)
    result = []
    for message in messages:
        content = str(message.get("content", ""))
        for evidence_id in ordered:
            content = content.replace(json.dumps(evidence_id, ensure_ascii=False), json.dumps(aliases[evidence_id]))
        result.append({**message, "content": content})
    return result


def unalias_evidence_ids(result, aliases):
    """Map a model answer's cited aliases back to real IDs; unknown values stay for validation to reject."""
    if isinstance(result, dict) and isinstance(result.get("evidence_ids"), list):
        reverse = {alias: evidence_id for evidence_id, alias in aliases.items()}
        result = {**result, "evidence_ids": [reverse.get(value, value) if isinstance(value, str) else value
                                             for value in result["evidence_ids"]]}
        if isinstance(result.get("numeric_claims"), list):
            result["numeric_claims"] = [({**claim, "evidence_id": reverse.get(
                claim.get("evidence_id"), claim.get("evidence_id"))} if isinstance(claim, dict) else claim)
                for claim in result["numeric_claims"]]
    return result


def prompt_text(messages):
    """All text a prompt showed the model, for checking which numbers it was given."""
    return " ".join(str(message.get("content", "")) for message in messages)


def decision_prompt_context(report):
    """The non-evidence numeric sections the decision prompt shows the model."""
    return {"decision_calibration": _compact_calibration(report.get("decision_calibration", {})),
            "base_rates": _compact_base_rates(report.get("base_rates", {}))}


def _decision_evidence(report):
    """Give a 4K-context decision model all hard facts plus representative direct headlines.

    The report itself remains complete.  The sentiment aggregate is calculated
    over every selected direct headline; four headlines are a citation-sized
    representative view rather than a new evidence selection rule.
    """
    evidence = report.get("evidence", [])
    # Comparable SEC ratios and prior-year pairs are decision evidence. Legacy
    # point fields remain in the immutable report for audit but are excluded.
    non_sentiment = [item for item in evidence
                     if item.get("domain") != "sentiment"
                     and (item.get("domain") != "fundamental" or item.get("comparative") is True)]
    indicators = [item for item in evidence
                  if item.get("domain") == "sentiment" and item.get("source_type") == "finbert_indicator"]
    direct_sentiment = [item for item in evidence
                        if item.get("domain") == "sentiment" and item.get("evidence_scope") == "target"
                        and item.get("source_type") != "finbert_indicator"]
    return [
        *[_compact_evidence_item(item, decision_view=True) for item in non_sentiment],
        *[_compact_evidence_item(item, decision_view=True) for item in indicators],
        *[_compact_evidence_item(item, sentiment_headline_limit=80, include_sentiment_labels=False,
                                 decision_view=True) for item in direct_sentiment[:4]],
    ]


def _compact_memory(memory):
    """Return an auditable historical calibration summary without raw database rows."""
    rows = list(memory or [])
    action_counts = {}
    correct_count = 0
    resolved = 0
    returns = []
    for row in rows:
        action = row.get("action")
        if action:
            action_counts[action] = action_counts.get(action, 0) + 1
        if row.get("correct") is not None:
            resolved += 1
            correct_count += int(bool(row.get("correct")))
        if isinstance(row.get("net_return"), (int, float)):
            returns.append(float(row["net_return"]))
    recent = [{key: row.get(key) for key in ("analysis_date", "action", "correct", "net_return")}
              for row in rows[:4]]
    summary = {"count": len(rows), "resolved_count": resolved, "correct_count": correct_count,
               "action_counts": action_counts, "recent": recent}
    if returns:
        summary["mean_net_return"] = round(sum(returns) / len(returns), 6)
    return summary


def _compact_report(report):
    """Bound decision prompts while keeping the complete report immutable."""
    has_comparable_fundamentals = any(item.get("domain") == "fundamental" and item.get("comparative") is True
                                      for item in report.get("evidence", []))
    return {
        "ticker": report.get("ticker"),
        "analysis_date": report.get("analysis_date"),
        "research": {
            domain: ({"status": value.get("status"),
                      "summary": ("Deterministic SEC prior-period comparisons are supplied in the evidence list."
                                  if has_comparable_fundamentals else
                                  "SEC point facts are preserved for audit, not used as a directional decision signal."),
                      "evidence_ids": []}
                     if domain == "fundamental" and str(value.get("mode", "")).startswith("source_locked") else
                     {"status": value.get("status"), "summary": _short_text(value.get("summary", ""), 72),
                      "evidence_ids": value.get("evidence_ids", [])[:2]})
            for domain, value in report.get("research", {}).items()
        },
        **decision_prompt_context(report),
        "degraded_research_domains": report.get("degraded_research_domains", []),
        "evidence": _decision_evidence(report),
    }

DECISION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["action", "expected_return_pct", "confidence", "rationale", "evidence_ids", "risks", "numeric_claims"],
    "properties": {
        "action": {"type": "string", "enum": ["Buy", "Hold", "Sell", "NoTrade"]},
        "expected_return_pct": {"type": "number", "minimum": -60, "maximum": 60},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string", "maxLength": 700},
        "evidence_ids": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"type": "string"}},
        "risks": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 160}},
        "strongest_counterpoint": {"type": "string", "maxLength": 240},
        "numeric_claims": {"type": "array", "maxItems": 12, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["evidence_id", "metric", "period", "unit", "value", "quote"],
            "properties": {
                "evidence_id": {"type": "string"}, "metric": {"type": "string", "maxLength": 120},
                "period": {"type": "string", "maxLength": 120}, "unit": {"type": "string", "maxLength": 48},
                "value": {"type": "number"}, "quote": {"type": "string", "maxLength": 360},
            },
        }},
    },
}
RESEARCH_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "evidence_ids", "risks"],
    "properties": {
        "summary": {"type": "string", "maxLength": 1800},
        "evidence_ids": {"type": "array", "maxItems": 30, "items": {"type": "string"}},
        "risks": {"type": "array", "maxItems": 8, "items": {"type": "string", "maxLength": 300}},
        "numeric_claims": {"type": "array", "maxItems": 12, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["evidence_id", "metric", "period", "unit", "value", "quote"],
            "properties": {
                "evidence_id": {"type": "string"}, "metric": {"type": "string", "maxLength": 120},
                "period": {"type": "string", "maxLength": 120}, "unit": {"type": "string", "maxLength": 48},
                "value": {"type": "number"}, "quote": {"type": "string", "maxLength": 360},
            },
        }},
    },
}


def messages_for(call, report, records, memory, protocol):
    base_rates = report.get("base_rates", {})
    band = base_rates.get("hold_band_pct")
    band_text = f"{band:.6f}%" if isinstance(band, (int, float)) else "the neutral band stated in report.base_rates"
    claim_bound = protocol.version in NUMERIC_CLAIM_VERSIONS
    numeric_claim_instruction = (
        "Every factual number in rationale, risks, strongest_counterpoint, or rebutted_claim must have one numeric_claims item: cite the exact evidence_id, metric, period, unit and value from that evidence's numeric_fields, and copy the exact sentence fragment into quote. The quote must be present verbatim in the prose. Use source values exactly or round half-up to at most 3 significant figures; never change units, periods, or compute unsupported values. Keep expected_return_pct as a separate forecast; do not repeat it as if it were a source fact. If a number cannot be fully bound, write the sentence without that number and omit its numeric_claim. "
        if claim_bound else
        "Copy financial numbers exactly as shown in cited evidence; do not invent, round, convert units, or compute values. Use numeric_claims: [] unless a factual numeric claim is explicitly supported. "
    )
    if protocol.version in STRICT_VALIDATION_VERSIONS:
        numeric_claim_instruction = (
            "Every factual number in rationale, risks, strongest_counterpoint or rebutted_claim needs one numeric_claims "
            "item (evidence_id, metric, period, unit, value from that evidence's numeric_fields; quote = the exact prose "
            "fragment). Use the source value or round it half-up (e.g. -58.9912 as -58.99 or -59), in the source unit (no "
            "thousand/million/billion; % only for percent units), naming the same metric. expected_return_pct is a "
            "forecast, not a source fact. Drop any number you cannot bind. ")
    common = ("You are a decision agent in a fixed historical experiment. "
        f"Forecast the target's return over the next {protocol.primary_horizon} trading sessions using only the supplied report; do not use remembered future facts. "
        "Candidate action is Buy, Hold, or Sell. NoTrade is reserved for the later Gatekeeper. "
        f"Give one expected_return_pct forecast for those {protocol.primary_horizon} sessions. "
        f"Choose Hold only when that point forecast is inside the {band_text} neutral band; otherwise choose Buy or Sell even when uncertain. "
        "Hold is not a way to avoid committing; uncertainty lowers confidence, never substitutes for a forecast. Read decision_calibration before research summaries. "
        "Target evidence is direct company evidence; context news cannot decide direction by itself. Use supplied comparative SEC metrics only as stated: never invent a growth rate, benchmark, valuation, or financial-quality label; words such as growth, decline, strong, weak, profit, loss or losses need a supplied comparison that states them. Legacy SEC point facts without a comparable period are excluded from this decision payload. "
        + numeric_claim_instruction +
        "Use only supplied evidence IDs exactly; URLs and invented IDs are forbidden. Keep rationale under 320 characters and give at most 4 concise risks. "
        "Return one compact JSON object with action (Buy, Hold, Sell), expected_return_pct (-60..60), confidence (0..1), rationale (string), evidence_ids (array of supplied IDs), risks (array of strings), numeric_claims (array; [] when no narrative number is used).")
    if call.kind == "debate":
        required_action = "Buy" if call.stance == "BULL" else "Sell"
        common += (f" Your assigned debate stance is {call.stance}. Argue this stance using evidence, address counterarguments and disclose uncertainty. "
            f"For this debate turn action MUST be {required_action}; it records the assigned argument rather than the final recommendation. "
            "Also state strongest_counterpoint: the single strongest evidence-supported argument against your assigned stance. "
            "Your expected_return_pct must have the sign of your assigned stance. Do not answer Hold or NoTrade. "
            f"This is round {call.round} of exactly 3.")
        if call.group == "D" and call.round == SWITCH_ROUND:
            common += (
                " This is the role-switch round: in round 1 you argued the opposite stance, and you must now "
                "argue against yourself. Read your own round-1 turn below")
            common += (" (shown alone, never your counterpart's, so you cannot copy their wording): name the "
                       "specific claim you made in rebutted_claim as one short quoted sentence (at most 200 "
                       "characters, not the whole earlier argument), and explain in "
                       "the rationale why it no longer holds under the newly assigned stance."
                       if protocol.switch_isolation else
                       " and your counterpart's: name the specific claim you made in rebutted_claim as one short "
                       "sentence (at most 200 characters) and explain in "
                       "the rationale why it no longer holds under the newly assigned stance.")
            common += (" State confidence_shift: your new confidence minus your round-1 confidence, signed toward "
                       "the newly assigned stance, from -1 to 1. A value near 0 means the switch changed little; "
                       "do not default to 0 without justifying it in the rationale.")
            if protocol.version in STRICT_VALIDATION_VERSIONS:
                common += (" rebutted_claim must be copied word for word from your own round-1 rationale, "
                           "strongest_counterpoint or risks; confidence_shift must equal this turn's confidence "
                           "minus your round-1 confidence exactly.")
    elif call.kind == "adjudication":
        common += (" You are the neutral Adjudicator. Weigh the complete debate without favoring speaker order. "
            "Assigned Bull/Bear counts are not evidence. For each side, check its cited evidence IDs against the evidence list in the report: "
            "an argument counts only as far as the cited evidence actually supports it, and a claim with no supporting evidence counts for nothing. "
            "Decide from the original evidence and calibration, using the debate to find which evidence matters, not from how forcefully or how often a side argued. "
            "Compare forecast magnitudes against that evidence. Maturity memory is prior-experiment calibration, not current-case evidence; a tie is not abstention.")
    # A and every B sample deliberately receive byte-identical prompts and no memory.
    payload = {"report": _compact_report(report),
               "history": _compact_history(visible_history(call, records, protocol))}
    if call.kind == "adjudication":
        payload["matured_same_group_memory"] = _compact_memory(memory)
    return [{"role": "system", "content": common}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)}]


def output_schema_for(messages):
    system = messages[0]["content"]
    if "neutral research agent" in system:
        return RESEARCH_SCHEMA
    schema = deepcopy(DECISION_SCHEMA)
    schema["properties"]["action"]["enum"] = ["Buy", "Hold", "Sell"]
    if "action MUST be Buy" in system:
        schema["properties"]["action"]["enum"] = ["Buy"]
        schema["properties"]["expected_return_pct"] = {"type": "number", "exclusiveMinimum": 0, "maximum": 60}
        schema["required"].append("strongest_counterpoint")
    elif "action MUST be Sell" in system:
        schema["properties"]["action"]["enum"] = ["Sell"]
        schema["properties"]["expected_return_pct"] = {"type": "number", "minimum": -60, "exclusiveMaximum": 0}
        schema["required"].append("strongest_counterpoint")
    if "role-switch round" in system:
        schema["properties"]["rebutted_claim"] = {"type": "string", "minLength": 1, "maxLength": 240}
        schema["properties"]["confidence_shift"] = {"type": "number", "minimum": -1, "maximum": 1}
        schema["required"] += ["rebutted_claim", "confidence_shift"]
    return schema


GEMINI_THINKING_ALLOWANCE = 2048
RATE_LIMIT_WAITS = 6
RATE_LIMIT_MAX_WAIT_SECONDS = 90


def _completion_with_rate_limit_wait(litellm, kwargs, usage):
    """Wait out provider rate limits (HTTP 429) instead of failing the step.

    Free and low-tier quotas (e.g. 25 requests/minute) are hit quickly by
    parallel decision waves; the provider says how long to wait. Waits are
    recorded in the usage audit and never consume a protocol retry.
    """
    for wait in range(RATE_LIMIT_WAITS + 1):
        try:
            return litellm.completion(**kwargs)
        except litellm.RateLimitError as error:
            if wait >= RATE_LIMIT_WAITS:
                raise
            match = re.search(r'retry in ([\d.]+)s', str(error))
            delay = min(float(match.group(1)) + 1 if match else 15 * (wait + 1), RATE_LIMIT_MAX_WAIT_SECONDS)
            usage.setdefault("rate_limit_waits", []).append(round(delay, 1))
            time.sleep(delay)


def _gemini_thinking_required(model):
    """Gemini Pro models reject disabling thinking; Flash/Flash-Lite accept it."""
    return "-pro" in model


def _plain_json(value):
    """JSON fallback for provider objects (pydantic models or plain attribute bags)."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    return str(value)


def generate(protocol, messages, seed=None, temperature=None):
    output_schema = output_schema_for(messages)
    effective_temperature = protocol.temperature if temperature is None else temperature
    timeout_seconds = model_timeout_seconds()
    # A frozen protocol (v3-1001.x) carries its own context length; older ones read the environment.
    context_length = getattr(protocol, "model_context_length", None) or model_context_length()
    failures, attempt_audits = [], []
    for attempt in range(1, protocol.provider_retry_attempts + 1):
        usage, content = {}, ""
        attempt_started = time.monotonic()
        try:
            if protocol.model.startswith("ollama/"):
                model = protocol.model.removeprefix("ollama/")
                options = {"temperature": effective_temperature, "num_predict": protocol.max_output_tokens,
                           "num_ctx": context_length}
                if seed is not None:
                    options["seed"] = int(seed)
                # Keep the local model loaded for the duration of a queued
                # decision wave.  Ollama's short default keep-alive can unload
                # a CPU model while sibling requests are still waiting, which
                # leaves a resumable job looking permanently active.
                keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "-1")
                try:
                    keep_alive = int(keep_alive)
                except ValueError:
                    pass
                body = {"model": model, "messages": messages, "stream": False, "format": output_schema,
                    "think": False, "keep_alive": keep_alive, "options": options}
                # A GPUtw Ollama template can be used without changing the
                # experiment protocol.  The remote URL is optional and is
                # deliberately preferred only when explicitly configured.
                base = (os.getenv("GPUTW_OLLAMA_BASE_URL", "").strip()
                        or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
                headers = {"Content-Type": "application/json"}
                remote_token = os.getenv("GPUTW_OLLAMA_API_KEY", "").strip()
                if remote_token:
                    headers["Authorization"] = f"Bearer {remote_token}"
                with gputw_urlopen(Request(base + "/api/chat", data=json.dumps(body).encode(), headers=headers),
                                    timeout_seconds) as response:
                    provider_result = json.load(response)
                content = provider_result["message"]["content"]
                usage = {"prompt_tokens": provider_result.get("prompt_eval_count"),
                    "completion_tokens": provider_result.get("eval_count"), "model": provider_result.get("model"),
                    "created_at": provider_result.get("created_at"), "total_duration": provider_result.get("total_duration")}
            else:
                # Lazy import: local Ollama operation never contacts a cloud LLM.
                import litellm
                kwargs = {"model": protocol.model, "messages": messages, "temperature": effective_temperature,
                    "max_tokens": protocol.max_output_tokens,
                    "response_format": {"type": "json_schema", "json_schema": {"name": "research_output", "strict": True, "schema": output_schema}},
                    "timeout": timeout_seconds, "num_retries": 0}
                # Some providers (e.g. Gemini) reject `seed`; send it only where
                # supported and record in the audit whether it was applied.
                seed_supported = "seed" in (litellm.get_supported_openai_params(model=protocol.model) or [])
                if seed is not None and seed_supported:
                    kwargs["seed"] = int(seed)
                # Gemini 2.5 "thinks" by default and those tokens count against
                # max_tokens, truncating the JSON answer. Match the Ollama path
                # (think=False) by disabling it.
                if protocol.model.startswith("gemini/"):
                    if _gemini_thinking_required(protocol.model):
                        # Pro models cannot disable thinking: keep it low and add
                        # room for it so the visible answer keeps its full budget.
                        kwargs["reasoning_effort"] = "low"
                        kwargs["max_tokens"] = protocol.max_output_tokens + GEMINI_THINKING_ALLOWANCE
                    else:
                        kwargs["reasoning_effort"] = "disable"
                provider_result = _completion_with_rate_limit_wait(litellm, kwargs, usage)
                content = provider_result.choices[0].message.content
                # LiteLLM usage nests provider objects (e.g. token-detail wrappers);
                # flatten to plain JSON so the job state can be persisted.
                waits = usage.get("rate_limit_waits")
                usage = json.loads(json.dumps(dict(provider_result.usage), default=_plain_json))
                if waits:
                    usage["rate_limit_waits"] = waits
                usage["provider_model"] = getattr(provider_result, "model", None)
                usage["system_fingerprint"] = getattr(provider_result, "system_fingerprint", None)
                usage["seed_applied"] = seed is not None and seed_supported
                usage["max_tokens_sent"] = kwargs["max_tokens"]
                usage["reasoning_effort"] = kwargs.get("reasoning_effort")
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            # Some small local models add a short preface despite JSON mode.
            if not content.startswith("{") and "{" in content and "}" in content:
                content = content[content.find("{"):content.rfind("}") + 1]
            parsed = json.loads(content)
            from jsonschema import validate
            validate(parsed, output_schema)
            usage["client_elapsed_seconds"] = round(time.monotonic() - attempt_started, 6)
            return parsed, {"usage": usage, "prompt_hash": digest(messages), "raw_response": content,
                "seed": seed, "provider_attempts": attempt, "prior_failures": failures,
                "temperature": effective_temperature, "model_timeout_seconds": timeout_seconds,
                "model_context_length": context_length,
                "attempts": attempt_audits + [{"attempt": attempt, "status": "complete", "usage": usage}]}
        except Exception as error:
            usage.setdefault("client_elapsed_seconds", round(time.monotonic() - attempt_started, 6))
            failures.append(type(error).__name__)
            attempt_audits.append({"attempt": attempt, "status": "failed", "error_type": type(error).__name__, "usage": usage})
            if attempt >= protocol.provider_retry_attempts:
                raise
            time.sleep(.5 * attempt)


def validate_decision(result, evidence, call=None, context=None, redact_numbers=False, claim_bound=False,
                      strict=False, own_round1=None):
    allowed_actions = ("Buy", "Hold", "Sell")
    if call is not None and call.kind == "debate":
        allowed_actions = ("Buy",) if call.stance == "BULL" else ("Sell",)
    if not isinstance(result, dict) or result.get("action") not in allowed_actions:
        raise ValueError("模型未輸出有效 action")
    expected_return = result.get("expected_return_pct")
    if isinstance(expected_return, bool) or not isinstance(expected_return, (float, int)) or not -60 <= expected_return <= 60:
        raise ValueError("模型 expected_return_pct 須介於 -60 與 60")
    confidence = result.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (float, int)) or not 0 <= confidence <= 1:
        raise ValueError("模型 confidence 須介於 0 與 1")
    if not isinstance(result.get("rationale"), str) or not result["rationale"].strip():
        raise ValueError("模型未提供 rationale")
    if (not isinstance(result.get("evidence_ids"), list) or not result["evidence_ids"]
            or not all(isinstance(x, str) for x in result["evidence_ids"])):
        raise ValueError("模型 evidence_ids 格式不正確")
    if not isinstance(result.get("risks"), list) or not all(isinstance(x, str) for x in result["risks"]):
        raise ValueError("模型 risks 格式不正確")
    if call is not None and call.kind == "debate":
        if not isinstance(result.get("strongest_counterpoint"), str) or not result["strongest_counterpoint"].strip():
            raise ValueError("辯論代理人未提供 strongest_counterpoint")
        if (call.stance == "BULL" and expected_return <= 0) or (call.stance == "BEAR" and expected_return >= 0):
            raise ValueError("辯論 expected_return_pct 與指派立場不一致")
        if call.group == "D" and call.round == SWITCH_ROUND:
            if not isinstance(result.get("rebutted_claim"), str) or not result["rebutted_claim"].strip():
                raise ValueError("角色交換輪未指出被推翻的原立場主張 (rebutted_claim)")
            shift = result.get("confidence_shift")
            if isinstance(shift, bool) or not isinstance(shift, (float, int)) or not -1 <= shift <= 1:
                raise ValueError("角色交換輪 confidence_shift 須介於 -1 與 1")
            if strict and own_round1 is not None:
                validate_self_rebuttal(result, own_round1)
    cited = set(result["evidence_ids"])
    if claim_bound:
        validate_numeric_claims(result, evidence, redact=redact_numbers, strict=strict)
    elif any(item.get("domain") == "fundamental" and item.get("evidence_id") in cited for item in evidence):
        validate_financial_numbers(result, evidence, context, redact=redact_numbers)
    validate_financial_interpretation(result, evidence)
    # Every citation must exist. Allowing one invented ID to pass an 80% ratio
    # made otherwise well-formed outputs impossible to audit reliably.
    allowed = {e["evidence_id"] for e in evidence}
    result["invalid_evidence_ids"] = [x for x in result["evidence_ids"] if x not in allowed]
    if result["invalid_evidence_ids"]:
        raise ValueError('決策引用不存在的 evidence_id；請重試模型輸出')
    return result


def _words(text):
    return re.findall(r"\w+", str(text or "").lower())


def validate_self_rebuttal(result, own_round1, shift_tolerance=0.05):
    """The switch round must rebut something this agent really said in round 1, and report the real shift."""
    earlier = own_round1.get("output", own_round1)
    claim = _words(result["rebutted_claim"])
    prose = _words(" ".join([str(earlier.get("rationale", "")), str(earlier.get("strongest_counterpoint", "")),
                             *[str(r) for r in earlier.get("risks", [])]]))
    if claim:
        from difflib import SequenceMatcher
        match = SequenceMatcher(None, claim, prose, autojunk=False).find_longest_match(0, len(claim), 0, len(prose))
        if match.size < max(1, round(0.7 * len(claim))):
            raise ValueError("rebutted_claim 必須引用自己第 1 輪實際寫過的主張（至少 70% 的字詞連續相同）")
    # confidence_shift is derivable, so the system records the true change and keeps the
    # model's own figure for audit instead of failing the call (decided 2026-10-01).
    previous = earlier.get("confidence")
    if isinstance(previous, (int, float)) and not isinstance(previous, bool):
        actual = round(result["confidence"] - previous, 6)
        if abs(result["confidence_shift"] - actual) > shift_tolerance + 1e-9:
            result["confidence_shift_reported"] = result["confidence_shift"]
            result["confidence_shift"] = actual


def validate_research(result, evidence, domain, claim_bound=False, strict=False, redact=False):
    """Validate a research-agent answer before it becomes part of the frozen report."""
    if not isinstance(result, dict) or not isinstance(result.get("summary"), str) or not result["summary"].strip():
        raise ValueError("研究代理人輸出格式錯誤")
    if not isinstance(result.get("evidence_ids"), list) or not result["evidence_ids"]:
        raise ValueError("研究代理人未提供引用")
    if not isinstance(result.get("risks"), list) or not all(isinstance(risk, str) for risk in result["risks"]):
        raise ValueError("研究代理人 risks 格式錯誤")
    allowed = {item["evidence_id"] for item in evidence}
    if any(evidence_id not in allowed for evidence_id in result["evidence_ids"]):
        raise ValueError("研究代理人引用未提供的證據")
    if claim_bound:
        validate_numeric_claims(result, evidence, redact=redact, strict=strict)
    elif domain == "fundamental":
        validate_financial_numbers(result, evidence)
    if domain == "fundamental":
        validate_financial_interpretation(result, evidence)
    return result
