"""Create a small real-data validation case from dated primary-source summaries.

This is a workflow check, not the formal 200-case study or a performance claim.
Only paraphrased facts and links are stored; no full third-party documents.
"""
import json
from pathlib import Path
from urllib.request import Request, urlopen
from research_service.storage import Store
from research_service.data import validate_dataset

base = "http://127.0.0.1:8000"
store = Store("research-data")
matches = [item for item in store.datasets() if item["ticker"] == "NVDA" and item["kind"] == "historical"]
if not matches:
    raise SystemExit("Download NVDA historical prices in the UI first")
data = store.dataset(matches[0]["id"])
data["evidence"] = [
    {"evidence_id": "nvda-sec-20241120-revenue", "domain": "fundamental", "available_at": "2024-11-20",
     "source": "https://www.sec.gov/Archives/edgar/data/1045810/000104581024000315/nvda-20241120.htm",
     "claim": "NVIDIA fiscal Q3 2025 revenue was approximately USD 35.1 billion, 94% above the year-earlier quarter. The release was furnished in a November 20, 2024 Form 8-K.",
     "source_type": "manual_primary_source_summary"},
    {"evidence_id": "nvda-release-20241120", "domain": "sentiment", "available_at": "2024-11-20",
     "source": "https://investor.nvidia.com/news/press-release-details/2024/NVIDIA-Announces-Financial-Results-for-Third-Quarter-Fiscal-2025/default.aspx",
     "claim": "NVIDIA's earnings announcement reported record quarterly revenue and substantial year-over-year growth. This is company-authored communication, not an independent survey of market sentiment.",
     "source_type": "company_news_summary", "sentiment_method": "LLM research agent; not FinBERT"},
    {"evidence_id": "fomc-20241218", "domain": "macro", "available_at": "2024-12-18", "vintage_date": "2024-12-18",
     "source": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20241218a.htm",
     "claim": "The December 18, 2024 FOMC statement reduced the federal funds target range by 25 basis points to 4.25–4.50 percent.",
     "source_type": "dated_policy_release_not_revised_macro_series"},
]
data["limitations"] = ["Small manually curated primary-source set for workflow validation, not a comprehensive news or macro dataset.",
    "Company-authored sentiment evidence overlaps the earnings evidence; no independent sentiment-quality claim.",
    "Historical adjusted Yahoo prices are downloaded today and are not immutable vintage prices."]
dataset_id = store.add_dataset(validate_dataset(data))
request = Request(base + "/api/jobs", data=json.dumps({"dataset_id": dataset_id, "analysis_date": "2024-12-31", "model": "ollama/gemma3:4b"}).encode(), headers={"Content-Type": "application/json"})
with urlopen(request, timeout=10) as response:
    job = json.load(response)
Path("research-data/live-validation.json").write_text(json.dumps({"job_id": job["id"], "dataset_id": dataset_id}, indent=2), encoding="utf-8")
print(json.dumps({"job_id": job["id"], "dataset_id": dataset_id, "status": job["status"]}))
