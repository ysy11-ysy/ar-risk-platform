# -*- coding: utf-8 -*-
"""双校验编排:
  Step 2  指标计算与初筛 —— 机器硬规则 + 大模型全量计算(互为校验)
  Step 3  疑点核验 —— 大模型携带关键词召回的年报原文段落,判断原因是否可接受
"""
import concurrent.futures as cf
import json
import logging

from core import calculator, document, extractor, llm, prompts, rules

log = logging.getLogger(__name__)

BATCH_RISKS = 2  # 大模型每次最多处理的规则数量(控制上下文与输出长度)


def _llm_concurrency() -> int:
    """并发路数:环境变量 LLM_CONCURRENCY 控制(默认 3,上限 8),防免费额度限流。"""
    import config
    return config.llm_concurrency()


def _run_parallel(calls, progress=None, label="并发调用"):
    """并行执行 [(fn, args, kwargs), ...],按传入顺序返回结果列表。

    单路抛异常时以异常对象占位、不阻塞其余路;progress(done, total, note)
    在主线程回调,供 UI 更新真实进度(默认 0.0 的占位进度是"假死"元凶)。
    """
    n = len(calls)
    if n == 0:
        return []
    out = [None] * n
    done = 0
    if progress:
        progress(0, n, f"{label}:准备(0/{n})")
    with cf.ThreadPoolExecutor(max_workers=min(_llm_concurrency(), n)) as ex:
        futs = {ex.submit(fn, *args, **kwargs): i for i, (fn, args, kwargs) in enumerate(calls)}
        for fut in cf.as_completed(futs):
            i = futs[fut]
            try:
                out[i] = fut.result()
            except Exception as e:  # 单路失败不阻塞其余(上层按异常占位处理)
                log.exception("并行 LLM 子任务失败")
                out[i] = e
            done += 1
            if progress:
                progress(done, n, f"{label}:已完成 {done}/{n}")
    return out


def _chat_json(system: str, user: str, temperature: float = 0.1):
    """worker:执行一次大模型 JSON 调用;失败时返回 {'_error': 原因} 占位。"""
    try:
        return llm.chat_json(system, user, temperature=temperature)
    except Exception as e:
        log.exception("LLM 调用失败")
        return {"_error": str(e)}


# ---------------- 第二步:计算与初筛 ----------------

def step2_calc(finance: dict, risk_ids=None, progress=None):
    """返回 {machine: [rows], llm: [rows], merged: [rows]}

    每行: {risk_id, signal_id, signal_name, indicator, value, unit, level,
           basis, source: machine|llm|demo}
    多批大模型调用并发执行(LLM_CONCURRENCY 路),结果按批序合并;单批失败不阻塞其余批。
    """
    machine = calculator.run_machine(finance, risk_ids)

    if not llm_ok():
        merged = merge_rows(machine, [])
        return {"machine": machine, "llm": [], "merged": merged, "llm_used": False}

    all_risks = rules.risks()
    targets = [r for r in all_risks if not risk_ids or r["id"] in risk_ids]
    # 主线程预组装各批 prompt(worker 只做网络请求);财务文本只序列化一次
    fin_text = extractor.finance_to_text(finance)
    batches = []
    for i in range(0, len(targets), BATCH_RISKS):
        ids = [r["id"] for r in targets[i:i + BATCH_RISKS]]
        rule_text = rules.rule_text_for_prompt(ids)
        sys_p, user_p = prompts.calc_metrics_prompt(rule_text, fin_text, ids)
        batches.append({"ids": ids, "sys": sys_p, "user": user_p})

    n = len(batches)
    if progress:
        progress(0, n, f"大模型全量计算:共 {n} 批,按并发闸排队执行(相同数据已算过会秒回)")
    raw = _run_parallel(
        [(_chat_json, (b["sys"], b["user"]), {"temperature": 0.1}) for b in batches],
        progress=progress, label=f"大模型全量计算(共{n}批)")

    llm_rows, errors = [], []
    for bi, b in enumerate(batches):
        obj = raw[bi]
        if isinstance(obj, Exception):
            errors.append({"error": str(obj), "batch": b["ids"]})
            continue
        if isinstance(obj, dict) and obj.get("_error"):
            errors.append({"error": obj["_error"], "batch": b["ids"]})
            continue
        if isinstance(obj, list):
            arr = obj
        elif isinstance(obj, dict):
            arr = obj.get("results") or obj.get("data") or []
        else:
            errors.append({"error": f"大模型返回类型异常:{type(obj).__name__}",
                           "batch": b["ids"]})
            continue
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
    merged = merge_rows(machine, llm_rows)
    return {"machine": machine, "llm": llm_rows, "merged": merged,
            "llm_used": True, "errors": errors}


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

    # 主线程预组装各信号的核验材料(规则文本/关键词召回段落/财务摘要/prompt)
    jobs = []
    for sid, rows in grouped.items():
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
        jobs.append({"sid": sid, "rk": rk, "sg": sg, "rows": rows,
                     "excerpts": excerpts, "sys": sys_p, "user": user_p})

    n = len(jobs)
    if progress:
        progress(0, n, f"第三步核验:共 {n} 个信号,按并发闸排队执行(已核验过的信号秒回)")
    raw = _run_parallel(
        [(_chat_json, (j["sys"], j["user"]), {"temperature": 0.1}) for j in jobs],
        progress=progress, label=f"原文核验(共{n}个信号)")

    for i, j in enumerate(jobs):
        r = raw[i]
        if isinstance(r, Exception):
            obj = {"error": str(r)}
        elif isinstance(r, dict) and r.get("_error"):
            obj = {"error": r["_error"]}
        elif isinstance(r, dict):
            obj = r
        else:  # 非 dict 返回(防御)
            obj = {}
        failed = bool(obj.get("error"))
        if failed:
            log.exception("verify failed")
            obj = {"verdict": "存疑-建议关注", "explanation": f"(核验调用失败:{obj['error']})",
                   "acceptable": False, "reason_type": "其他", "manual_review": [],
                   "evidence": "", "error": obj["error"]}
        results.append({
            "signal_id": j["sid"], "risk_id": j["rk"]["id"], "signal_name": j["sg"]["name"],
            "indicators": [x.get("indicator") for x in j["rows"]],
            "metric_values": {x.get("indicator"): f"{x.get('value')}{x.get('unit','')} {x.get('level')}" for x in j["rows"]},
            "keywords": j["sg"].get("keywords", ""),
            "excerpts": j["excerpts"],
            "suspicious": obj.get("suspicious", True),
            "explanation": obj.get("explanation", ""),
            "reason_type": obj.get("reason_type", ""),
            "acceptable": obj.get("acceptable", False),
            "verdict": obj.get("verdict", "存疑-建议关注"),
            "manual_review": obj.get("manual_review", []),
            "evidence": obj.get("evidence", ""),
            "source": "llm",
            "failed": failed,
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
