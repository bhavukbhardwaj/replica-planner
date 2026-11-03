"""Provider list lives in config (ConfigMap in-cluster); env can override the active one."""
import os
from pathlib import Path

import yaml

from app.models.base import ModelClient
from app.models.fake import FakeModel
from app.models.openai_compat import OpenAICompatModel


def build_model() -> ModelClient:
    path = Path(os.environ.get("PROVIDER_CONFIG_PATH",
                               Path(__file__).resolve().parent.parent / "config" / "providers.yaml"))
    cfg = yaml.safe_load(path.read_text())
    name = os.environ.get("MODEL_PROVIDER") or cfg["active"]
    p = cfg["providers"][name]
    if p["kind"] == "fake":
        return FakeModel()
    if p["kind"] == "openai_compat":
        base = os.environ.get("MODEL_BASE_URL") or p["base_url"]
        model_name = os.environ.get("MODEL_NAME") or p["model"]
        return OpenAICompatModel(base, model_name, p.get("timeout_s", 60))
    raise ValueError(f"unknown provider kind for {name!r}")
