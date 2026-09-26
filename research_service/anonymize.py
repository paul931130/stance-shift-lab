"""Replace a study company's identity with ``ASSET`` in everything a model reads.

Anonymized runs test for training-data memorization: if a model does as well
without knowing which company it analyses, it is reading the evidence rather
than recalling the stock's later performance. That only holds when the
company cannot be recognised, so beyond the ticker this also removes company
names, legal names and chief executives.

Known limit: product and brand names (iPhone, Azure, GeForce, Big Mac, ...)
are left in place; listing them all is open-ended and would also rewrite
ordinary text. Report anonymized results with that caveat.

Matching is whole-word, so the ticker ``GE`` does not alter ``CHANGE`` or
``GEOPOLITICAL``. Tickers match case-sensitively (``ge`` is a common
fragment); names and executives match case-insensitively.
"""
import re

from .protocol import COMPANY_NAMES

PLACEHOLDER = "ASSET"

# Identifiers beyond COMPANY_NAMES, which drives news-relevance scoring and is
# deliberately left unchanged here. Executives are included because a CEO's
# name identifies the company as surely as its ticker.
EXTRA_IDENTIFIERS = {
    "AAPL": ("Apple Inc", "Tim Cook"),
    "NVDA": ("NVIDIA Corporation", "NVIDIA Corp", "Jensen Huang"),
    "GOOGL": ("Alphabet Inc", "Sundar Pichai"),
    "MSFT": ("Microsoft Corporation", "Microsoft Corp", "Satya Nadella"),
    "AMZN": ("Amazon.com", "Andy Jassy", "Jeff Bezos"),
    "JPM": ("JPMorgan Chase", "JP Morgan Chase", "J.P. Morgan", "Jamie Dimon"),
    "MCD": ("McDonald's", "McDonalds", "Chris Kempczinski"),
    "INTC": ("Intel Corporation", "Intel Corp", "Pat Gelsinger", "Lip-Bu Tan"),
    "GE": ("General Electric Company", "GE Vernova", "GE HealthCare", "Larry Culp"),
    "ASTS": ("AST SpaceMobile",),
    "LLY": ("Eli Lilly and Company",),
}
# Ticker forms as they appear in news: NVDA, $NVDA, NASDAQ:NVDA.
_EDGE_BEFORE, _EDGE_AFTER = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"


def identifiers(ticker):
    """Every name that must not reach an anonymized prompt, longest first."""
    names = {*COMPANY_NAMES.get(ticker, ()), *EXTRA_IDENTIFIERS.get(ticker, ())}
    return sorted(names, key=len, reverse=True)


def _pattern(ticker):
    names = "|".join(re.escape(name) for name in identifiers(ticker))
    ticker_part = rf"{_EDGE_BEFORE}\$?{re.escape(ticker)}{_EDGE_AFTER}"
    # Names first: "GE Aerospace" must be replaced whole, not as "ASSET Aerospace".
    name_part = rf"{_EDGE_BEFORE}(?i:{names}){_EDGE_AFTER}" if names else None
    return re.compile(f"{name_part}|{ticker_part}" if name_part else ticker_part)


def anonymize(value, ticker):
    """Return ``value`` with the company's identity replaced in every string.

    Walks dicts and lists so only string values change; keys, numbers and
    evidence IDs keep their structure.
    """
    pattern = _pattern(ticker)

    def walk(item):
        if isinstance(item, str):
            return pattern.sub(PLACEHOLDER, item)
        if isinstance(item, list):
            return [walk(element) for element in item]
        if isinstance(item, dict):
            return {key: walk(element) for key, element in item.items()}
        return item

    return walk(value)
