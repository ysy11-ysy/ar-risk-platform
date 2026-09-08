# -*- coding: utf-8 -*-
"""从年报文本中抽取财务科目(大模型)-> 结构化的 finance dict。"""
import json
import re

from core import prompts, llm
from core.fields import ALL_ANNUAL_KEYS, QUARTER_KEYS


def _pick_year_sections(text: str, budget: int = 90000) -> str:
    """年报全文很长:优先保留三大报表/分季度/员工/特殊事项附近章节再交给模型。"""
    anchors = ["合并资产负债表", "合并利润表", "合并现金流量表", "主要会计数据",
               "分季度主要财务数据", "员工情况", "母公司资产负债表", "母公司利润表",
               "非经常性损益", "前十名股东"]
    parts = []
    for a in anchors:
        idx = text.find(a)
        if idx >= 0:
            parts.append(text[max(0, idx - 200): idx + 12000])
    merged = "\n".join(parts) if parts else text
    return merged[:budget]


def _num(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("，", ""))
    except (TypeError, ValueError):
        return None


def _fill_from_scaled(mapping: dict, scale: float):
    """LLM 若偷懒用亿元:映射值*scale(把 value 转万元)。scale 为 1 时表示已经万元。"""
    return {k: (_num(v) * scale if v is not None else None) for k, v in mapping.items()}


def normalize(raw: dict) -> dict:
    """校验/规整 LLM 输出,得到前端可直接使用的 finance dict。"""
    out = {"year": str(raw.get("year") or ""), "company": str(raw.get("company") or ""),
           "unit": "万元", "Y0": {}, "Y1": {}, "Y2": {}, "quarter": {}, "extra": {}}
    for tag in ("Y0", "Y1", "Y2"):
        src = raw.get(tag) or {}
        for k in ALL_ANNUAL_KEYS:
            v = src.get(k)
            out[tag][k] = _num(v)
    q = raw.get("quarter") or {}
    for k in QUARTER_KEYS:
        out["quarter"][k] = _num(q.get(k))
    ex = raw.get("extra") or {}
    for k in ("top5_customer_ratio", "top1_customer_ratio", "related_sales_ratio", "pledge_ratio"):
        out["extra"][k] = _num(ex.get(k))
    out["extra"]["special_events"] = str(ex.get("special_events") or "")
    return out


def extract_finance(text: str, page_hint: str = "") -> dict:
    """返回 finance dict。LLM 不可用/失败时抛异常。"""
    sys_p, user_p = prompts.extract_finance_prompt(_pick_year_sections(text), page_hint)
    try:
        raw = llm.chat_json(sys_p, user_p, temperature=0.1)
    except llm.LLMNotConfigured:
        raise
    except Exception:
        # 重试一次(降低 temperature 再试,再失败向上抛)
        raw = llm.chat_json(sys_p, user_p, temperature=0.0)
    return normalize(raw)


def finance_to_text(fin: dict) -> str:
    """finance dict -> 给模型/展示的紧凑 JSON 文本。"""
    compact = {"year": fin.get("year"), "company": fin.get("company")}
    for tag in ("Y0", "Y1", "Y2"):
        compact[tag] = {k: v for k, v in (fin.get(tag) or {}).items() if v is not None}
    compact["quarter"] = {k: v for k, v in (fin.get("quarter") or {}).items() if v is not None}
    compact["extra"] = {k: v for k, v in (fin.get("extra") or {}).items() if v is not None and v != ""}
    return json.dumps(compact, ensure_ascii=False, indent=0)
