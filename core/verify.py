# -*- coding: utf-8 -*-
"""双校验编排:
  Step 2  指标计算与初筛 —— 机器硬规则 + 大模型全量计算(互为校验)
  Step 3  疑点核验 —— 大模型携带关键词召回的年报原文段落,判断原因是否可接受
"""
import json
import logging

from core import calculator, document, extractor, llm, prompts, rules

log = logging.getLogger(__name__)

BATCH_RISKS = 2  # 大模型每次最多处理的规则数量(控制上下文与输出长度)


# ---------------- 第二步:计算与初筛 ----------------

def step2_calc(finance: dict, risk_ids=None, progress=None):
    """返回 {machine: [rows], llm: [rows], merged: [rows]}

    每行: {risk_id, signal_id, signal_name, indicator, value, unit, level,
           basis, source: machine|llm|demo}
    """
    machine = calculator.run_machine(finance, risk_ids)

    if not llm_ok():
        merged = merge_rows(machine, [])
        return {"machine": machine, "llm": [], "merged": merged, "llm_used": False}

    llm_rows = []
    all_risks = rules.risks()
    targets = [r for r in all_risks if not risk_ids or r["id"] in risk_ids]
    n_batches = (len(targets) + BATCH_RISKS - 1) // BATCH_RISKS
    for bi in range(n_batches):
        batch = targets[bi * BATCH_RISKS: (bi + 1) * BATCH_RISKS]
        if progress:
            progress(f"大模型全量计算第 {bi + 1}/{n_batches} 批:{','.join(r['id'] for r in batch)}")
        rule_text = rules.rule_text_for_prompt([r["id"] for r in batch])
        sys_p, user_p = prompts.calc_metrics_prompt(rule_text, extractor.finance_to_text(finance),
                                                    [r["id"] for r in batch])
        try:
            arr = llm.chat_json(sys_p, user_p, temperature=0.1)
            if isinstance(arr, dict):
                arr = arr.get("results") or arr.get("data") or []
            for item in (arr or []):
                if not item.get("signal_id"):
                    continue
                llm_rows.append({
                    "risk_id": item.get("risk_id"), "signal_id": item.get("signal_id"),
                    "signal_name": item.get("signal_name", ""),
                    "indicator": item.get("indicator", ""),
                    "value": item.get("value"), "unit": item.get("unit", ""),
                    "level": item.get("level", "无法计算"),
                    "basis": item.get("basis", ""), "source": "llm",
                })
        except Exception as e:  # 单批失败不阻塞:标注错误由前端提示
            log.exception("LLM calc batch failed")
            llm_rows.append({"error": str(e), "batch": [r["id"] for r in batch]})
        if progress:
            progress(f"第 {bi + 1}/{n_batches} 批完成")
    merged = merge_rows(machine, [r for r in llm_rows if "error" not in r])
    return {"machine": machine, "llm": [r for r in llm_rows if "error" not in r],
            "merged": merged, "llm_used": True, "errors": [r for r in llm_rows if "error" in r]}


def merge_rows(machine_rows, llm_rows):
    """机器优先,LLM 补齐;同名指标(同 risk+signal+indicator)保留机器结果并附 LLM 对照。"""
    out = []
    seen = set()
    for r in machine_rows:
        r = dict(r)
        r.setdefault("source", "machine")
        r.setdefault("llm_value", None)
        r.setdefault("llm_level", None)
        out.append(r)
        seen.add((r["risk_id"], r["signal_id"], r["indicator"]))
    for r in llm_rows:
        key = (r.get("risk_id"), r.get("signal_id"), r.get("indicator"))
        if key in seen:
            for m in out:
                if (m["risk_id"], m["signal_id"], m["indicator"]) == key:
                    m["llm_value"] = r.get("value")
                    m["llm_level"] = r.get("level")
                    m["llm_basis"] = r.get("basis", "")
            continue
        r = dict(r)
        r.setdefault("source", "llm")
        out.append(r)
    return out


def flagged_rows(merged, only_high=False):
    """取需要进入第三步的高风险(+关注)行。"""
    levels = {"高风险"} if only_high else {"高风险", "关注"}
    return [r for r in merged if r.get("level") in levels]


# ---------------- 第三步:疑点核验 ----------------

def step3_verify(annual_text: str, finance: dict, industry: str,
                 targets, progress=None, demo_callback=None):
    """targets: flagged rows(见 flagged_rows)。返回核验记录列表。

    每条: {signal_id, risk_id, signal_name, indicators, suspicious, explanation,
           reason_type, acceptable, verdict, manual_review, evidence, excerpts, source}
    """
    if not targets:
        return []
    sig_map = {}
    for r in rules.risks():
        for s in r["signals"]:
            sig_map[s["id"]] = (r, s)

    results = []
    # 同一信号的多条指标合并为一条核验记录
    grouped = {}
    for row in targets:
        sid = row.get("signal_id")
        if not sid:
            continue
        grouped.setdefault(sid, []).append(row)

    if not llm_ok():
        return [demo_placeholder(sid, rows, sig_map, annual_text, finance, industry)
                for sid, rows in grouped.items()]

    for i, (sid, rows) in enumerate(grouped.items()):
        if progress:
            progress(f"第三步核验 {i + 1}/{len(grouped)}:{sid}")
        pair = sig_map.get(sid)
        if not pair:
            continue
        rk, sg = pair
        rule_text = rules.rule_text_for_prompt([rk["id"]])
        excerpts = document.recall_keyword(annual_text, sg.get("keywords") or sg.get("name") or "", top_k=6)
        metric_brief = "；".join(
            f"{x.get('indicator')}={x.get('value')}{x.get('unit','')}({x.get('level')})" for x in rows)
        sys_p, user_p = prompts.verify_prompt(rule_text, sg, metric_brief,
                                              document.compress_excerpts(excerpts),
                                              extractor.finance_to_text(finance), industry)
        try:
            obj = llm.chat_json(sys_p, user_p, temperature=0.1)
            obj = obj if isinstance(obj, dict) else {}
        except Exception as e:
            log.exception("verify failed")
            obj = {"verdict": "存疑-建议关注", "explanation": f"(核验调用失败:{e})",
                   "acceptable": False, "reason_type": "其他", "manual_review": [],
                   "evidence": "", "error": str(e)}
        results.append({
            "signal_id": sid, "risk_id": rk["id"], "signal_name": sg["name"],
            "indicators": [x.get("indicator") for x in rows],
            "metric_values": {x.get("indicator"): f"{x.get('value')}{x.get('unit','')} {x.get('level')}" for x in rows},
            "keywords": sg.get("keywords", ""),
            "excerpts": excerpts,
            "suspicious": obj.get("suspicious", True),
            "explanation": obj.get("explanation", ""),
            "reason_type": obj.get("reason_type", ""),
            "acceptable": obj.get("acceptable", False),
            "verdict": obj.get("verdict", "存疑-建议关注"),
            "manual_review": obj.get("manual_review", []),
            "evidence": obj.get("evidence", ""),
            "source": "llm",
        })
    return results


def demo_placeholder(sid, rows, sig_map, annual_text, finance, industry):
    """无 LLM Key 时的占位记录(由前端提示配置 Key 或切到演示模式)。"""
    pair = sig_map.get(sid, (None, None))
    rk, sg = pair
    return {
        "signal_id": sid, "risk_id": rk["id"] if rk else "", "signal_name": sg["name"] if sg else sid,
        "indicators": [x.get("indicator") for x in rows],
        "metric_values": {x.get("indicator"): f"{x.get('value')}{x.get('unit','')} {x.get('level')}" for x in rows},
        "keywords": sg.get("keywords", "") if sg else "",
        "excerpts": [],
        "suspicious": True, "explanation": "未配置大模型 API Key,无法完成第三步语义核验。",
        "reason_type": "", "acceptable": False,
        "verdict": "存疑-建议关注",
        "manual_review": ["请在本页顶部配置大模型 API Key(.env)后重新核验,或切换到演示模式查看完整演示。"],
        "evidence": "", "source": "placeholder",
    }


def llm_ok() -> bool:
    import config
    return config.llm_ready() and not config.demo_mode()
