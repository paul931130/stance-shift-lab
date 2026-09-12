"""Pinned, offline-first headline classification with atomic dataset enrichment."""
from copy import deepcopy
from functools import lru_cache
import importlib.util
import json
import math
import os
from pathlib import Path
import sqlite3
import threading

MODEL = "ProsusAI/finbert"
REVISION = "4556d13015211d73dccd3fdd39d39232506f3e43"
PARAMETERS = {"max_length": 128, "truncation": True, "batch_size": 8, "device": "cpu"}
PROCESSING_VERSION = "headline-local-v1"
_lock = threading.RLock()


def cache_root():
    return Path(os.getenv("RESEARCH_DATA_DIR", "research-data")) / "models" / "finbert"


def status():
    folder = cache_root() / REVISION
    ready = all((folder / name).is_file() for name in ("config.json", "pytorch_model.bin", "vocab.txt"))
    return {"backend": "local", "model": MODEL, "revision": REVISION,
            "installed": all(importlib.util.find_spec(name) is not None for name in ("torch", "transformers")),
            "downloaded": ready, "token_required": False}


@lru_cache(maxsize=2)
def _load_model(folder):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True, trust_remote_code=False)
    model = AutoModelForSequenceClassification.from_pretrained(
        folder, local_files_only=True, trust_remote_code=False, weights_only=True).eval()
    return tokenizer, model


def prepare_model(progress=None):
    with _lock:
        if not status()["installed"]:
            raise ValueError("本機 FinBERT 套件尚未安裝；請重新建置研究服務")
        folder = cache_root() / REVISION
        if not status()["downloaded"]:
            if progress:
                progress(stage="downloading", message="首次下載固定版本 FinBERT（約 438 MB）；完成後可離線使用")
            from huggingface_hub import snapshot_download
            snapshot_download(MODEL, revision=REVISION, local_dir=folder, token=False,
                              allow_patterns=["config.json", "pytorch_model.bin", "vocab.txt",
                                              "tokenizer_config.json", "special_tokens_map.json"])
        if progress:
            progress(stage="loading", message="正在載入本機 FinBERT")
        return _load_model(str(folder))


def validate_scores(result):
    if isinstance(result, list) and result and isinstance(result[0], list):
        result = result[0]
    if not isinstance(result, list) or len(result) != 3:
        raise ValueError("FinBERT 必須回傳三個分類機率")
    scores = {}
    for row in result:
        if not isinstance(row, dict):
            raise ValueError("FinBERT 分類格式錯誤")
        value, label = row.get("score"), str(row.get("label", "")).lower()
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("FinBERT 機率須為 0 到 1 的有限數值")
        scores[label] = float(value)
    if set(scores) != {"positive", "negative", "neutral"} or not math.isclose(sum(scores.values()), 1, abs_tol=1e-5):
        raise ValueError("FinBERT 三類機率須合計為 1")
    return scores


def headline(item):
    text = item.get("headline")
    if not text and (item.get("source_type") == "FNSPID" or str(item.get("evidence_id", "")).startswith("fnspid-news-")):
        text = item.get("claim")
    if not text and item.get("source_type") == "alpha_vantage_news_sentiment":
        text = item.get("claim", "").split("。", 1)[0]
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"新聞 {item.get('evidence_id')} 缺少 headline；請補上標題再評分")
    return text.strip()


def score(data, requester=None, progress=None):
    from .data import digest
    # Never mutate the caller's dataset, even when the last inference fails.
    enriched = deepcopy(data)
    items = [item for item in enriched.get("evidence", []) if item.get("domain") == "sentiment"]
    if not 1 <= len(items) <= 100:
        raise ValueError("FinBERT 每次須包含 1–100 則新聞標題")
    texts = [headline(item) if requester is None else str(item.get("headline") or item["claim"]).strip() for item in items]
    signature = {"model": MODEL, "revision": REVISION, "parameters": PARAMETERS, "version": PROCESSING_VERSION}
    keys = [digest({**signature, "text": text}) for text in texts]
    completed = 0

    def update(**values):
        if progress:
            progress(total=len(items), completed=completed, **values)

    update(stage="queued", message="檢查標題與已完成評分快取")
    with _lock:
        root = cache_root()
        root.mkdir(parents=True, exist_ok=True)
        # Injected classifiers never populate the real-model cache.
        db = sqlite3.connect(":memory:" if requester else root / "scores.sqlite3")
        try:
            db.execute("CREATE TABLE IF NOT EXISTS scores (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            results = {}
            for key in keys:
                row = db.execute("SELECT value FROM scores WHERE key=?", (key,)).fetchone()
                if row:
                    results[key] = validate_scores(json.loads(row[0]))
            pending = list(dict.fromkeys(key for key in keys if key not in results))
            completed = sum(key in results for key in keys)
            if pending and not requester:
                tokenizer, model = prepare_model(update)
            for offset in range(0, len(pending), 1 if requester else PARAMETERS["batch_size"]):
                batch_keys = pending[offset:offset + (1 if requester else PARAMETERS["batch_size"])]
                batch_texts = [texts[keys.index(key)] for key in batch_keys]
                update(stage="scoring", message="在本機分析新聞標題")
                if requester:
                    batch_results = [requester(text) for text in batch_texts]
                else:
                    import torch
                    inputs = tokenizer(batch_texts, padding=True, truncation=True, max_length=PARAMETERS["max_length"], return_tensors="pt")
                    with torch.inference_mode():
                        probabilities = model(**inputs).logits.softmax(-1).tolist()
                    batch_results = [[{"label": model.config.id2label[index], "score": value} for index, value in enumerate(row)] for row in probabilities]
                for key, result in zip(batch_keys, batch_results):
                    probabilities = validate_scores(result)
                    results[key] = probabilities
                    db.execute("INSERT OR REPLACE INTO scores VALUES (?,?)", (key, json.dumps([{"label": k, "score": v} for k, v in probabilities.items()])))
                    db.commit()  # Successful batches survive a later failure.
                completed = sum(key in results for key in keys)
                update(stage="scoring", message="已保存成功評分；重試時可重用")
            for item, text, key in zip(items, texts, keys):
                scores = results[key]
                label = max(scores, key=scores.get)
                item.update(headline=text, sentiment_scores=scores, sentiment_score=scores["positive"] - scores["negative"],
                            sentiment_label=label, sentiment_input="headline", sentiment_input_hash=digest(text),
                            sentiment_method=f"{MODEL} local CPU", sentiment_revision=REVISION,
                            direction={"positive": "bullish", "negative": "bearish", "neutral": "neutral"}[label])
            enriched.setdefault("processing", {})["sentiment"] = {
                **signature, "backend": "local" if requester is None else "test_override", "items": len(items),
                "input": "headline", "input_hash": digest(texts), "score": "P(positive)-P(negative)", "complete": True}
            update(stage="complete", message="全部標題評分完成，建立獨立資料版本")
            return enriched
        except Exception as error:
            update(stage="failed", message=f"評分未完成：{type(error).__name__}；原資料未變更")
            raise
        finally:
            db.close()
