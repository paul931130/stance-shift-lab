"""Runtime weight checks; endpoint credentials never enter the identity audit."""
import os

from .gputw import ollama_base_url
from .storage import now


class ModelIdentityError(RuntimeError):
    pass


def resolve_ollama_identity(model):
    # Import lazily: the inventory route also uses the model transport helpers.
    from .web.ollama import get_json
    endpoint = (ollama_base_url() or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
    headers = {}
    if os.getenv("GPUTW_OLLAMA_API_KEY", "").strip():
        headers["Authorization"] = "Bearer " + os.getenv("GPUTW_OLLAMA_API_KEY").strip()
    try:
        inventory = get_json(endpoint + "/api/tags", headers=headers)
    except Exception as error:
        raise ModelIdentityError(f"無法核對模型權重（{type(error).__name__}）；未放行推理") from error
    name = model.removeprefix("ollama/")
    matches = [item for item in inventory.get("models", []) if item.get("name") == name]
    if len(matches) != 1 or not matches[0].get("digest"):
        raise ModelIdentityError("模型未安裝或沒有唯一的權重 digest；未放行推理")
    return {"id": model, "digest": matches[0]["digest"]}


def verify_model_identity(config, probe=resolve_ollama_identity):
    model = config["protocol"]["model"]
    expected = config.get("model_identity") or {}
    if expected.get("id") != model or not expected.get("digest"):
        raise ModelIdentityError("工作沒有與模型名稱相符的凍結 digest；請重新建立工作")
    observed = probe(model)
    if observed.get("id") != model or observed.get("digest") != expected["digest"]:
        raise ModelIdentityError("目前模型權重與工作凍結的 digest 不符；未放行推理")
    return {"checked_at": now(), "id": model, "digest": observed["digest"], "status": "pass"}
