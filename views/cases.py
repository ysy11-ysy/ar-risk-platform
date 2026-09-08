# -*- coding: utf-8 -*-
"""第 4 步:经典案例库(哪个公司陷入 R001..R017,违规原因与处罚举措)。"""
import json

import pandas as pd
import streamlit as st

import config
from core import rules, ui

ui.inject_css()
st.title("④ 经典舞弊案例库")
st.caption("17 个监管处罚典型案例,与规则库 R001-R017 一一对应,来源:证监会及派出机构行政处罚决定书(公开信息)。")

with open(config.CASES_FILE, encoding="utf-8") as f:
    cases = json.load(f)["cases"]

risk_sel = st.selectbox("按风险类型筛选(规则库编号)", ["全部"] + [f"{c['risk_id']} {c['risk_name']}" for c in cases])
items = cases if risk_sel == "全部" else [c for c in cases if c["risk_id"] == risk_sel.split(" ")[0]]

ov = [{
    "风险": c["risk_id"],
    "舞弊类型": c["risk_name"],
    "涉案公司": c["company"],
    "处罚文号": c["penalty"],
    "案情要点": c["summary"][:42] + ("…" if len(c["summary"]) > 42 else ""),
} for c in items]
st.dataframe(pd.DataFrame(ov), use_container_width=True, hide_index=True)

st.divider()
for c in items:
    html = (f'<div class="card card-risk">'
            f'<div style="font-size:15px;font-weight:700;">{c["risk_id"]} · {c["company"]}'
            f'&nbsp;<span class="chip" style="background:#1f4e8c">{c["risk_name"]}</span></div>'
            f'<div class="small-note">处罚:{c["penalty"]}　涉及年报:{c.get("year_hint","")}　'
            f'证券代码:{c.get("code","—")}</div>'
            f'<p style="margin:6px 0 2px;"><b>违规原因/案情:</b>{c["summary"]}</p>'
            f'<p style="margin:2px 0;"><b>年报中的风险信号:</b>{c["signals"]}</p>'
            f'<p style="margin:2px 0;"><b>审计启示(规则要点):</b>{c["lesson"]}</p>'
            f'<p style="margin:4px 0 0;"><a href="{c["link"]}" target="_blank">查看证监会处罚决定书原文 ↗</a>'
            f'<span class="small-note">　来源:{c.get("source","")}</span></p>'
            f'</div>')
    st.markdown(html, unsafe_allow_html=True)

st.divider()
st.markdown("""**如何用案例库支撑审核结论**:当第 ③ 步把某信号判定为『确定为风险点』时,
平台会在结果中引用对应风险编号;审计人员可对照本库案例中的真实舞弊手法、监管关注点
与处罚力度,快速评估涉案主体的违规性质与潜在后果(比赛汇报时建议按 R 编号联动展示)。""")

st.caption("提示:将本案库扩展为『可导入处罚通告 PDF 的档案库』,可在 data/cases.json 中按同结构追加条目。")
