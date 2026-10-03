# -*- coding: utf-8 -*-
"""AI 相关 API：Provider 状态 / 切换 / 单独触发评估。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "config"))
import settings  # noqa: E402

from fastapi import APIRouter, HTTPException, Query  # noqa: E402

from backend.app import db  # noqa: E402
from backend.app.ai import available_providers, get_provider  # noqa: E402
from backend.app.services.scoring_service import grade_level  # noqa: E402

router = APIRouter()


@router.get("/ai/status")
def ai_status():
    """当前 AI Provider 状态（前端"AI 设置"卡片用）。"""
    prov = get_provider()
    return {
        "ok": True,
        "configured": settings.AI_PROVIDER,
        "active": prov.name,
        "available": prov.is_available(),
        "providers": available_providers(),
        "deepseek": {
            "base_url": settings.DEEPSEEK_BASE_URL,
            "model": settings.DEEPSEEK_MODEL,
            "key_configured": bool(settings.DEEPSEEK_API_KEY),
        },
        "note": (
            "当前使用 mock provider（规则实现，无需 API Key，功能完整）。"
            "要接入 DeepSeek：在 config/settings.json 里设置 ai_provider=\"deepseek\" "
            "并填入 deepseek_api_key，或设置环境变量 DEEPSEEK_API_KEY，然后重启后端。"
        ),
    }


@router.get("/ai/providers")
def list_providers():
    return {"ok": True, "active": get_provider().name, "items": available_providers()}


@router.post("/ai/evaluate/{candidate_id}")
def ai_evaluate(
    candidate_id: int,
    round: int | None = Query(None, description="不传则用该候选人最新一轮已完成面试"),
):
    """
    对某候选人的某轮面试做 AI 智能评估。
    - 只**读取**已有评分，不修改评分与面试记录（只把结果回写到该记录的 ai_evaluation）。
    - AI 不可用时明确返回降级原因（验收标准 L：无 Key 也能跑）。
    """
    cand = db.get_candidate(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")

    interviews = db.list_interviews(candidate_id)
    target = None
    if round is not None:
        target = next((i for i in interviews if i["round"] == round), None)
    if target is None:
        done = [i for i in interviews if i.get("status") == "completed"]
        target = done[-1] if done else (interviews[-1] if interviews else None)

    if target is None:
        raise HTTPException(
            status_code=400,
            detail="该候选人还没有任何面试记录，无法评估。请先完成一轮面试评分。",
        )

    scores = target.get("scores")
    if isinstance(scores, str) and scores:
        try:
            scores = json.loads(scores)
        except Exception:
            scores = {}

    prov = get_provider()
    payload = {
        "candidate": dict(cand),
        "scores": scores or {},
        "total_score": target.get("total_score"),
        "comment": target.get("comment"),
        "round": target.get("round", 1),
    }

    used = prov.name
    fallback_note = None
    try:
        evaluation = prov.evaluate_candidate(payload)
    except Exception as exc:
        from backend.app.ai import MockAIProvider

        used = "mock"
        fallback_note = f"{prov.name} 调用失败，已自动降级为 mock：{exc}"
        evaluation = MockAIProvider().evaluate_candidate(payload)
        evaluation["ai_fallback"] = fallback_note

    try:
        summary = prov.summarize_interview(payload)
    except Exception:
        from backend.app.ai import MockAIProvider

        summary = MockAIProvider().summarize_interview(payload)

    # 回写到该轮记录（不新增记录）
    db.save_interview(
        {
            "candidate_id": candidate_id,
            "round": target.get("round", 1),
            "interviewer": target.get("interviewer"),
            "scores": json.dumps(scores or {}, ensure_ascii=False),
            "total_score": target.get("total_score"),
            "comment": target.get("comment"),
            "ai_summary": summary,
            "ai_evaluation": json.dumps(evaluation, ensure_ascii=False),
            "ai_provider": used,
            "status": target.get("status", "completed"),
        }
    )

    return {
        "ok": True,
        "candidate_id": candidate_id,
        "candidate_name": cand["name"],
        "round": target.get("round", 1),
        "provider_used": used,
        "fallback_note": fallback_note,
        "total_score": target.get("total_score"),
        "level": grade_level(target.get("total_score")),
        "summary": summary,
        "evaluation": evaluation,
    }
