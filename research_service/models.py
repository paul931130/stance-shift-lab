"""Auditable JSON model calls. Never silently substitute simulated inference."""
from copy import deepcopy
import json
import os
import re
from decimal import Decimal
import time
from urllib.request import Request, urlopen

from .data import digest
from .protocol import visible_history


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
    if domain == "sentiment":
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
    return {key: value for key, value in compact.items() if value not in (None, "")}


def compact_research_evidence(domain, items):
    """Build a bounded research-agent view while retaining full evidence for validation."""
    return [_compact_evidence_item(item) for item in items if item.get("domain") == domain]


def _compact_history(records):
    """Expose prior arguments, never their provider audit payloads, to a debate turn."""
    compact = []
    for record in records:
        output = record.get("output", {})
        compact.append({
            "key": record.get("key"), "stance": record.get("stance"), "round": record.get("round"),
            "output": {"action": output.get("action"), "expected_return_pct": output.get("expected_return_pct"),
                       "rationale": _short_text(output.get("rationale"), 60),
                       "evidence_ids": output.get("evidence_ids", [])[:1],
                       "strongest_counterpoint": _short_text(output.get("strongest_counterpoint"), 50)},
        })
    return compact


def validate_financial_numbers(result, evidence):
    """Reject financial prose that introduces a number absent from its citations."""
    def numbers(text):
        if not isinstance(text, str):
            return set()
        return {Decimal(value.replace(',', '')) for value in
                re.findall(r'(?<![\w.])-?\d[\d,]*(?:\.\d+)?', text)}

    cited = set(result.get('evidence_ids', []))
    source = ' '.join(e['claim'] for e in evidence if e['evidence_id'] in cited)
    if not source:
        raise ValueError('財務摘要沒有可驗證的引用來源')
    text = " ".join([str(result.get("summary", "")), str(result.get("rationale", "")),
                     str(result.get("strongest_counterpoint", "")),
                     *(str(value) for value in result.get("risks", []))])
    unsupported = numbers(text) - numbers(source)
    if unsupported:
        raise ValueError('財務摘要包含來源未支持的數字；必須原樣保留數值、單位與期間')


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
    return {
        "technical": {key: technical.get(key) for key in
                      ("return20", "mean20_vs_mean60", "annual_volatility", "direction", "strength")
                      if technical.get(key) is not None},
        "sentiment_target": {key: sentiment.get(key) for key in
                              ("count", "scored_count", "mean_score", "direction")
                              if sentiment.get(key) is not None},
    }


def _compact_base_rates(base_rates):
    return {key: base_rates.get(key) for key in
            ("horizon_sessions", "hold_band_pct", "horizon_sigma_pct", "basis", "positive_rate", "median_return_pct")
            if base_rates.get(key) is not None}


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
    direct_sentiment = [item for item in evidence
                        if item.get("domain") == "sentiment" and item.get("evidence_scope") == "target"]
    return [
        *[_compact_evidence_item(item, decision_view=True) for item in non_sentiment],
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
        "decision_calibration": _compact_calibration(report.get("decision_calibration", {})),
        "base_rates": _compact_base_rates(report.get("base_rates", {})),
        "degraded_research_domains": report.get("degraded_research_domains", []),
        "evidence": _decision_evidence(report),
    }

DECISION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["action", "expected_return_pct", "confidence", "rationale", "evidence_ids", "risks"],
    "properties": {
        "action": {"type": "string", "enum": ["Buy", "Hold", "Sell", "NoTrade"]},
        "expected_return_pct": {"type": "number", "minimum": -60, "maximum": 60},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string", "maxLength": 700},
        "evidence_ids": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"type": "string"}},
        "risks": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 160}},
        "strongest_counterpoint": {"type": "string", "maxLength": 240},
    },
}
RESEARCH_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "evidence_ids", "risks"],
    "properties": {
        "summary": {"type": "string", "maxLength": 1800},
        "evidence_ids": {"type": "array", "maxItems": 30, "items": {"type": "string"}},
        "risks": {"type": "array", "maxItems": 8, "items": {"type": "string", "maxLength": 300}},
    },
}


def messages_for(call, report, records, memory, protocol):
    base_rates = report.get("base_rates", {})
    band = base_rates.get("hold_band_pct")
    band_text = f"{band:.6f}%" if isinstance(band, (int, float)) else "the neutral band stated in report.base_rates"
    common = ("You are a decision agent in a fixed historical experiment. "
        f"Forecast the target's return over the next {protocol.primary_horizon} trading sessions using only the supplied report; do not use remembered future facts. "
        "Candidate action is Buy, Hold, or Sell. NoTrade is reserved for the later Gatekeeper. "
        f"Give one expected_return_pct forecast for those {protocol.primary_horizon} sessions. "
        f"Choose Hold only when that point forecast is inside the {band_text} neutral band; otherwise choose Buy or Sell even when uncertain. "
        "Hold is not a way to avoid committing; uncertainty lowers confidence, never substitutes for a forecast. Read decision_calibration before research summaries. "
        "Target evidence is direct company evidence; context news cannot decide direction by itself. Use supplied comparative SEC metrics only as stated: copy their numbers exactly and never invent a growth rate, benchmark, valuation, or financial-quality label. Legacy SEC point facts without a comparable period are excluded from this decision payload. "
        "Use only supplied evidence IDs exactly; URLs and invented IDs are forbidden. Keep rationale under 320 characters and give at most 4 concise risks. "
        "Return one compact JSON object with action (Buy, Hold, Sell), expected_return_pct (-60..60), confidence (0..1), rationale (string), evidence_ids (array of supplied IDs), risks (array of strings).")
    if call.kind == "debate":
        required_action = "Buy" if call.stance == "BULL" else "Sell"
        common += (f" Your assigned debate stance is {call.stance}. Argue this stance using evidence, address counterarguments and disclose uncertainty. "
            f"For this debate turn action MUST be {required_action}; it records the assigned argument rather than the final recommendation. "
            "Also state strongest_counterpoint: the single strongest evidence-supported argument against your assigned stance. "
            "Your expected_return_pct must have the sign of your assigned stance. Do not answer Hold or NoTrade. "
            f"This is round {call.round} of exactly 3.")
        if protocol.switch_isolation and call.group == "D" and call.round == 2:
            common += (" You have deliberately not been shown any prior debate turn for this round. "
                       "Build your case for the assigned stance from the neutral report alone.")
    elif call.kind == "adjudication":
        common += (" You are the neutral Adjudicator. Weigh the complete debate without favoring speaker order. "
            "Assigned Bull/Bear counts are not evidence. Compare their support and forecast magnitude against the direct evidence and calibration. Maturity memory is prior-experiment calibration, not current-case evidence; a tie is not abstention.")
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
    return schema


def generate(protocol, messages, seed=None, temperature=None):
    output_schema = output_schema_for(messages)
    effective_temperature = protocol.temperature if temperature is None else temperature
    failures, attempt_audits = [], []
    for attempt in range(1, protocol.provider_retry_attempts + 1):
        usage, content = {}, ""
        attempt_started = time.monotonic()
        try:
            if protocol.model.startswith("ollama/"):
                model = protocol.model.removeprefix("ollama/")
                options = {"temperature": effective_temperature, "num_predict": protocol.max_output_tokens}
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
                base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
                with urlopen(Request(base + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}), timeout=240) as response:
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
                    "timeout": 240, "num_retries": 0}
                if seed is not None:
                    kwargs["seed"] = int(seed)
                provider_result = litellm.completion(**kwargs)
                content = provider_result.choices[0].message.content
                usage = dict(provider_result.usage)
                usage["provider_model"] = getattr(provider_result, "model", None)
                usage["system_fingerprint"] = getattr(provider_result, "system_fingerprint", None)
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
                "temperature": effective_temperature,
                "attempts": attempt_audits + [{"attempt": attempt, "status": "complete", "usage": usage}]}
        except Exception as error:
            usage.setdefault("client_elapsed_seconds", round(time.monotonic() - attempt_started, 6))
            failures.append(type(error).__name__)
            attempt_audits.append({"attempt": attempt, "status": "failed", "error_type": type(error).__name__, "usage": usage})
            if attempt >= protocol.provider_retry_attempts:
                raise
            time.sleep(.5 * attempt)


def validate_decision(result, evidence, call=None):
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
    cited = set(result["evidence_ids"])
    if any(item.get("domain") == "fundamental" and item.get("evidence_id") in cited for item in evidence):
        validate_financial_numbers(result, evidence)
    validate_financial_interpretation(result, evidence)
    # Every citation must exist. Allowing one invented ID to pass an 80% ratio
    # made otherwise well-formed outputs impossible to audit reliably.
    allowed = {e["evidence_id"] for e in evidence}
    result["invalid_evidence_ids"] = [x for x in result["evidence_ids"] if x not in allowed]
    if result["invalid_evidence_ids"]:
        raise ValueError('決策引用不存在的 evidence_id；請重試模型輸出')
    return result


def validate_research(result, evidence, domain):
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
    if domain == "fundamental":
        validate_financial_numbers(result, evidence)
        validate_financial_interpretation(result, evidence)
    return result
