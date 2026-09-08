# -*- coding: utf-8 -*-
"""全局配置:读取 .env(若存在),提供大模型供应商与演示模式开关。"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RULES_FILE = DATA_DIR / "rules.json"
CASES_FILE = DATA_DIR / "cases.json"
METRICS_FILE = DATA_DIR / "machine_metrics.json"
DEMO_DIR = DATA_DIR / "demo"

PROVIDER_CONF = {
    # provider: (env key of api key, base_url, default model)
    "zhipu":     ("ZHIPU_API_KEY",     "https://open.bigmodel.cn/api/paas/v4",              "glm-4.5-air"),
    "dashscope": ("DASHSCOPE_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    "deepseek":  ("DEEPSEEK_API_KEY",  "https://api.deepseek.com/v1",                       "deepseek-chat"),
    "openai":    ("OPENAI_API_KEY",    "https://api.openai.com/v1",                         "gpt-4o-mini"),
}


def demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "true").strip().lower() in ("1", "true", "yes")


def llm_settings():
    """返回 (provider, base_url, api_key, model)。未配置 key 时 api_key 为 ''。"""
    provider = os.getenv("LLM_PROVIDER", "zhipu").strip().lower()
    if provider not in PROVIDER_CONF:
        provider = "zhipu"
    env_key, base, default_model = PROVIDER_CONF[provider]
    api_key = os.getenv(env_key, "").strip()
    if provider == "openai":
        base = os.getenv("OPENAI_BASE_URL", base).strip().rstrip("/")
    model = os.getenv("LLM_MODEL", "").strip() or default_model
    return provider, base, api_key, model


def llm_ready() -> bool:
    return bool(llm_settings()[2])
