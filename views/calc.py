# -*- coding: utf-8 -*-
"""第 2 步:AI 指标计算与初筛。
数值硬规则(机器)+ 大模型全量计算双轨;高风险标红、关注标橙。
"""
import json

import pandas as pd
import streamlit as st

import config
from core import calculator, external as external_ref, industry as industry_lib, rules, ui
from core import verify as verify_core

ui.inject_css()
st.title("② 指标计算与初筛")
st.caption("数值硬规则引擎先行计算可量化指标;配置大模型后,由大模型按规则库公式对全部信号逐项计算,双轨互为校验。")

company = st.session_state.get("company_info") or {}
if not company.get("company") and not st.session_state.get("is_demo"):
    st.info("尚未录入公司信息,请先到「① 上传年报与公司信息」载入演示公司或上传年报。")
    st.stop()

with st.expander("当前公司/运行环境", expanded=False):
    st.json(company)
    st.write(ui.engine_status())

fin = st.session_state.get("finance")
if not fin:
    st.warning("缺少财务科目数据,请先完成第 1 步。")
    st.stop()

# ---------------- 计算范围 ----------------
st.subheader("计算设置")
risk_all = rules.risks()
cats = rules.categories()
sel_cats = st.multiselect("风险大类(规则库共 17 类)", cats, default=[])
sel_risks = st.multiselect(
    "或直接选择风险(留空 = 按上述大类,均未选则全部 17 项)",
    [f"{r['id']} {r['name']}" for r in risk_all], default=[])
risk_ids = None
if sel_risks:
    risk_ids = [s.split(" ")[0] for s in sel_risks]
elif sel_cats:
    risk_ids = [r["id"] for r in risk_all if r.get("category") in sel_cats]

# ---------------- 行业基准(机器计算行业类指标引用;默认值为示意参考,可人工覆盖) ----------------
_ind_now = (company or {}).get("industry") or ""
with st.expander("📊 行业基准参照(机器计算行业类指标用)", expanded=False):
    if not _ind_now:
        st.warning("公司尚未录入所属行业:行业类指标(毛利率行业偏离、营收增长偏离、人均产值/薪酬行业倍数、背离指数)将无法引用基准而标『无法计算』。"
                   "请先到「① 上传年报与公司信息」选择所属行业。")
    else:
        base = industry_lib.baseline(_ind_now)
        ov = (st.session_state.get("ind_override") or {}).get(_ind_now) or {}
        st.markdown(
            f"公司所属行业:**{_ind_now}**。下表**默认值为示意参考,并非权威统计口径**,正式使用请以权威行业数据"
            f"(Wind/Choice/行业协会)核对后在此覆盖——机器轨按覆盖值重算,可靠性由录入人背书。")
        c1, c2, c3, c4 = st.columns(4)
        w = {}
        for col, key, label, unit in (
                (c1, "per_capita_output", "行业人均产值", "万元/人/年"),
                (c2, "per_capita_pay", "行业人均薪酬", "万元/人/年"),
                (c3, "gross_margin", "行业平均毛利率", "%"),
                (c4, "rev_growth", "行业营收增速", "%")):
            bv = base.get(key)
            cur = ov.get(key) if (ov.get(key) is not None or bv is None) else bv
            w[key] = col.number_input(
                f"{label}({unit})", min_value=-200.0, max_value=5000.0,
                value=float(cur if cur is not None else 0.0), format="%.1f", key=f"ind_{key}",
                help=f"基准表默认:{bv if bv is not None else '未提供/不适用'}"
                     f"{'(金融/房地产/教育等无标准销售毛利率口径)' if key == 'gross_margin' and bv is None else ''};"
                     f"留 0 表示不录入,对应行业类指标标『无法计算』交大模型+人工判读。")
        st.caption("改动后需点下方「应用」才会生效(写入本会话覆盖值);未点应用则按基准表默认值计算。")
        if st.button("✅ 应用上述行业基准(供机器轨计算)"):
            ovs = dict(st.session_state.get("ind_override") or {})
            m = {}
            for k in ("per_capita_output", "per_capita_pay", "gross_margin", "rev_growth"):
                v = w[k]
                bv = base.get(k)
                if bv is None and v == 0.0:
                    continue  # 不适用且未录入 -> 不注入,对应指标标无法计算
                if bv is None or abs(v - bv) > 1e-9:
                    m[k] = v
            ovs[_ind_now] = m
            st.session_state["ind_override"] = ovs
            st.success(f"已保存「{_ind_now}」行业基准覆盖;点击下方「开始计算」机器轨将按覆盖值重算。")

# ---------------- 可选联网增强:行业参考(仅供人工核对后应用,不自动覆盖) ----------------
if _ind_now:
    with st.expander("🌐 可选:联网补充行业参考值(实验性,仅供人工核对)", expanded=False):
        st.caption("联网只作『行业基准表』的可选补充,**绝不自动进入机器判定**:拉取结果须由人工核对来源与口径后点"
                   "「应用联网参考值」才生效。中国公开免费的『行业人均产值/毛利率』结构化接口不可靠且口径不一,"
                   "故不内置第三方源——请填写可信数据源的 JSON 地址(公司数据网关/付费数据库导出/行业协会统计)。")
        url_val = st.text_input(
            "行业参考 JSON 地址(留空 = 仅用内置基准与人工录入)",
            value=getattr(config, "external_ref_url", lambda: "")(), key="ext_url",
            help="期望返回 JSON:{\"industry\": \"制造业\", \"source\": \"来源说明\", \"as_of\": \"口径/截至\", "
                 "\"values\": {\"per_capita_output\": 88.0, \"per_capita_pay\": 9.8, \"gross_margin\": 21.0, "
                 "\"rev_growth\": 4.5}};values 可只含部分键;行业不匹配/格式错误/网络失败会被拒绝且不影响主流程。")
        if st.button("🌐 联网获取并预览"):
            ref = external_ref.fetch_ref(url_val, expect_industry=_ind_now)
            if not ref:
                st.warning("获取失败或格式/行业不符(URL 需可访问且返回上述 JSON)。主流程不受影响:继续用内置基准/人工录入即可。")
                st.session_state.pop("web_ref", None)
            else:
                st.session_state["web_ref"] = ref
                st.success(f"已获取参考值(来源:{ref.get('source') or '未注明'} · {ref.get('as_of') or '未注明'})"
                           f"——请人工核对口径后决定是否采用。")
        ref = st.session_state.get("web_ref") or {}
        if ref and ref.get("industry") == _ind_now:
            st.json(ref)
            if st.button("✅ 应用该联网参考值(覆盖本会话行业基准)"):
                ovs = dict(st.session_state.get("ind_override") or {})
                ovs[_ind_now] = dict(ref.get("values") or {})
                st.session_state["ind_override"] = ovs
                st.session_state.pop("web_ref", None)
                st.success(f"已按联网参考值覆盖「{_ind_now}」行业基准;点击「开始计算」机器轨将按此重算"
                           f"(建议回上方行业基准区核对数值后再算)。")
                st.rerun()


def _show_machine_preview(rows: list):
    """机器轨结果即时渲染:让用户在等待大模型期间先看到图表与疑点清单。"""
    st.markdown("#### ① 数值硬规则引擎结果(本地即时计算,已完成)")
    from collections import Counter
    cnt = Counter(r.get("level", "未知") for r in rows)
    if not rows:
        st.info("所选范围内没有可机器计算的指标(可能全部依赖外部数据,将由大模型处理)。")
        return
    order = ["高风险", "关注", "正常", "未触发", "需外部数据", "无法计算"]
    n_normal = cnt.get("正常", 0) + cnt.get("未触发", 0)
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("机器计算指标数", len(rows))
    m2.metric("高风险(红)", cnt.get("高风险", 0))
    m3.metric("关注(橙)", cnt.get("关注", 0))
    m4.metric("正常/未触发", n_normal)
    m5.metric("需外部数据", cnt.get("需外部数据", 0))
    m6.metric("无法计算", cnt.get("无法计算", 0))
    dist = pd.DataFrame({"判定": order, "数量": [cnt.get(k, 0) for k in order]})
    st.bar_chart(dist.set_index("判定"), color="#1f4e8c", height=200)
    st.caption(f"对账:高风险 {cnt.get('高风险',0)} + 关注 {cnt.get('关注',0)} + "
               f"正常/未触发 {n_normal} + 需外部数据 {cnt.get('需外部数据',0)} + "
               f"无法计算 {cnt.get('无法计算',0)} = 机器计算指标数 {len(rows)}")
    flagged = [r for r in rows if r.get("level") in ("高风险", "关注")]
    if flagged:
        pre = pd.DataFrame([{
            "信号": f"{r.get('signal_id')}",
            "指标": r.get("indicator", ""),
            "计算值": f"{r.get('value') if r.get('value') is not None else '—'} {r.get('unit','')}".strip(),
            "判定": r.get("level", ""),
        } for r in sorted(flagged, key=lambda r: (r.get("level") != "高风险",
                                                  r.get("risk_id", ""),
                                                  r.get("signal_id", "")))])
        st.dataframe(pre, use_container_width=True, hide_index=True)
    st.caption("以上为本地数值硬规则即时结果;大模型全量计算在下方执行,进度实时更新。")

calc = st.session_state.get("calc_result")

force_recalc = st.checkbox("🔁 强制重新计算(不复用同参数缓存)", value=False,
                           help="默认:同一会话、同一财务数据与风险范围将直接复用上次计算结果,"
                                "避免重复调用大模型耗时;勾选后忽略缓存完整重跑。")

if st.button("⚙️ 开始计算指标(机器硬规则 + 大模型全量)", type="primary"):
    # ---- 行业基准注入:机器(与 LLM 上下文)引用 extra.ind_* 计算行业类指标 ----
    _ind = (company or {}).get("industry") or ""
    _ov = (st.session_state.get("ind_override") or {}).get(_ind)
    fin_run, ind_applied = industry_lib.inject(fin, _ind, _ov)
    if ind_applied:
        st.caption(f"机器轨已注入行业基准「{_ind}」:人均产值 {ind_applied.get('ind_per_capita_output')} 万元/人/年、"
                   f"人均薪酬 {ind_applied.get('ind_per_capita_pay')} 万元/人/年、毛利率 {ind_applied.get('ind_gross_margin')}%、"
                   f"营收增速 {ind_applied.get('ind_rev_growth')}%(可在上方「📊 行业基准参照」覆盖后重算)。")
    else:
        st.caption("未注入行业基准(公司无行业或基准表未收录):行业类指标将标『无法计算』,交大模型估算 + 人工复核。")
    scope = json.dumps({"finance": fin_run, "risk_ids": risk_ids,
                        "company": (company or {}).get("company"),
                        "year": (company or {}).get("year"),
                        "is_demo": bool(st.session_state.get("is_demo"))},
                       ensure_ascii=False, sort_keys=True, default=str)
    prev = st.session_state.get("calc_result")
    if not force_recalc and prev and prev.get("_scope") == scope:
        st.success("计算参数与上次一致,已直接复用上次计算结果"
                   "(如需重跑请勾选「🔁 强制重新计算」)。")
        st.rerun()
    st.session_state.pop("verify_results", None)

    # ---- 1) 机器硬规则先行(本地毫秒级):立刻出图表,不等大模型 ----
    bar = st.progress(0.0, text="正在运行数值硬规则引擎…")
    machine = calculator.run_machine(fin_run, risk_ids)
    _show_machine_preview(machine)

    # ---- 2) 大模型全量计算(逐批推进,进度实时更新;相同数据命中缓存秒回)----
    if st.session_state.get("is_demo"):
        # 演示公司:机器实算 + 内置演示 LLM 结果合并
        from core.ui import demo_company
        demo_llm = demo_company().get("llm", [])
        calc = {"machine": machine, "llm": demo_llm,
                "merged": verify_core.merge_rows(machine, demo_llm), "llm_used": False,
                "demo": True, "_scope": scope}
        bar.progress(1.0, text="完成")
        st.session_state["calc_result"] = calc
    elif verify_core.llm_ok():
        import time as _t
        t0 = _t.time()

        def _cb(done, total, note):
            frac = (done / total) if total else 1.0
            eta = ""
            if done > 0:
                eta_s = (_t.time() - t0) / done * max(total - done, 0)
                eta = f",预计还需约 {eta_s / 60:.1f} 分钟"
            bar.progress(frac, text=f"{note}{eta}")

        calc = verify_core.step2_calc(fin_run, risk_ids, progress=_cb)
        calc["_scope"] = scope
        bar.progress(1.0, text="大模型全量计算完成,正在合并双轨结果…")
        st.session_state["calc_result"] = calc
    else:
        st.error("当前未配置可用的真实大模型(需要 .env 中配置 Key 且 DEMO_MODE=false),且本次会话不是演示公司。可选:"
                 "① 到第 ① 步载入演示公司体验完整效果;② 编辑 .env 配置 Key 后重试。")
        st.stop()
    st.rerun()

calc = st.session_state.get("calc_result")
if not calc:
    st.info("点击上方「开始计算」生成指标结果。")
    st.stop()

merged = calc.get("merged") or []
if calc.get("demo"):
    st.info("当前结果为【离线演示】:机器硬规则实时计算 + 内置演示公司的大模型计算结果(红/橙色为异常项)。")
if calc.get("errors"):
    _err_ids = ["/".join(e.get("batch") or []) for e in calc["errors"][:5]]
    st.warning(f"本次大模型计算有 **{len(calc['errors'])} 个批次未完成**(限流或网络原因:"
               f"{'、'.join(_err_ids)})。已成功的批次结果已保留并缓存——"
               f"直接再次点击上方「开始计算」即可**续跑缺失批次,已完成部分秒回不重算**;"
               f"若反复失败请减少所选风险范围或稍后再试。")
if not merged:
    st.warning("所选范围内没有可计算指标,请放宽选择。")
    st.stop()

# ---------------- 统计 ----
n_high = sum(1 for r in merged if r.get("level") == "高风险")
n_watch = sum(1 for r in merged if r.get("level") == "关注")
n_normal = sum(1 for r in merged if r.get("level") in ("正常", "未触发"))
n_ext = sum(1 for r in merged if r.get("level") == "需外部数据")
n_na = sum(1 for r in merged if r.get("level") == "无法计算")
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("计算指标数", len(merged))
m2.metric("高风险(红)", n_high)
m3.metric("关注(橙)", n_watch)
m4.metric("正常/未触发", n_normal)
m5.metric("需外部数据", n_ext)
m6.metric("无法计算", n_na)
st.caption(f"对账:高风险 {n_high} + 关注 {n_watch} + 正常/未触发 {n_normal} + "
           f"需外部数据 {n_ext} + 无法计算 {n_na} = "
           f"{n_high + n_watch + n_normal + n_ext + n_na}(计算指标数 {len(merged)},应相等)")
st.markdown(
    '<div class="small-note">图例:<span class="chip" style="background:#c0392b">高风险</span>'
    '<span class="chip" style="background:#e67e22">关注</span>'
    '<span class="chip" style="background:#1e8449">正常</span>'
    '<span class="chip" style="background:#7f8c8d">未触发</span>'
    '<span class="chip" style="background:#6c3483">需外部数据</span>'
    '<span class="chip" style="background:#95a5a6">无法计算</span></div>',
    unsafe_allow_html=True)
if n_ext:
    st.caption(f"其中 {n_ext} 项标『需外部数据』(依赖多年历史或外部权威数据、无法由单期年报判定),"
               f"由大模型估算并在第 ③ 步人工补齐清单复核;行业对标类指标已按行业基准表机算,"
               f"基准可在上方「📊 行业基准参照」核对/覆盖——请勿把『需外部数据/无法计算』当作安全结论。")

# ---------------- 结果表 ----
st.subheader("风险信号指标明细(高风险标红)")
show_all = st.toggle("显示全部指标(默认仅显示 高风险+关注 的疑点)", value=False)
rows = merged if show_all else [r for r in merged if r.get("level") in ("高风险", "关注")]
rows = sorted(rows, key=lambda r: ({"高风险": 0, "关注": 1}.get(r.get("level"), 9),
                                   r.get("risk_id", ""), r.get("signal_id", "")))

tbl = []
for r in rows:
    tbl.append({
        "风险": f"{r.get('risk_id')}",
        "信号": f"{r.get('signal_id')} {r.get('signal_name','')}",
        "指标": r.get("indicator", ""),
        "计算值": f"{r.get('value') if r.get('value') is not None else '—'} {r.get('unit','')}",
        "判定": r.get("level", ""),
        "机器判定依据": r.get("basis", "")[:60],
        "LLM对照": f"{r.get('llm_level','—')}" if r.get("llm_value") is not None else "—",
    })

df = pd.DataFrame(tbl)


def paint(v):
    color = ui.LEVEL_COLORS.get(v, "#7f8c8d")
    return f"color:{color};font-weight:700" if v in ui.LEVEL_COLORS else ""


st.dataframe(df.style.map(paint, subset=["判定"]),
             use_container_width=True, hide_index=True,
             height=min(560, max(80, 40 + 34 * len(df))))

if rows:
    flagged = verify_core.flagged_rows(rows)
    st.success(f"初筛得到 **{len(flagged)}** 个待核验信号指标(高风险+关注),"
               f"已自动带入第 ③ 步由 AI 到年报原文核查原因是否可接受。")
    if st.button("➡️ 前往第 ③ 步进行 AI 原文核验", type="primary"):
        st.switch_page("views/verify.py")

# ---------------- 双校验说明 ----------------
with st.expander("双轨计算机制说明(机器 vs 大模型)"):
    st.markdown(
        "1. **数值硬规则(机器)**:内置 ~40 个核心指标公式与阈值,直接由财务科目代码计算,"
        "结果客观可复现;\n"
        "2. **大模型全量计算**:携带规则库公式+科目表,对全部 17 项风险 × 113 个信号的数百指标"
        "逐项计算与阈值判定,可覆盖需要行业对标、定性判断的指标;\n"
        "3. 两轨结果同屏对照(`LLM对照`列),不一致处提示人工关注——这就是计划书中的『双校验机制』。")
