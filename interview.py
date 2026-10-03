# -*- coding: utf-8 -*-
"""面试流程 API：当前候选人 / 下一位 / 上一位 / 顺序重置 / 提交面试记录。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "config"))
import settings  # noqa: E402

from fastapi import APIRouter, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from backend.app import db  # noqa: E402
from backend.app.ai import get_provider  # noqa: E402
from backend.app.services.scoring_service import (  # noqa: E402
    ScoreValidationError,
    grade_level,
    score_breakdown,
    validate_scores,
    weighted_total,
)

router = APIRouter()

META_CURRENT = "current_candidate_id"


# --------------------------------------------------------------- 工具
def _ordered_candidates() -> list[dict]:
    return db.list_candidates()


def _position_of(cid: int, rows: list[dict]) -> int:
    for i, r in enumerate(rows):
        if r["id"] == cid:
            return i
    return -1


def _bootstrap_current(rows: list[dict]) -> int | None:
    """首次进入时把第 1 位设为当前候选人（不写入 DB 也能工作，这里持久化以便刷新继续）。"""
    if not rows:
        return None
    saved = db.meta_get(META_CURRENT)
    if saved:
        try:
            sid = int(saved)
            if _position_of(sid, rows) >= 0:
                return sid
        except (TypeError, ValueError):
            pass
    cid = rows[0]["id"]
    db.meta_set(META_CURRENT, str(cid))
    return cid


def _candidate_bundle(cid: int, rows: list[dict]) -> dict:
    idx = _position_of(cid, rows)
    row = rows[idx] if idx >= 0 else db.get_candidate(cid)
    if not row:
        return {}

    from backend.app.services import resume_service

    interviews = db.list_interviews(cid)
    completed = [i for i in interviews if i.get("status") == "completed"]

    # 进入面试页时确保当前轮是"开放中"的 → 后续每次保存都是 UPDATE 同一条
    cur_round = db.current_round_for(cid)
    db.ensure_open_round(cid, cur_round)
    cur = db.get_interview(cid, cur_round) or {}

    if isinstance(cur.get("scores"), str) and cur["scores"]:
        try:
            cur["scores"] = json.loads(cur["scores"])
        except Exception:
            pass
    elif cur.get("scores") is None:
        cur["scores"] = {}
    if isinstance(cur.get("ai_evaluation"), str) and cur["ai_evaluation"]:
        try:
            cur["ai_evaluation"] = json.loads(cur["ai_evaluation"])
        except Exception:
            pass

    return {
        "candidate": {
            k: v for k, v in dict(row).items() if k != "resume_text"
        },
        "position": idx + 1,                        # 1 起的面试顺序
        "total": len(rows),
        "completed_rounds": len(completed),
        "current_round": cur_round,                 # 当前正在进行的轮次
        "next_round": cur_round,                    # 兼容旧字段名
        "current_interview": cur or None,
        "rounds_completed_list": sorted(i["round"] for i in completed),
        "resume": resume_service.resume_info(row["name"], row.get("resume_file")),
        # 维度定义随候选人数据一并下发 → 前端不用硬编码维度，改配置即全站生效
        "dimensions": settings.SCORE_DIMENSIONS,
        "prev_id": rows[idx - 1]["id"] if idx > 0 else None,
        "next_id": rows[idx + 1]["id"] if 0 <= idx < len(rows) - 1 else None,
        "has_prev": idx > 0,
        "has_next": idx >= 0 and idx < len(rows) - 1,
    }


# --------------------------------------------------------------- 读取接口
@router.get("/interview/current")
def get_current():
    rows = _ordered_candidates()
    if not rows:
        return {
            "ok": True, "empty": True,
            "message": "尚无候选人数据。请先运行 scripts/make_test_data.py 生成测试数据，"
                       "或把你的 interview_order.xlsx 放入 E:\\InterviewSystem\\Data 后刷新。",
            "total": 0,
        }
    cid = _bootstrap_current(rows)
    return {"ok": True, "empty": False, **_candidate_bundle(cid, rows)}


@router.get("/interview/next")
def get_next():
    rows = _ordered_candidates()
    if not rows:
        return {"ok": True, "empty": True, "total": 0, "message": "尚无候选人数据。"}

    cid = _bootstrap_current(rows)
    idx = _position_of(cid, rows)
    if idx < 0 or idx >= len(rows) - 1:
        return {
            "ok": True, "empty": False, "at_end": True,
            "message": "已经是最后一位候选人了。",
            **_candidate_bundle(cid, rows),
        }

    new_id = rows[idx + 1]["id"]
    db.meta_set(META_CURRENT, str(new_id))
    return {"ok": True, "empty": False, "at_end": False, **_candidate_bundle(new_id, rows)}


@router.get("/interview/previous")
def get_previous():
    rows = _ordered_candidates()
    if not rows:
        return {"ok": True, "empty": True, "total": 0, "message": "尚无候选人数据。"}

    cid = _bootstrap_current(rows)
    idx = _position_of(cid, rows)
    if idx <= 0:
        return {
            "ok": True, "empty": False, "at_start": True,
            "message": "已经是第一位候选人了。",
            **_candidate_bundle(cid, rows),
        }

    new_id = rows[idx - 1]["id"]
    db.meta_set(META_CURRENT, str(new_id))
    return {"ok": True, "empty": False, "at_start": False, **_candidate_bundle(new_id, rows)}


@router.post("/interview/goto/{candidate_id}")
def goto(candidate_id: int):
    rows = _ordered_candidates()
    if _position_of(candidate_id, rows) < 0:
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不在当前面试顺序中")
    db.meta_set(META_CURRENT, str(candidate_id))
    return {"ok": True, **_candidate_bundle(candidate_id, rows)}


@router.post("/interview/reset")
def reset_pointer():
    """把当前指针重置到第 1 位（不动任何面试数据）。"""
    rows = _ordered_candidates()
    if not rows:
        return {"ok": True, "empty": True, "total": 0}
    db.meta_set(META_CURRENT, str(rows[0]["id"]))
    return {"ok": True, "empty": False, **_candidate_bundle(rows[0]["id"], rows)}


@router.get("/interview/interviewers")
def list_interviewers():
    """
    历史面试官名单（去重，按打分轮次数降序）。

    用途：面试页「面试官」栏从纯手填升级为「可下拉选择 + 可手填」，
    避免同一位面试官在不同设备上写成「王老师 / 王 老师 / 老王」导致
    联评时被算成 3 个人。前端还会把它与当前记录里的面试官合并展示。
    """
    rows = db.list_interviewer_names()
    return {
        "ok": True,
        "count": len(rows),
        "items": [r["interviewer"] for r in rows],
        "detail": rows,
    }


# --------------------------------------------------------------- 提交接口
class InterviewSubmit(BaseModel):
    candidate_id: int
    round: int | None = Field(
        default=None,
        description="要写入的轮次；不传则用该候选人当前正在进行的轮次（推荐）",
    )
    interviewer: str | None = None
    scores: dict = Field(default_factory=dict)
    comment: str | None = None
    # 默认 in_progress：保存不等于"结束本轮"。
    # 面试官可以反复修改分数；要开新一轮必须调用 /interview/advance/{id}。
    status: str = "in_progress"
    generate_ai: bool = True


@router.post("/interview/advance/{candidate_id}")
def advance(candidate_id: int):
    """
    显式开始该候选人的**新一轮**面试。
    只有在确实需要第二轮时才调用；普通"保存"不会自动开新轮。
    """
    cand = db.get_candidate(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")

    new_round = db.advance_round(candidate_id)
    rows = _ordered_candidates()
    return {
        "ok": True,
        "candidate_id": candidate_id,
        "new_round": new_round,
        "message": f"已为 {cand['name']} 开启第 {new_round} 轮面试。",
        **_candidate_bundle(candidate_id, rows),
    }


@router.post("/interviews")
def submit_interview(payload: InterviewSubmit):
    """
    保存一轮面试记录。

    数据安全语义（题目硬性要求）：
      - 同一候选人同一轮**重复提交 → UPDATE 原记录**，绝不新增重复行；
      - 默认写入"当前正在进行的轮次"，因此面试官连点保存也只会有一条记录；
      - 保存后该轮仍是 in_progress（可以继续改分），
        要开始下一轮必须显式调用 POST /interview/advance/{id}；
      - AI 总结/评估由独立 Provider 生成，AI 失败自动降级，不影响保存。
    """
    cand = db.get_candidate(payload.candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail=f"候选人 {payload.candidate_id} 不存在")

    try:
        scores = validate_scores(payload.scores)
    except ScoreValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 轮次：显式指定则用它；否则用"当前正在进行的轮次"（不递增！）
    rnd = payload.round or db.current_round_for(payload.candidate_id)
    db.ensure_open_round(payload.candidate_id, rnd)

    prev = db.get_interview(payload.candidate_id, rnd) or {}
    total = weighted_total(scores)

    # 本轮默认保持 in_progress：这样后续保存继续命中同一轮（不会新开轮次）。
    # 只有面试官显式"结束本轮"（status='completed'）或调用 advance 才会封轮。
    target_status = payload.status if payload.status in ("in_progress", "completed") else "in_progress"

    # AI 参与（可关闭）；任何异常都降级，不阻断保存
    ai_summary = None
    ai_evaluation = None
    provider_name = None
    ai_note = None
    if payload.generate_ai:
        provider = get_provider()
        provider_name = provider.name
        ai_payload = {
            "candidate": dict(cand),
            "scores": scores,
            "total_score": total,
            "comment": payload.comment,
            "round": rnd,
        }
        try:
            ai_summary = provider.summarize_interview(ai_payload)
        except Exception as exc:
            ai_summary = f"[AI 总结生成失败，已跳过：{exc}]"
            ai_note = f"summarize 失败: {exc}"
        try:
            ai_evaluation = provider.evaluate_candidate(ai_payload)
        except Exception as exc:
            ai_note = (ai_note or "") + f" | evaluate 失败: {exc}"

    iid = db.save_interview(
        {
            "candidate_id": payload.candidate_id,
            "round": rnd,
            "interviewer": payload.interviewer or prev.get("interviewer"),
            "scores": json.dumps(scores, ensure_ascii=False),
            "total_score": total,
            "comment": payload.comment,
            "ai_summary": ai_summary,
            "ai_evaluation": json.dumps(ai_evaluation, ensure_ascii=False)
            if ai_evaluation else None,
            "ai_provider": provider_name,
            "status": target_status,
            "started_at": prev.get("started_at"),
        }
    )

    saved = db.get_interview_by_id(iid)
    if saved and isinstance(saved.get("scores"), str):
        try:
            saved["scores"] = json.loads(saved["scores"])
        except Exception:
            pass
    if saved and isinstance(saved.get("ai_evaluation"), str) and saved["ai_evaluation"]:
        try:
            saved["ai_evaluation"] = json.loads(saved["ai_evaluation"])
        except Exception:
            pass

    return {
        "ok": True,
        "interview_id": iid,
        "candidate_id": payload.candidate_id,
        "candidate_name": cand["name"],
        "round": rnd,
        "is_update": bool(prev),
        "status": target_status,
        "scores": scores,
        "total_score": total,
        "level": grade_level(total),
        "breakdown": score_breakdown(scores),
        "interview": saved,
        "ai": {
            "provider": provider_name,
            "summary": ai_summary,
            "evaluation": ai_evaluation,
            "note": ai_note,
        },
        "message": (
            f"已{'更新' if prev else '保存'} {cand['name']} 第 {rnd} 轮面试记录"
            f"（同一轮重复提交只会更新同一条记录）。"
        ),
    }


@router.get("/interviews/{interview_id}")
def get_interview(interview_id: int):
    it = db.get_interview_by_id(interview_id)
    if not it:
        raise HTTPException(status_code=404, detail=f"面试记录 {interview_id} 不存在")

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

    return {
        "ok": True,
        "interview": it,
        "breakdown": score_breakdown(it.get("scores")),
        "level": grade_level(it.get("total_score")),
        "candidate": db.get_candidate(it["candidate_id"]),
    }
