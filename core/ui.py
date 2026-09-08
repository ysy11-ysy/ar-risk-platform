# -*- coding: utf-8 -*-
"""页面共享的 UI 工具(样式/色值/状态读写)。"""
import streamlit as st

LEVEL_COLORS = {
    "高风险": "#c0392b", "关注": "#e67e22", "正常": "#1e8449", "未触发": "#7f8c8d",
    "无法计算": "#95a5a6", "可接受-视为无问题": "#1e8449",
    "存疑-建议关注": "#e67e22", "确定为风险点": "#c0392b",
}

GLOBAL_CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.stApp header[data-testid="stHeader"] {background: transparent;}
.block-container {padding-top: 2.2rem;}
div[data-testid="stMetric"] {background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 14px;}
h1, h2, h3 {letter-spacing: .5px;}
.chip {display:inline-block; padding:1px 10px; border-radius:12px; color:#fff; font-size:12px; font-weight:600; margin-right:6px;}
.card {background:#ffffff; border:1px solid #e2e8f0; border-left:4px solid #1f4e8c; border-radius:8px;
      padding:14px 16px; margin:8px 0;}
.card-ok {border-left-color:#1e8449;}
.card-warn {border-left-color:#e67e22;}
.card-risk {border-left-color:#c0392b;}
.verdict-ok {background:#1e8449;} .verdict-warn {background:#e67e22;} .verdict-risk {background:#c0392b;}
.small-note {color:#5d6d7e; font-size:12px;}
</style>
"""


def inject_css():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def chip(text: str) -> str:
    color = LEVEL_COLORS.get(text, "#7f8c8d")
    return f'<span class="chip" style="background:{color}">{text}</span>'


def card(text: str, kind: str = "") -> None:
    cls = {"ok": "card-ok", "warn": "card-warn", "risk": "card-risk"}.get(kind, "")
    st.markdown(f'<div class="card {cls}">{text}</div>', unsafe_allow_html=True)


def state(key: str, default=None):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


def demo_company() -> dict:
    """载入内置演示公司完整包。"""
    import json
    from config import DEMO_DIR
    with open(DEMO_DIR / "demo_company.json", encoding="utf-8") as f:
        return json.load(f)


def load_demo_into_state() -> None:
    pkg = demo_company()
    st.session_state["company_info"] = pkg["company_info"]
    st.session_state["finance"] = pkg["finance"]
    st.session_state["calc_result"] = {
        "machine": pkg["machine"], "llm": pkg["llm"],
        "merged": merge_demo(pkg["machine"], pkg["llm"]), "llm_used": False,
    }
    st.session_state["verify_results"] = pkg["verify"]
    st.session_state["is_demo"] = True


def merge_demo(machine, llm_rows):
    from core.verify import merge_rows
    return merge_rows(machine, llm_rows)


def engine_status() -> str:
    import config
    if config.demo_mode():
        return "演示模式(未调用大模型;配置 .env 并设 DEMO_MODE=false 可启用真实 API)"
    if config.llm_ready():
        p, b, k, m = config.llm_settings()
        return f"大模型已就绪:{p} / {m}"
    return "未配置 API Key"
