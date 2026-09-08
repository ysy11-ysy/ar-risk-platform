# -*- coding: utf-8 -*-
"""年报 PDF 解析(pdfplumber)与文本切块。"""
import re


def extract_pdf_text(pdf_path: str) -> list:
    """返回 [页文本, ...]。失败抛出带提示的异常。"""
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("未安装 pdfplumber,请先执行: pip install pdfplumber")
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t.strip():
                pages.append(f"【第{i + 1}页】\n{t}")
    if not pages:
        raise RuntimeError(f"{pdf_path} 未能提取到文本,该 PDF 可能为扫描件(图片型),请改用带文本层的年报 PDF。")
    return pages


def join_pages(pages: list, max_chars: int = 1_000_000) -> str:
    """拼接全文并截断(LLM 上下文保护)。"""
    text = "\n".join(pages)
    return text[:max_chars]


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def recall_keyword(text: str, keywords: str, top_k: int = 6, window: int = 260) -> list:
    """用关键词集在年报全文中定位命中句,返回带上下文片段列表。

    每个片段: {"kw": 命中的关键词, "page_hint": 页号提示, "ctx": 上下文文本}
    """
    text = text or ""
    pages = re.split(r"【第\s*(\d+)\s*页】", text)
    # pages[0] 可能为前导空,之后成对: [.., pageno, content, pageno, content ...]
    kws = [k.strip() for k in re.split(r"[、;；/\s]+", keywords or "") if len(k.strip()) >= 2]
    kws = list(dict.fromkeys(kws))  # 去重保序
    if not kws:
        return []
    hits = []
    for i in range(1, len(pages) - 1, 2):
        try:
            pno = pages[i].strip()
        except Exception:
            pno = "?"
        content = pages[i + 1] if i + 1 < len(pages) else ""
        for kw in kws:
            for m in re.finditer(re.escape(kw), content):
                s = max(0, m.start() - window // 2)
                e = min(len(content), m.end() + window // 2)
                seg = content[s:e].replace("\n", " ")
                hits.append({"kw": kw, "page": pno, "ctx": seg})
                break  # 每页每词只取 1 处,避免冗余
    # 排序:同页优先,ctx 去重
    seen, uniq = set(), []
    for h in sorted(hits, key=lambda x: int(x["page"]) if x["page"].isdigit() else 9999):
        key = _norm(h["ctx"])[:120]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
        if len(uniq) >= top_k * 3:
            break
    # 只保留关键词差异大、覆盖不同信号的片段(简化:取前 top_k)
    return uniq[:top_k]


def compress_excerpts(excerpts: list, limit: int = 9000) -> str:
    """把召回片段拼成给模型的文本。"""
    if not excerpts:
        return ""
    lines = []
    total = 0
    for e in excerpts:
        line = f"[第{e['page']}页·关键词『{e['kw']}』] {e['ctx']}"
        total += len(line)
        if total > limit:
            break
        lines.append(line)
    return "\n\n".join(lines)
