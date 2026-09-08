# -*- coding: utf-8 -*-
"""大模型客户端:统一封装智谱 / 通义 / DeepSeek / OpenAI 兼容接口。

- chat_text(): 返回纯文本
- chat_json(): 请求 JSON 输出并容错解析(容忍 ```json 代码块、前后杂文)
- demo_result(): 演示模式下返回 False,由上层走内置演示数据
"""
import json
import re
import time

import requests

import config


class LLMNotConfigured(Exception):
    pass


def _headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _post(base_url: str, key: str, model: str, messages: list, temperature: float,
          timeout: int = 600, max_tokens: int = 8000):
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=_headers(key), json=payload, timeout=timeout)
        except requests.RequestException as e:  # 网络错误:等待重试
            if attempt < 2:
                time.sleep(2 + attempt * 3)
                continue
            raise LLMNotConfigured(f"网络请求失败: {e}") from e
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < 2:
                time.sleep(3 + attempt * 5)
                continue
        if resp.status_code != 200:
            raise RuntimeError(f"LLM 接口返回 {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"LLM 返回格式异常: {str(data)[:300]}") from e
    raise RuntimeError("LLM 请求重试后仍失败")


def _messages(system: str, user: str):
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def chat_text(system: str, user: str, temperature: float = 0.3) -> str:
    provider, base, key, model = config.llm_settings()
    if not key:
        raise LLMNotConfigured("未配置大模型 API Key(见 .env)")
    return _post(base, key, model, _messages(system, user), temperature)


def chat_json(system: str, user: str, temperature: float = 0.1):
    """请求并解析 JSON。"""
    text = chat_text(system, user, temperature)
    return parse_json(text)


def parse_json(text: str):
    """容错解析模型输出中的 JSON。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"(\{.*\}|\[.*\])", t, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    raise ValueError(f"模型未返回合法 JSON:\n{text[:800]}")


def strip_code_block(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()
