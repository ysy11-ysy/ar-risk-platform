# -*- coding: utf-8 -*-
"""附加页:规则库浏览(17 风险 × 113 信号 × 数百指标,含公式/阈值/关键词)。"""
import streamlit as st

from core import rules, ui

ui.inject_css()
st.title("📚 年报风险识别规则库(展示层)")
st.caption("由《规则库 Excel》自动解析生成:17 项风险、113 个信号、391 个指标;"
           "公式与阈值文本均来自规则库原文,供评委审阅与审计人员参照。")

meta = rules.load_rules().get("meta", {})
st.markdown(f"规则库规模:**{meta.get('counts', {}).get('risks')} 项风险 / "
            f"{meta.get('counts', {}).get('signals')} 个信号 / "
            f"{meta.get('counts', {}).get('indicators')} 个指标**")

risk_all = rules.risks()
c1, c2 = st.columns([1, 2])
with c1:
    cat = st.selectbox("风险大类", ["全部"] + rules.categories())
    ids = [r for r in risk_all if cat == "全部" or r.get("category") == cat]
    label = st.radio("选择风险", [f"{r['id']} {r['name']}" for r in ids])
    rid = label.split(" ")[0]
with c2:
    risk = rules.risk_map().get(rid, {})
    st.markdown(f"### {risk.get('id')} · {risk.get('name')}")
    st.markdown(f"**所属大类**:{risk.get('category','')}")
    st.markdown(f"**定义**:{risk.get('definition','')}")

sig_opts = {f"{s['id']} {s['name']}": s for s in risk.get("signals", [])}
if sig_opts:
    sel = st.selectbox("信号", list(sig_opts.keys()))
    sig = sig_opts[sel]
    s1, s2 = st.columns(2)
    s1.metric("信号类型", sig.get("type", "—"))
    s2.metric("指标数", len(sig.get("indicators", [])))
    st.markdown(f"**数据来源**:{sig.get('dataSource','—')}")
    with st.expander("查看该信号全部指标(公式 + 判定阈值)", expanded=True):
        for i, ind in enumerate(sig.get("indicators", []), 1):
            if ind.get("formula"):
                st.markdown(f"{i}. **{ind.get('name','')}**\n\n  `{ind.get('formula')}`")
                if ind.get("threshold"):
                    st.markdown(f"  - 判定:{ind.get('threshold')}")
        if sig.get("thresholdText") and sig.get("thresholdText") != (sig.get("indicators") or [{}])[0].get("threshold", ""):
            st.markdown(f"- **信号判定总述**:{sig.get('thresholdText')}")
        if sig.get("extraThresholds"):
            for t in sig.get("extraThresholds"):
                st.markdown(f"- 补充阈值:{t}")
    with st.expander("RAG 关键词(用于第 ③ 步在年报中自动定位原文)"):
        st.code(sig.get("keywords", "") or "(规则库未提供)")
    if sig.get("evidence"):
        with st.expander("证据要求"):
            st.write(sig.get("evidence"))

st.divider()
st.caption("注:部分单元格(如 R002 第 1 行编号、R013-S02 等)保留规则库 Excel 原文;"
           "R005-R017 中个别信号原表未提供阈值档位说明的,平台如实留空并交由大模型判断。")
