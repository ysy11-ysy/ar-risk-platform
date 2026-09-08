# -*- coding: utf-8 -*-
"""第 1 步:上传年报与公司信息。
产出:st.session_state.company_info / finance / annual_text(可选)/ is_demo
"""
import hashlib
import json
from pathlib import Path

import streamlit as st

import config
from core import extractor, ui
from core.fields import ALL_ANNUAL_KEYS as ALL_KEYS, QUARTER_KEYS

ui.inject_css()

st.title("① 上传年报与公司信息")
st.caption("选择公司所属行业、上传年报 PDF 与相关资料,系统将解析并抽取三大报表财务科目(单位:万元)。")

col_a, col_b = st.columns([2, 1])
with col_a:
    st.subheader("公司基本信息")
    c1, c2, c3 = st.columns(3)
    name = c1.text_input("公司全称", value=ui.state("company_info", {}).get("company", ""))
    code = c2.text_input("证券代码", value=ui.state("company_info", {}).get("code", ""))
    year = c3.text_input("审计年度(报告年度)", value=str(ui.state("company_info", {}).get("year", "") or ""))

    industries = json.loads((Path(config.DATA_DIR) / "industry.json").read_text(encoding="utf-8"))
    cur_ind = ui.state("company_info", {}).get("industry", "")
    ind_opt = industries + [cur_ind] if cur_ind and cur_ind not in industries else industries
    industry = st.selectbox("所属行业(证监会门类)", ind_opt,
                            index=ind_opt.index(cur_ind) if cur_ind in ind_opt else 0)

with col_b:
    st.subheader("运行模式")
    st.markdown(
        f'<div class="card">{ui.engine_status()}</div>'
        f'<div class="small-note">当前会话:{"内置演示公司" if ui.state("is_demo") else "自定义上传"}</div>',
        unsafe_allow_html=True)
    if st.button("📥 一键载入演示公司(离线演示)", use_container_width=True):
        ui.load_demo_into_state()
        st.success("已载入演示公司。请前往「② 指标计算与初筛」查看。")
    if st.button("🧹 清空本会话数据", use_container_width=True):
        for k in ["company_info", "finance", "annual_text", "annual_pages",
                  "calc_result", "verify_results", "is_demo", "uploaded_names",
                  "verify_cache", "_extract_cache", "_pdf_sig"]:
            st.session_state.pop(k, None)
        st.rerun()

st.divider()
st.subheader("上传文件")
uploaded_pdfs = st.file_uploader(
    "年报 PDF(可多选:主报告/审计报告/分卷;扫描件将无法解析)",
    type=["pdf"], accept_multiple_files=True,
    help="支持上传年报及其分卷;系统用 pdfplumber 提取文本层。")

mode = st.radio("财务数据获取方式(需先上传年报 PDF):",
                ["大模型自动抽取(推荐,需配置 API Key)", "手工录入 / 从 JSON 载入", "仅载入年报文本(暂不抽取)"],
                horizontal=True)

if st.button("🚀 解析年报并进入下一步", type="primary"):
    msgs = []
    if not name.strip():
        msgs.append("公司全称")
    if not year.strip():
        msgs.append("审计年度")
    if msgs:
        st.error("请补充:" + "、".join(msgs))
        st.stop()
    st.session_state["company_info"] = {"company": name.strip(), "code": code.strip(),
                                        "industry": industry, "year": year.strip()}

    if mode.startswith("手工") or mode.startswith("仅载入"):
        if not st.session_state.get("finance"):
            st.info("未提供财务数据:可点击右上「📥 一键载入演示公司」,或在下方上传财务 JSON 后再执行下一步。")
        else:
            st.success("公司信息已保存,财务数据沿用当前会话。")
        st.stop()

    # ---- 解析 PDF(同一批文件已解析过则直接复用文本,跳过耗时的 pdfplumber)----
    pdf_sig = None
    if uploaded_pdfs:
        pdf_sig = tuple(sorted((f.name, f.size) for f in uploaded_pdfs))
    if pdf_sig and pdf_sig == st.session_state.get("_pdf_sig") and st.session_state.get("annual_text"):
        names = st.session_state.get("uploaded_names") or []
        st.info(f"检测到与上次相同的 {len(names)} 份 PDF,直接复用已解析文本(如需重新解析请先点「🧹 清空本会话数据」)。")
    else:
        pages_all, names = [], []
        if uploaded_pdfs:
            # ---- 磁盘级复用:同一批文件(名称+大小+内容指纹)解析过则直接读缓存 ----
            from core import cache as _dc
            disk_key = None
            cached = None
            try:
                _sig_parts = []
                for _f in uploaded_pdfs:
                    _f.seek(0)
                    _head = _f.read(1_048_576)
                    _f.seek(0)
                    _sig_parts.append(f"{_f.name}|{_f.size}|{_dc.key_of(_head)}")
                disk_key = _dc.key_of(*_sig_parts)
                cached = _dc.get("pdftext", disk_key, ttl_days=7.0)
            except Exception:
                cached = None
            if cached:
                pages_all = cached.get("pages", [])
                names = cached.get("names", [])
                st.info(f"同一批 PDF 之前已解析过,直接复用解析结果"
                        f"(共 {len(names)} 份、{len(pages_all)} 页文本,免去再次等待)。"
                        f"如需强制重新解析请先点「🧹 清空本会话数据」。")
            else:
                import pdfplumber
                pbar = st.progress(0.0, text="正在解析 PDF(年报较长时约需几分钟,请耐心等待)…")
                try:
                    # 先快速统计总页数(不提取文本),用于统一进度
                    _plans = []
                    for _f in uploaded_pdfs:
                        with pdfplumber.open(_f) as _pdf:
                            _plans.append((_f, len(_pdf.pages)))
                    total_pages = max(sum(n for _, n in _plans), 1)
                    done_pages = 0
                    for _f, _npg in _plans:
                        _f.seek(0)
                        with pdfplumber.open(_f) as _pdf:
                            for _i, _page in enumerate(_pdf.pages):
                                _t = _page.extract_text() or ""
                                if _t.strip():
                                    pages_all.append(f"【第{_i + 1}页·{_f.name}】\n{_t}")
                                done_pages += 1
                                if done_pages % 15 == 0 or done_pages == total_pages:
                                    pbar.progress(
                                        done_pages / total_pages,
                                        text=f"正在解析 {_f.name}:第 {_i + 1}/{_npg} 页"
                                             f"(全部 {total_pages} 页,已完成 {done_pages})…")
                        names.append(_f.name)
                    pbar.progress(1.0, text="PDF 解析完成")
                except Exception as e:
                    st.error(f"PDF 解析失败:{e}")
                    st.stop()
                # 解析结果落盘,方便其他会话/下次直接复用
                if disk_key:
                    try:
                        _dc.put("pdftext", disk_key,
                                {"pages": pages_all, "names": names}, ttl_days=7.0)
                    except Exception:
                        pass
            st.session_state["annual_pages"] = pages_all
            st.session_state["annual_text"] = "\n".join(pages_all)[:1_200_000]
            st.session_state["uploaded_names"] = names
            if pdf_sig:
                st.session_state["_pdf_sig"] = pdf_sig
            st.info(f"已解析 {len(names)} 份 PDF,共 {len(pages_all)} 页文本。")
        else:
            st.warning("尚未上传 PDF。您仍可载入演示数据,或在下一表单中手工录入/上传财务 JSON。")

    # ---- 抽取财务数据(同一年报文本已抽取过则复用,避免重复等待大模型)----
    if mode.startswith("大模型"):
        if not st.session_state.get("annual_text"):
            st.warning("没有年报文本,无法自动抽取:请上传 PDF 后重试,或改用演示/手工方式。")
            st.stop()
        if not config.llm_ready():
            st.warning("未配置大模型 API Key:请复制 .env.example 为 .env 并填写,或改用演示/手工方式。")
            st.stop()
        _model = config.llm_settings()[3]
        _h = hashlib.md5(st.session_state["annual_text"].encode("utf-8", "ignore")).hexdigest()
        cache = st.session_state.get("_extract_cache") or {}
        fin = cache.get(f"{_h}:{_model}")
        if fin:
            st.info("同一年报文本已抽取过,直接复用上次抽取结果(如需强制重新抽取请先点「🧹 清空本会话数据」)。")
        else:
            with st.spinner("大模型正在从年报中抽取财务科目(约 1-3 分钟)…"):
                fin = extractor.extract_finance(st.session_state["annual_text"])
            cache[f"{_h}:{_model}"] = fin
            if len(cache) > 3:  # 只保留最近 3 份,防会话状态膨胀
                cache = dict(list(cache.items())[-3:])
            st.session_state["_extract_cache"] = cache
        st.session_state["finance"] = fin
        st.session_state["is_demo"] = False
        st.success(f"自动抽取完成:{fin.get('company')}({fin.get('year')})")
    st.rerun()

# ---- 财务数据编辑/载入区 ----
if "finance" not in st.session_state:
    st.divider()
    st.subheader("尚无财务数据")
    st.write("可选路径:")
    st.markdown(
        "1. 点击右上「📥 一键载入演示公司」立即体验全流程(离线);\n"
        "2. 上传年报 PDF 并配置 API Key 后点「解析年报并进入下一步」自动抽取;\n"
        "3. 先下载**财务 JSON 模板**手工填写后上传:")
    template = {
        "company": "", "year": "", "unit": "万元",
        "Y0": {k: None for k in ALL_KEYS}, "Y1": {k: None for k in ALL_KEYS},
        "Y2": {k: None for k in ALL_KEYS},
        "quarter": {k: None for k in QUARTER_KEYS},
        "extra": {"top5_customer_ratio": None, "top1_customer_ratio": None,
                  "related_sales_ratio": None, "pledge_ratio": None, "special_events": ""},
    }
    st.download_button("⬇️ 下载财务 JSON 模板", data=json.dumps(template, ensure_ascii=False, indent=1),
                       file_name="finance_template.json", mime="application/json")
    fup = st.file_uploader("上传财务 JSON(模板或系统导出的文件)", type=["json"])
    if fup:
        try:
            data = json.loads(fup.read().decode("utf-8"))
            st.session_state["finance"] = data
            info = st.session_state.get("company_info") or {}
            if not info.get("company"):
                info = {"company": data.get("company") or "",
                        "code": "", "industry": "", "year": str(data.get("year") or "")}
            st.session_state["company_info"] = info
            st.session_state["is_demo"] = False
            st.success("财务 JSON 已载入。请回到顶部确认公司信息后进入「② 指标计算」;或直接前往计算页。")
            st.rerun()
        except Exception as e:
            st.error(f"JSON 解析失败:{e}")
    st.stop()

fin = st.session_state.get("finance")
if fin:
    st.subheader("财务科目数据预览与修正")
    st.caption("可下载 JSON 后批量修改,或直接在下方表格修订关键年度科目(单位:万元)。")
    st.json({k: fin.get(k) for k in ("company", "year", "unit", "Y0", "Y1", "Y2", "quarter", "extra")},
            expanded=False)
    cA, cB, cC = st.columns(3)
    btn_edit = cA.button("✏️ 展开编辑关键科目", use_container_width=True)
    btn_dl = cB.download_button("⬇️ 下载财务 JSON",
                                data=json.dumps(fin, ensure_ascii=False, indent=1),
                                file_name=f"finance_{name or 'company'}_{year or ''}.json",
                                mime="application/json", use_container_width=True)
    up_fin = cC.file_uploader("上传财务 JSON 覆盖", type=["json"], key="fin_json_up")
    if up_fin:
        st.session_state["finance"] = json.loads(up_fin.read().decode("utf-8"))
        st.success("已载入上传的财务 JSON。")
        st.rerun()
    if btn_edit:
        st.session_state["_show_editor"] = True

    if st.session_state.get("_show_editor"):
        keys = ["revenue", "cost", "net_profit", "net_profit_parent", "deduct_profit",
                "sales_expense", "admin_expense", "rd_expense", "finance_expense",
                "cfo_net", "sales_cash_in", "cfo_inflow", "staff_cash_out",
                "cash", "ar", "inventory", "contract_liab", "adv_receipt",
                "other_receivable", "total_assets", "total_liab", "current_assets",
                "current_liab", "fixed_assets", "cip", "goodwill", "equity_parent",
                "st_loan", "lt_loan", "staff_end"]
        import pandas as pd
        rows = []
        for k in keys:
            row = {"科目": k}
            for tag in ("Y0", "Y1", "Y2"):
                row[tag] = (fin.get(tag) or {}).get(k)
            rows.append(row)
        df = pd.DataFrame(rows)
        edited = st.data_editor(df, num_rows="fixed", key="fin_editor")
        if st.button("💾 保存修订"):
            for _, r in edited.iterrows():
                for tag in ("Y0", "Y1", "Y2"):
                    v = r.get(tag)
                    fin[tag][r["科目"]] = (float(v) if v not in (None, "") and str(v) not in ("nan",) else None)
            st.session_state["finance"] = fin
            st.session_state["calc_result"] = None
            st.session_state["verify_results"] = None
            st.success("已保存。建议重新执行「② 指标计算」刷新结果。")

st.divider()
st.caption("流程:① 上传与抽取 → ② 指标计算与初筛(高风险标红) → ③ AI 原文核验与结论 → ④ 案例库")
