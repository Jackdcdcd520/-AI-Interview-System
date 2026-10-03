# -*- coding: utf-8 -*-
"""
简历服务：定位候选人简历 → 抽取纯文本 → （可选）调用 AI 结构化。

数据安全：
  - 全程**只读**原始简历文件，绝不修改/移动/删除；
  - 支持 .pdf / .docx / .txt / .md；.doc（老格式）与扫描件 PDF 会明确提示"无法解析文字"。
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "config"))
import settings  # noqa: E402

SUPPORTED_EXT = {".pdf", ".docx", ".txt", ".md"}
KNOWN_EXT = SUPPORTED_EXT | {".doc", ".png", ".jpg", ".jpeg"}

# 简历文件名里用于匹配姓名的主分隔符
_SPLIT_CHARS = "_-—–()（）[]【】 "


def list_resume_files() -> list[Path]:
    """列出 Resumes 目录下的全部候选文件（只读）。"""
    d = settings.RESUME_DIR
    if not d.is_dir():
        return []
    files = [p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in KNOWN_EXT]
    return sorted(files, key=lambda p: p.name)


def _normalize(s: str) -> str:
    return re.sub(r"[\s_\-—–()（）\[\]【】.]", "", (s or "")).lower()


def match_resume(name: str, filename_hint: str | None = None) -> Path | None:
    """按姓名/文件名匹配简历：先精确，再包含，最后归一化比较。"""
    files = list_resume_files()
    if not files:
        return None

    if filename_hint:
        for p in files:
            if p.name == filename_hint:
                return p

    if name:
        for p in files:
            if p.stem == name:
                return p
        for p in files:
            if name in p.stem:
                return p
        nn = _normalize(name)
        for p in files:
            if nn and nn in _normalize(p.stem):
                return p
    return None


# --------------------------------------------------------------- 文本抽取
def extract_pdf(path: Path) -> str:
    """PDF 文本抽取：优先 pypdf，失败回落到 PyMuPDF/pdfminer（若已安装）。"""
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages):
            try:
                pages.append(page.extract_text() or "")
            except Exception as exc:
                pages.append(f"[第 {i + 1} 页解析失败: {exc}]")
        text = "\n".join(pages).strip()
        if text:
            return text
        return "[PDF 未提取到文字，可能是扫描件/图片型 PDF。请人工查看原件。]"
    except ImportError:
        return "[未安装 pypdf，无法解析 PDF 文本。可执行 pip install pypdf。]"
    except Exception as exc:
        return f"[PDF 解析失败: {exc}]"


def extract_docx(path: Path) -> str:
    """
    DOCX 抽取：直接读 OOXML（word/document.xml），不依赖 python-docx。
    用 zipfile + 正则去标签，够用且零额外依赖。
    """
    try:
        with zipfile.ZipFile(str(path)) as z:
            names = z.namelist()
            target = "word/document.xml"
            if target not in names:
                return "[DOCX 结构异常：缺少 word/document.xml]"
            xml = z.read(target).decode("utf-8", errors="replace")
    except Exception as exc:
        return f"[DOCX 解析失败: {exc}]"

    # 段落/换行 → \n
    xml = re.sub(r"</w:p\s*>", "\n", xml)
    xml = re.sub(r"<w:br\s*/?>", "\n", xml)
    xml = re.sub(r"</w:tc\s*>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    # 反转义
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&apos;", "'")):
        text = text.replace(a, b)
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_atomic(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def extract_text(path: Path | None, filename: str | None = None) -> tuple[str, str]:
    """
    返回 (文本, 状态)。
    状态取值：ok | not_found | unsupported | empty
    """
    if path is None or not path.is_file():
        return "", "not_found"
    ext = path.suffix.lower()
    if ext == ".pdf":
        t = extract_pdf(path)
    elif ext == ".docx":
        t = extract_docx(path)
    elif ext in (".txt", ".md"):
        t = extract_atomic(path)
    else:
        return "", "unsupported"

    if not t or t.startswith("["):
        return t, "empty" if not t else "ok"
    return t, "ok"


def resume_info(name: str, filename_hint: str | None = None) -> dict:
    """汇总某候选人的简历信息（供 API 返回）。"""
    p = match_resume(name, filename_hint)
    if p is None:
        return {
            "found": False,
            "filename": None,
            "path": None,
            "ext": None,
            "size": 0,
            "text_available": False,
            "text_length": 0,
            "viewable_inline": False,
            "message": f"未在 {settings.RESUME_DIR} 找到 {name} 的简历文件。",
        }
    ext = p.suffix.lower()
    text, status = extract_text(p)
    return {
        "found": True,
        "filename": p.name,
        "path": str(p),
        "ext": ext,
        "size": p.stat().st_size,
        "text_available": status == "ok" and bool(text),
        "text_length": len(text),
        "text_status": status,
        "viewable_inline": ext == ".pdf",     # 浏览器内置 PDF 查看器
        "downloadable": True,
        "message": "OK" if status == "ok" else f"文本抽取状态：{status}",
    }


# =============================================================== 大窗预览
# 所有 Word 简历（.doc / .docx）统一用本机 Word/WPS COM 转 PDF 后预览，
# 保留原始表格/图片/排版；.pdf 浏览器原生；.txt/.md 纯文本。

import html as _html  # noqa: E402
import hashlib  # noqa: E402
import threading  # noqa: E402

# 同一时刻只允许一个 Word COM 转换（Word 对并发很脆弱）
_doc_convert_lock = threading.Lock()


def docx_to_html(path: Path) -> str:
    """
    DOCX → 简单 HTML（零额外依赖，zipfile + xml.etree）。
    保留：段落、标题级别（Heading1~3）、加粗、换行、表格单元格分隔。
    不保留：复杂样式/图片（简历场景纯文字为主，够用）。
    """
    import xml.etree.ElementTree as ET

    NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        with zipfile.ZipFile(str(path)) as z:
            if "word/document.xml" not in z.namelist():
                return ""
            root = ET.fromstring(z.read("word/document.xml"))
    except Exception:
        return ""

    def para_html(p_el) -> str:
        style = ""
        pPr = p_el.find("w:pPr", NS)
        if pPr is not None:
            ps = pPr.find("w:pStyle", NS)
            if ps is not None:
                style = (ps.get(f"{{{NS['w']}}}val") or "").lower()
        parts = []
        for r in p_el.iter(f"{{{NS['w']}}}r"):
            bold = r.find("w:rPr/w:b", NS) is not None
            text = "".join(
                t.text or "" for t in r.iter(f"{{{NS['w']}}}t")
            )
            brs = len(r.findall(".//w:br", NS))
            if not text and brs:
                parts.append("<br>")
                continue
            esc = _html.escape(text)
            parts.append(f"<strong>{esc}</strong>" if bold else esc)
            if brs:
                parts.append("<br>" * min(brs, 3))
        content = "".join(parts).strip()
        if not content:
            return ""
        if "heading1" in style:
            return f"<h2>{content}</h2>"
        if "heading2" in style:
            return f"<h3>{content}</h3>"
        if "heading3" in style or "title" in style:
            return f"<h4>{content}</h4>"
        return f"<p>{content}</p>"

    body_parts: list[str] = []
    body = root.find("w:body", NS)
    if body is None:
        return ""
    for child in body.iter():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            body_parts.append(para_html(child))
        elif tag == "tc":  # 表格单元格 → 段落（简化处理）
            for p in child.findall("w:p", NS):
                body_parts.append(para_html(p))

    html_text = "\n".join(x for x in body_parts if x)
    return html_text or "<p>（该 DOCX 未解析出可见文字）</p>"


def _doc_cache_key(path: Path) -> Path:
    """转换缓存文件名：源路径 + 修改时间 决定，源文件变了自动失效。"""
    st = path.stat()
    key = hashlib.sha1(f"{path}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:16]
    cache = settings.DOC_PREVIEW_CACHE_DIR
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return cache / f"{key}.pdf"


def doc_to_pdf(path: Path) -> Path | None:
    """
    Word 文档（.doc / .docx）→ PDF：调用本机 Word（优先）或 WPS COM 转换。
    结果缓存；源文件未变时直接复用。失败返回 None。
    注意：只读打开原文档，输出写缓存目录，绝不修改原始简历。
    """
    out = _doc_cache_key(path)
    if out.is_file() and out.stat().st_size > 0:
        return out

    with _doc_convert_lock:
        # 双重检查（等锁期间别的线程可能已转好）
        if out.is_file() and out.stat().st_size > 0:
            return out
        try:
            import pythoncom  # pywin32
        except ImportError:
            print(f"[preview][WARN] 未安装 pywin32，无法转换 Word 文档")
            return None

        app = None
        try:
            pythoncom.CoInitialize()
            import win32com.client

            prog_ids = ["Word.Application", "KWPS.Application", "WPS.Application"]
            for pid in prog_ids:
                try:
                    app = win32com.client.DispatchEx(pid)
                    break
                except Exception:
                    continue
            if app is None:
                print("[preview][WARN] 本机没有可用的 Word/WPS COM")
                return None

            try:
                app.Visible = False
            except Exception:
                pass
            try:
                app.DisplayAlerts = 0
            except Exception:
                pass

            doc = app.Documents.Open(
                str(path), ReadOnly=True, AddToRecentFiles=False
            )
            try:
                doc.SaveAs2(str(out), FileFormat=17)   # 17 = wdFormatPDF
            except Exception:
                doc.SaveAs(str(out), FileFormat=17)
            finally:
                doc.Close(SaveChanges=False)
            return out if out.is_file() and out.stat().st_size > 0 else None
        except Exception as exc:
            print(f"[preview][WARN] Word 转 PDF 失败：{exc}")
            try:
                if out.is_file():
                    out.unlink()
            except Exception:
                pass
            return None
        finally:
            try:
                if app is not None:
                    app.Quit()
            except Exception:
                pass
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def preview_resume(name: str, filename_hint: str | None = None) -> dict:
    """
    大窗预览分派：根据扩展名决定前端如何渲染。
    kind: pdf | html | text | unsupported | missing
    """
    p = match_resume(name, filename_hint)
    if p is None:
        return {"kind": "missing", "filename": None,
                "message": f"未在 {settings.RESUME_DIR} 找到 {name} 的简历文件。"}

    ext = p.suffix.lower()
    base = {"filename": p.name, "ext": ext, "size": p.stat().st_size}

    if ext == ".pdf":
        return {**base, "kind": "pdf", "url": "file"}

    if ext in (".docx", ".doc"):
        # 统一走本机 Word/WPS → PDF：保留原始表格/图片/排版。
        # （docx 自写 HTML 会把表格拍平，观感差，已弃用为主通道。）
        # 转换结果缓存（按源文件路径+修改时间失效），首次几秒、之后秒开。
        pdf = doc_to_pdf(p)
        if pdf is not None:
            return {**base, "kind": "pdf", "url": "converted", "converted": True}
        if ext == ".docx":
            # Word 转换失败 → 退回自写 HTML（表格拍平但可读）→ 再退纯文本
            html_text = docx_to_html(p)
            if html_text:
                return {**base, "kind": "html", "html": html_text,
                        "message": "Word 转 PDF 失败，已退回简化版式预览。"}
            text, _ = extract_text(p)
            return {**base, "kind": "text", "text": text,
                    "message": "DOCX 预览失败，已退回纯文本。"}
        text, _ = extract_text(p)   # .doc 通常抽不出干净文本，可能为空
        return {**base, "kind": "unsupported",
                "text": text or "",
                "message": "老版 .doc 转换预览失败（本机需要安装 Word 或 WPS）。可下载原件，或请候选人提供 PDF/DOCX。"}

    # txt / md / 其它
    text, _ = extract_text(p)
    return {**base, "kind": "text", "text": text}
