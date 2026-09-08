# -*- coding: utf-8 -*-
"""第 2 步:AI 指标计算与初筛。
数值硬规则(机器)+ 大模型全量计算双轨;高风险标红、关注标橙。
"""
import json

import pandas as pd
import streamlit as st

import config
from core import calculator, rules, ui
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

calc = st.session_state.get("calc_result")

if st.button("⚙️ 开始计算指标(机器硬规则 + 大模型全量)", type="primary"):
    st.session_state.pop("verify_results", None)
    bar = st.progress(0.0, text="准备计算…")
    if st.session_state.get("is_demo"):
        # 演示公司:机器实算 + 内置演示 LLM 结果合并
        machine = calculator.run_machine(fin, risk_ids)
        from core.ui import demo_company
        demo_llm = demo_company().get("llm", [])
        calc = {"machine": machine, "llm": demo_llm,
                "merged": verify_core.merge_rows(machine, demo_llm), "llm_used": False,
                "demo": True}
        bar.progress(1.0, text="完成")
        st.session_state["calc_result"] = calc
    elif verify_core.llm_ok():
        calc = verify_core.step2_calc(fin, risk_ids,
                                      progress=lambda msg: bar.progress(0.0, text=msg))
        bar.progress(1.0, text="完成")
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
if not merged:
    st.warning("所选范围内没有可计算指标,请放宽选择。")
    st.stop()

# ---------------- 统计 ----
n_high = sum(1 for r in merged if r.get("level") == "高风险")
n_watch = sum(1 for r in merged if r.get("level") == "关注")
n_normal = sum(1 for r in merged if r.get("level") in ("正常", "未触发"))
m1, m2, m3, m4 = st.columns(4)
m1.metric("计算指标数", len(merged))
m2.metric("高风险(红)", n_high)
m3.metric("关注(橙)", n_watch)
m4.metric("正常/未触发", n_normal)
st.markdown(
    '<div class="small-note">图例:<span class="chip" style="background:#c0392b">高风险</span>'
    '<span class="chip" style="background:#e67e22">关注</span>'
    '<span class="chip" style="background:#1e8449">正常</span>'
    '<span class="chip" style="background:#7f8c8d">未触发</span></div>',
    unsafe_allow_html=True)

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
