# -*- coding: utf-8 -*-
"""规则库加载:读取 data/rules.json,提供风险/信号/指标的查询与文本化。"""
import json
from functools import lru_cache
from pathlib import Path
from typing import List, Dict

from config import RULES_FILE

HIGH, WATCH, NORMAL, NA = "高风险", "关注", "正常", "未触发"


@lru_cache(maxsize=1)
def load_rules() -> dict:
    with open(RULES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data


@lru_cache(maxsize=1)
def risks() -> List[dict]:
    return load_rules().get("risks", [])


@lru_cache(maxsize=1)
def risk_map() -> Dict[str, dict]:
    return {r["id"]: r for r in risks()}


def find_signal(risk_id: str, signal_id: str) -> dict:
    return risk_map().get(risk_id, {}).get("signals", [{}])[0]


def rule_text_for_prompt(risk_ids: List[str] | None = None) -> str:
    """把(部分)风险规则转成给大模型看的紧凑文本。"""
    all_risks = risks()
    if risk_ids:
        all_risks = [r for r in all_risks if r["id"] in risk_ids]
    blocks = []
    for r in all_risks:
        sigs = []
        for s in r["signals"]:
            inds = "；".join(
                f"{i['name']}({i['formula']})" + (f"。判定:{i['threshold']}" if i.get("threshold") else "")
                for i in s["indicators"] if i.get("formula")
            )
            line = f"- 信号 {s['id']} {s['name']}(类型:{s.get('type','')}):{inds}"
            if s.get("thresholdText"):
                line += f"。信号判定总述:{s['thresholdText']}"
            sigs.append(line)
        blocks.append(f"【{r['id']} {r['name']}】定义:{r['definition']}\n" + "\n".join(sigs))
    return "\n\n".join(blocks)


def keyword_dict() -> Dict[str, str]:
    """signal_id -> 关键词文本(供 RAG 关键词召回)。"""
    out = {}
    for r in risks():
        for s in r["signals"]:
            kw = (s.get("keywords") or "").strip()
            if kw:
                out[s["id"]] = kw
    return out


def categories() -> List[str]:
    seen = []
    for r in risks():
        if r.get("category") and r["category"] not in seen:
            seen.append(r["category"])
    return seen
