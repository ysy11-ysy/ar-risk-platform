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


def llm_concurrency() -> int:
    """大模型调用并发路数(第二步批次 / 第三步信号核验并行使用)。

    默认 3 路;若 API 频发 429 限流请调低,若额度允许可调高。
    可用环境变量 LLM_CONCURRENCY 覆盖(1~8)。
    """
    try:
        v = int(os.getenv("LLM_CONCURRENCY", "3"))
    except (TypeError, ValueError):
        v = 3
    return max(1, min(8, v))


def llm_global_concurrency() -> int:
    """全站(所有访客会话共用)的大模型并发总路数。

    关键防崩开关:同一时刻全站最多并发这么多路 LLM 请求。
    多个访客同时点击计算时,超出部分自动排队等待,而不是一起轰炸
    API 触发限流重试风暴。默认 4 路(免费额度一般 2~5 并发),1~16。
    """
    try:
        v = int(os.getenv("LLM_GLOBAL_CONCURRENCY", "4"))
    except (TypeError, ValueError):
        v = 4
    return max(1, min(16, v))


def llm_cache_enabled() -> bool:
    """是否启用『大模型结果磁盘缓存』:同公司同数据只调一次 API,之后秒回。

    关闭:设置环境变量 LLM_CACHE_DISABLE=1。
    """
    return os.getenv("LLM_CACHE_DISABLE", "").strip().lower() not in ("1", "true", "yes")


def llm_cache_ttl_days() -> float:
    """LLM 结果缓存有效期(天),默认 30 天。"""
    try:
        return max(0.1, float(os.getenv("LLM_CACHE_TTL_DAYS", "30")))
    except (TypeError, ValueError):
        return 30.0
