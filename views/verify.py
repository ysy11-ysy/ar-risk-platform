# -*- coding: utf-8 -*-
"""第 3 步:AI 原文核验与最终结论。
针对第 2 步的高风险/关注指标:大模型携带规则库关键词到年报原文定位证据,
核查异常原因是否为特殊事件并判断可否接受,给出最终审核结论与人工复核点。
"""
import json

import streamlit as st

import config
from core import report as report_mod
from core import rules, ui
from core import verify as verify_core

ui.inject_css()
st.title("③ AI 疑点核验与最终结论")
st.caption("核验逻辑:初筛异常指标 → 规则库关键词自动抓取年报原文 → 大模型判断"
           "『异常原因是否为特殊事件、理由可否接受』→ 输出最终审核意见与需人工复核事项。")

calc = st.session_state.get("calc_result")
company = st.session_state.get("company_info") or {}
if not calc or not calc.get("merged"):
    st.info("还没有指标计算结果,请先完成第 ② 步(或载入演示公司后到第 ② 步点击计算)。")
    st.stop()

merged = calc.get("merged")
flagged = verify_core.flagged_rows(merged)

# 按信号归并显示
groups = {}
for r in flagged:
    groups.setdefault((r.get("risk_id"), r.get("signal_id"), r.get("signal_name")), []).append(r)

st.subheader("待核验疑点")
st.write(f"第 ② 步共筛出 **{len(flagged)}** 条异常指标,归并为 **{len(groups)}** 个信号待核验。")
if not groups:
    st.success("本报告范围未发现高风险/关注指标,审核结论:暂未发现明显风险点。")
    st.stop()

kind = st.radio("核验范围", ["全部疑点(高风险+关注)", "仅高风险"], horizontal=True)
only_high = kind.startswith("仅高")
target_rows = [r for r in flagged if not only_high or r.get("level") == "高风险"]

verify_results = st.session_state.get("verify_results")

is_demo_session = bool(st.session_state.get("is_demo"))
if st.button("🤖 开始 AI 原文核验(大模型逐信号核查)", type="primary"):
    annual_text = st.session_state.get("annual_text") or ""
    fin = st.session_state.get("finance") or {}
    industry = (company or {}).get("industry", "")
    if is_demo_session:
        # 载入内置演示核验结果(离线可看效果)
        from core.ui import demo_company
        pkg = demo_company()
        results = pkg["verify"]
        for r in results:
            r["source"] = "demo"
        st.info("演示模式:展示内置核验结论;上传真实年报并配置 API Key 后将实时执行。")
    else:
        if not annual_text:
            st.error("第 ③ 步需要年报原文用于关键词定位与核验。请到第 ① 步上传年报 PDF"
                     "(或载入演示公司体验完整流程)。")
            st.stop()
        if not verify_core.llm_ok():
            st.error("未配置可用的真实大模型(需 .env 中 Key + DEMO_MODE=false):请编辑 .env 后重试,"
                     "或到第 ① 步载入演示公司离线体验。")
            st.stop()
        st.session_state.pop("verify_results", None)
        bar = st.progress(0.0, text="准备核验…")
        results = verify_core.step3_verify(
            annual_text, fin, industry, target_rows,
            progress=lambda msg: bar.progress(0.0, text=msg))
        bar.progress(1.0, text="完成")
    st.session_state["verify_results"] = results
    st.rerun()

verify_results = st.session_state.get("verify_results")
if not verify_results:
    st.info("点击上方按钮开始核验。核验会在年报原文中定位『高风险指标对应的关键词段落』,"
            "由大模型逐信号给出:异常产生原因 → 原因类型 → 是否可接受 → 最终结论 → 人工复核点。")
    st.stop()

# ---------------- 汇总统计 ----------------
n_risk = sum(1 for v in verify_results if v.get("verdict") == "确定为风险点")
n_doubt = sum(1 for v in verify_results if v.get("verdict") == "存疑-建议关注")
n_ok = sum(1 for v in verify_results if v.get("verdict") == "可接受-视为无问题")
n_other = len(verify_results) - n_risk - n_doubt - n_ok
m1, m2, m3, m4 = st.columns(4)
m1.metric("核验信号数", len(verify_results))
m2.metric("⛔ 确定为风险点", n_risk)
m3.metric("⚠️ 存疑-建议关注", n_doubt)
m4.metric("✅ 可接受-无问题", n_ok)

# ---------------- 结论总览 ----------------
st.subheader("最终审核结论总览")
ov = [{
    "信号": v.get("signal_id", ""),
    "信号名称": v.get("signal_name", ""),
    "异常指标": "、".join((v.get("indicators") or [])[:3]),
    "原因类型": v.get("reason_type", ""),
    "原因可否接受": "是" if v.get("acceptable") else "否",
    "最终结论": v.get("verdict", ""),
} for v in verify_results]
import pandas as pd
pdf = pd.DataFrame(ov)


def paint_verdict(v):
    color = ui.LEVEL_COLORS.get(v, "#7f8c8d")
    return f"color:{color};font-weight:700"


st.dataframe(pdf.style.map(paint_verdict, subset=["最终结论"]),
             use_container_width=True, hide_index=True)

st.divider()

# ---------------- 逐信号核验卡片 ----------------
st.subheader("逐信号核验详情")
import html as _html

for v in verify_results:
    verdict = v.get("verdict", "")
    kind_css = {"可接受-视为无问题": "ok", "存疑-建议关注": "warn", "确定为风险点": "risk"}.get(verdict, "")
    tag = "✅" if verdict == "可接受-视为无问题" else ("⛔" if verdict == "确定为风险点" else "⚠️")
    mv = v.get("metric_values") or {}
    metric_line = "；".join(f"{k}={val}" for k, val in mv.items())
    acc = "✅ 可以接受(理由充分)" if v.get("acceptable") else "❌ 不能接受(理由不足/空泛)"

    def esc(x):
        return _html.escape(str(x or ""), quote=False)

    html = (f'<div class="card card-{kind_css}">'
            f'<div style="font-size:15px;font-weight:700;">{tag} {esc(v.get("signal_id"))} '
            f'{esc(v.get("signal_name"))}&nbsp;{ui.chip(verdict)}</div>'
            f'<div class="small-note">异常指标:{esc(metric_line) or "—"}</div>'
            f'<p style="margin:6px 0 2px;"><b>年报中给出的原因解释:</b>{esc(v.get("explanation")) or "—"}</p>'
            f'<p style="margin:2px 0;"><b>原因类型:</b>{esc(v.get("reason_type")) or "—"}　'
            f'<b>该原因可否接受:</b>{acc}</p>'
            f'<p style="margin:2px 0;"><b>年报证据原文:</b><i>“{esc(v.get("evidence")) or "—"}”</i></p>'
            f'<p style="margin:4px 0 2px;color:#8b4513;"><b>🔎 需人工复核:</b></p>'
            f'<ul style="margin:0 0 2px 18px;color:#8b4513;">'
            + "".join(f"<li>{esc(x)}</li>" for x in (v.get("manual_review") or []))
            + '</ul></div>')
    st.markdown(html, unsafe_allow_html=True)
    with st.expander(f"查看命中的年报原文段落(关键词定位,{len(v.get('excerpts') or [])} 处)"):
        for e in v.get("excerpts") or []:
            st.markdown(f"- **第{e.get('page','?')}页 · 关键词『{e.get('kw','')}』**\n\n  {e.get('ctx','')}")

st.divider()

# ---------------- 导出 ----------------
st.subheader("导出评估报告")
c1, c2 = st.columns([1, 2])
if c1.button("📄 生成并下载《风险评估 PDF 报告》", use_container_width=True):
    try:
        flagged4pdf = verify_core.flagged_rows(calc.get("merged") or [])
        data = report_mod.export_pdf(company, flagged4pdf, verify_results)
        st.download_button("⬇️ 下载 PDF", data=data,
                           file_name=f"风险审核报告_{company.get('company','')}_{company.get('year','')}.pdf",
                           mime="application/pdf")
    except Exception as e:
        st.error(f"导出失败:{e}")
with c2:
    st.session_state["_export_json"] = json.dumps(
        {"company": company, "finance": st.session_state.get("finance"),
         "calc": calc, "verify": verify_results}, ensure_ascii=False, indent=1, default=str)
    st.download_button("⬇️ 下载原始 JSON(留档/复现)", data=st.session_state["_export_json"],
                       file_name=f"风险审核_数据_{company.get('company','')}.json",
                       mime="application/json")

st.divider()
st.caption("第四步的经典案例(哪个公司曾陷入 R001 等风险、违规原因与处罚)请见「④ 经典案例库」。")
