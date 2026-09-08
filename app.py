# -*- coding: utf-8 -*-
"""年报风险智能识别平台 — 主入口
基于「数值硬规则初筛 + 大模型文本核验」双校验的上市公司年报舞弊风险识别系统。

运行: streamlit run app.py
"""
import streamlit as st

from core import ui

st.set_page_config(
    page_title="年报风险智能识别平台",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

ui.inject_css()

pages = [
    st.Page("views/home.py", title="🏠 平台总览", default=True),
    st.Page("views/upload.py", title="① 上传年报与公司信息"),
    st.Page("views/calc.py", title="② 指标计算与初筛"),
    st.Page("views/verify.py", title="③ AI 原文核验与结论"),
    st.Page("views/cases.py", title="④ 经典案例库"),
    st.Page("views/rules_browser.py", title="📚 规则库浏览"),
]

nav = st.navigation(pages)
nav.run()
