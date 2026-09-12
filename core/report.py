# -*- coding: utf-8 -*-
"""风险评估 PDF 报告导出(reportlab)。中文字体:本机 .ttf 优先,兜底用内置 STSong-Light CID 字体,跨平台(含 Streamlit Cloud)可导出中文。"""
import io
import os
from datetime import datetime

LEVEL_COLOR = {"高风险": "#c0392b", "关注": "#e67e22", "正常": "#27ae60", "未触发": "#7f8c8d",
               "可接受-视为无问题": "#27ae60", "存疑-建议关注": "#e67e22", "确定为风险点": "#c0392b"}


def _register_cjk_font() -> str:
    """注册中文字体并返回字体名。

    优先用本机“单字体”文件(.ttf/.otf，黑体/仿宋/楷体等)；找不到时回退到
    reportlab 内置的 Adobe 简体中文 CID 字体 STSong-Light——它不依赖任何外部
    字体文件，跨平台(含 Streamlit Cloud 的 Linux 容器)均可正常导出中文。
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    # 只列“单字体”文件：reportlab 的 TTFont 对 .ttc(字体集合)加载不稳定，
    # 可能注册出“无字形”的假字体导致 PDF 中文空白，故 .ttc 一律不在此列。
    candidates = [
        r"C:\Windows\Fonts\simhei.ttf",   # 黑体
        r"C:\Windows\Fonts\simfang.ttf",  # 仿宋
        r"C:\Windows\Fonts\simkai.ttf",   # 楷体
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("CJK", path))
                return "CJK"
            except Exception:
                continue

    # 兜底：reportlab 自带 CID 字体，无需任何字体文件，PDF 阅读器均可正常显示中文
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def export_pdf(company_info: dict, calc_merged: list, verify_results: list, rule_summary: str = "") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

    font_name = _register_cjk_font()

    st_title = ParagraphStyle("t", fontName=font_name, fontSize=16, leading=22, alignment=1, spaceAfter=6)
    st_h = ParagraphStyle("h", fontName=font_name, fontSize=11.5, leading=16, spaceBefore=8, spaceAfter=4)
    st_b = ParagraphStyle("b", fontName=font_name, fontSize=9, leading=13)
    st_small = ParagraphStyle("s", fontName=font_name, fontSize=8, leading=11)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=12 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm)
    story = []

    def para(text, style=st_b):
        t = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(t.replace("\n", "<br/>"), style)

    story.append(para(f"上市公司年报风险智能识别评估报告", st_title))
    info = company_info or {}
    story.append(para(f"公司:{info.get('company','') or info.get('name','')}   "
                      f"代码:{info.get('code','')}  行业:{info.get('industry','')}  "
                      f"报告年度:{info.get('year','')}  生成时间:{datetime.now():%Y-%m-%d %H:%M}", st_small))

    # ---- 1. 指标计算与初筛 ----
    story.append(para("一、风险信号指标计算与初筛(高风险标红、关注标橙)", st_h))
    if calc_merged:
        data = [["风险", "信号", "指标", "数值", "级别", "说明"]]
        for r in calc_merged:
            data.append([r.get("risk_id", ""), r.get("signal_id", ""),
                         (r.get("indicator") or "")[:18],
                         f"{r.get('value') if r.get('value') is not None else '-'}{r.get('unit','')}",
                         r.get("level", ""), (r.get("basis") or "")[:46]])
        t = Table(data, colWidths=[14 * mm, 20 * mm, 34 * mm, 22 * mm, 16 * mm, 76 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b9c6d6")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e8c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]))
        for ri, r in enumerate(calc_merged, start=1):
            lv = r.get("level")
            if lv in ("高风险", "关注"):
                color = colors.HexColor(LEVEL_COLOR[lv])
                t.setStyle(TableStyle([("TEXTCOLOR", (4, ri), (4, ri), color),
                                       ("TEXTCOLOR", (2, ri), (3, ri), color)]))
        story.append(t)
    else:
        story.append(para("(无计算结果)"))

    # ---- 2. 疑点核验结论 ----
    story.append(para("二、AI 疑点核验结论(是否由特殊事件合理解释)", st_h))
    if verify_results:
        data = [["信号", "异常指标", "年报中的原因解释", "原因类型", "是否可接受", "结论", "人工复核点"]]
        for v in verify_results:
            data.append([
                v.get("signal_id", ""),
                "；".join((v.get("indicators") or [])[:3])[:20],
                (v.get("explanation") or "")[:60],
                v.get("reason_type", ""),
                "是" if v.get("acceptable") else "否",
                v.get("verdict", ""),
                "；".join((v.get("manual_review") or [])[:2])[:40],
            ])
        t = Table(data, colWidths=[16 * mm, 24 * mm, 40 * mm, 18 * mm, 14 * mm, 26 * mm, 44 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_name), ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b9c6d6")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e8c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]))
        for ri, v in enumerate(verify_results, start=1):
            c = colors.HexColor(LEVEL_COLOR.get(v.get("verdict"), "#7f8c8d"))
            t.setStyle(TableStyle([("TEXTCOLOR", (5, ri), (5, ri), c)]))
        story.append(t)
        story.append(Spacer(1, 4 * mm))
        for v in verify_results:
            story.append(para(
                f"◆ {v.get('signal_id')} {v.get('signal_name','')} —— {v.get('verdict','')}", st_small))
            story.append(para(f"  原因说明:{v.get('explanation','')}", st_small))
            if v.get("evidence"):
                story.append(para(f"  年报证据:{v.get('evidence','')}", st_small))
            if v.get("manual_review"):
                story.append(para("  需人工复核:" + "；".join(v.get("manual_review")), st_small))
    else:
        story.append(para("(无核验记录)"))

    # ---- 3. 汇总 ----
    story.append(para("三、审核结论汇总", st_h))
    n_risk = sum(1 for v in verify_results if v.get("verdict") == "确定为风险点")
    n_doubt = sum(1 for v in verify_results if v.get("verdict") == "存疑-建议关注")
    n_ok = sum(1 for v in verify_results if v.get("verdict") == "可接受-视为无问题")
    story.append(para(f"共核验 {len(verify_results)} 项异常信号:确定为风险点 {n_risk} 项、"
                      f"存疑建议关注 {n_doubt} 项、可接受视为无问题 {n_ok} 项。", st_b))
    story.append(para("声明:本报告由『数值硬规则初筛 + 大模型文本核验』双校验自动生成,供审计尽调参考;"
                      "标注为『需人工复核』的事项必须由专业人员结合函证、流水、合同等外部证据最终确认。", st_small))

    doc.build(story)
    return buf.getvalue()
