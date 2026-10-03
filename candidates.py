# -*- coding: utf-8 -*-
"""候选人相关 API：列表 / 详情 / 简历 / 面试轮次记录。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "config"))
import settings  # noqa: E402

from fastapi import APIRouter, HTTPException, Query  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

from backend.app import db  # noqa: E402
from backend.app.ai import get_provider  # noqa: E402
from backend.app.services import resume_service  # noqa: E402
from backend.app.services import interview_order_service  # noqa: E402
from backend.app.services import joint_service  # noqa: E402
from backend.app.services.scoring_service import (  # noqa: E402
    grade_level,
    score_breakdown,
    weighted_total,
)

router = APIRouter()


def _decode_candidate(row: dict) -> dict:
    """把 DB 行转成前端易用的结构（JSON 字段反序列化 + 派生字段）。"""
    c = dict(row)
    for k in ("resume_parsed",):
        if isinstance(c.get(k), str) and c[k]:
            try:
                c[k] = json.loads(c[k])
            except Exception:
                pass
    c.pop("resume_text", None)   # 列表/详情不必带大段正文
    c["order_index"] = c.get("order_index")
    return c


@router.post("/candidates/import-from-order")
def import_from_order():
    """
    从面试顺序表（E:\\InterviewSystem\\Data\\interview_order.xlsx）同步候选人名单：
      - 新增表里有而库里没有的人
      - 更新顺序与基本信息（Excel 非空字段才覆盖，不动简历解析结果与面试记录）
      - 顺带全量重扫简历：先导名单后补简历文件的人自动挂上
    手动触发（按钮），不静默改库；绝不删除任何候选人。
    """
    result = interview_order_service.sync_candidates_from_order()
    return result


@router.get("/candidates")
def list_candidates(
    q: str | None = Query(None, description="按姓名/学号/专业/岗位模糊搜索"),
    only_pending: bool = Query(False, description="只看尚未完成第一轮的候选人"),
):
    """候选人列表（支持搜索）。"""
    rows = [_decode_candidate(r) for r in db.list_candidates()]
    for r in rows:
        r["resume_found"] = bool(r.get("resume_exists"))
        r["completed_rounds"] = r.get("completed_rounds") or 0
        r["level"] = grade_level(r.get("best_score"))

    if q:
        kw = q.strip().lower()
        def hit(r: dict) -> bool:
            blob = " ".join(
                str(r.get(f) or "") for f in
                ("name", "student_no", "major", "grade", "position", "email", "phone")
            ).lower()
            return kw in blob
        rows = [r for r in rows if hit(r)]

    if only_pending:
        rows = [r for r in rows if (r.get("completed_rounds") or 0) == 0]

    return {"ok": True, "total": len(rows), "items": rows}


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: int):
    row = db.get_candidate(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")

    c = _decode_candidate(row)
    interviews = db.list_interviews(candidate_id)
    for it in interviews:
        if isinstance(it.get("scores"), str) and it["scores"]:
            try:
                it["scores"] = json.loads(it["scores"])
            except Exception:
                pass
        it["breakdown"] = score_breakdown(it.get("scores"))
        it["level"] = grade_level(it.get("total_score"))

    return {
        "ok": True,
        "candidate": c,
        "interviews": interviews,
        "completed_rounds": sum(1 for i in interviews if i.get("status") == "completed"),
        "resume": resume_service.resume_info(c["name"], c.get("resume_file")),
    }


@router.get("/candidates/{candidate_id}/resume")
def get_resume_meta(candidate_id: int):
    """简历元信息 + 抽取文本（供前端展示）。"""
    row = db.get_candidate(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")

    info = resume_service.resume_info(row["name"], row.get("resume_file"))
    if not info.get("found"):
        return {"ok": True, "resume": info, "text": "", "parsed": None}

    p = Path(info["path"])
    text, status = resume_service.extract_text(p)

    parsed = row.get("resume_parsed")
    if isinstance(parsed, str) and parsed:
        try:
            parsed = json.loads(parsed)
        except Exception:
            parsed = None

    info["text_status"] = status
    return {
        "ok": True,
        "resume": info,
        "text": text,
        "parsed": parsed,
        "view_url": f"{settings.API_PREFIX}/candidates/{candidate_id}/resume/file",
    }


@router.get("/candidates/{candidate_id}/resume/file")
def get_resume_file(candidate_id: int):
    """
    原样返回简历文件（只读）。
    PDF 用 inline 让浏览器内置查看器打开；DOCX 等触发下载。
    """
    row = db.get_candidate(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")

    info = resume_service.resume_info(row["name"], row.get("resume_file"))
    if not info.get("found"):
        raise HTTPException(status_code=404, detail=f"未找到 {row['name']} 的简历文件")

    p = Path(info["path"])
    if not p.is_file():
        raise HTTPException(status_code=404, detail="简历文件已不存在于磁盘上")

    media = {
        ".pdf": "application/pdf",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/plain; charset=utf-8",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(p.suffix.lower(), "application/octet-stream")

    disposition = "inline" if p.suffix.lower() == ".pdf" else "attachment"
    return FileResponse(path=str(p), media_type=media, filename=p.name,
                        content_disposition_type=disposition)


@router.get("/candidates/{candidate_id}/resume/preview")
def preview_resume_meta(candidate_id: int):
    """
    大窗预览分派（JSON）：
      kind = pdf  → 前端 iframe 打开 url（file=原件 / converted=Word 转出的 PDF）
      kind = html → 前端直接渲染 html（Word 转 PDF 失败时的 DOCX 退回）
      kind = text → 前端显示纯文本（txt/md/转换失败退回）
      kind = unsupported / missing → 给出可读提示
    全程只读原始简历；Word（.doc/.docx）转换结果写项目缓存目录，不碰 E 盘。
    """
    row = db.get_candidate(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")

    info = resume_service.preview_resume(row["name"], row.get("resume_file"))
    if info.get("kind") == "missing":
        return {"ok": False, **info}

    if info.get("url") == "file":
        info["url"] = f"{settings.API_PREFIX}/candidates/{candidate_id}/resume/file"
    elif info.get("url") == "converted":
        info["url"] = f"{settings.API_PREFIX}/candidates/{candidate_id}/resume/converted"

    download_url = f"{settings.API_PREFIX}/candidates/{candidate_id}/resume/file"
    return {"ok": True, "candidate_id": candidate_id,
            "candidate_name": row["name"], "download_url": download_url, **info}


@router.get("/candidates/{candidate_id}/resume/converted")
def get_resume_converted(candidate_id: int):
    """返回由 Word 文档（.doc/.docx）转换出的 PDF（inline）。首次调用会启动本机 Word/WPS 转换，稍慢。"""
    row = db.get_candidate(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")

    p = resume_service.match_resume(row["name"], row.get("resume_file"))
    if p is None:
        raise HTTPException(status_code=404, detail=f"未找到 {row['name']} 的简历文件")
    if p.suffix.lower() not in (".doc", ".docx"):
        raise HTTPException(status_code=400,
                            detail="该简历不是 Word 文档（.doc/.docx），请直接用 resume/file 预览")

    pdf = resume_service.doc_to_pdf(p)
    if pdf is None or not pdf.is_file():
        raise HTTPException(status_code=503,
                            detail="本机 Word/WPS 转换失败，无法预览。可下载原件查看。")

    out_name = p.stem + ".pdf"
    return FileResponse(path=str(pdf), media_type="application/pdf",
                        filename=out_name, content_disposition_type="inline")


@router.get("/candidates/{candidate_id}/interviews")
def list_candidate_interviews(candidate_id: int):
    row = db.get_candidate(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")

    items = []
    for it in db.list_interviews(candidate_id):
        if isinstance(it.get("scores"), str) and it["scores"]:
            try:
                it["scores"] = json.loads(it["scores"])
            except Exception:
                pass
        if isinstance(it.get("ai_evaluation"), str) and it["ai_evaluation"]:
            try:
                it["ai_evaluation"] = json.loads(it["ai_evaluation"])
            except Exception:
                pass
        it["breakdown"] = score_breakdown(it.get("scores"))
        it["level"] = grade_level(it.get("total_score"))
        items.append(it)

    return {
        "ok": True,
        "candidate_id": candidate_id,
        "candidate_name": row["name"],
        "next_round": db.next_round_for(candidate_id),
        "total": len(items),
        "items": items,
    }


@router.get("/candidates/{candidate_id}/joint")
def candidate_joint(candidate_id: int):
    """
    联评综合评分：把该候选人所有面试官的评价合成为一个综合成绩
    （每位面试官先取自己的平均分，再对各面试官取平均，等权）。
    """
    if not db.get_candidate(candidate_id):
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")
    return joint_service.joint_evaluation(candidate_id)


@router.post("/candidates/{candidate_id}/resume/extract")
def extract_resume(candidate_id: int, use_ai: bool = Query(True)):
    """
    抽取简历文本并（可选）调用 AI 结构化，结果缓存进 DB。
    只读原始简历，不做任何修改。
    """
    row = db.get_candidate(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")

    info = resume_service.resume_info(row["name"], row.get("resume_file"))
    if not info.get("found"):
        return {"ok": False, "reason": "resume_not_found", "resume": info,
                "message": info.get("message")}

    text, status = resume_service.extract_text(Path(info["path"]))
    if not text:
        return {"ok": False, "reason": "no_text", "resume": info,
                "message": "未能从该文件中抽取到文字（可能是扫描件或不支持的格式）。"}

    if not use_ai:
        return {"ok": True, "text": text, "parsed": None, "resume": info}

    provider = get_provider()
    try:
        parsed = provider.extract_resume(text, info["filename"])
    except Exception as exc:
        # 降级：AI 失败也必须返回可用结果（验收标准 L）
        from backend.app.ai import MockAIProvider

        parsed = MockAIProvider().extract_resume(text, info["filename"])
        parsed["ai_fallback"] = f"{provider.name} 调用失败，已降级：{exc}"

    db.update_candidate_parsed(candidate_id, json.dumps(parsed, ensure_ascii=False), text)
    return {
        "ok": True,
        "provider": parsed.get("extracted_by"),
        "resume": info,
        "text_length": len(text),
        "parsed": parsed,
        "text": text,
    }
