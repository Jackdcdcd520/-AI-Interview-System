# -*- coding: utf-8 -*-
"""结果汇总 API：汇总列表 / 排序 / 单条详情 / 统计。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "config"))
import settings  # noqa: E402

from fastapi import APIRouter, HTTPException, Query  # noqa: E402

from backend.app import db  # noqa: E402
from backend.app.services import joint_service, weights_service  # noqa: E402
from backend.app.services.scoring_service import (  # noqa: E402
    grade_level,
    score_breakdown,
    weighted_total,
)

router = APIRouter()

# 简单排序键 -> items 里的字段名
SORTABLE = {
    "total": "best_score",
    "score": "best_score",
    "name": "name",
    "order": "order_index",
    "rounds": "rounds",
    "joint": "joint_score",
    "custom": "custom_score",
    "updated": "last_updated",
}


def _jsonify(v):
    if isinstance(v, str) and v:
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


def _parse_weight_param(raw: str | None) -> dict | None:
    """
    解析前端传来的权重覆盖参数（JSON 字符串），例如：
        {"professional": 30, "logic": 25}
    解析失败 / 为空 → 返回 None（表示「使用后端已保存的权重」）。
    """
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    out: dict[str, float] = {}
    for k, v in data.items():
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv >= 0:
            out[str(k)] = fv
    return out or None


def _num_key(v):
    """数值排序键：缺失视为 -1（与原行为一致）。"""
    return v if isinstance(v, (int, float)) else -1


def _completed_rounds(interviews: list[dict]) -> list[dict]:
    """
    哪些记录算"已完成的面试"？
    - status == 'completed'            → 算
    - status == 'in_progress' 但已有评分 → 也算（面试官已打完分、只是还在同一轮里改）
    这样汇总页能立即反映刚保存的分数，不会因为轮次还开着而显示为"未面试"。
    """
    out = []
    for i in interviews:
        if i.get("status") == "completed":
            out.append(i)
            continue
        sc = _jsonify(i.get("scores"))
        if isinstance(sc, dict) and any(v is not None for v in sc.values()):
            out.append(i)
    return out


@router.get("/results")
def get_results(
    sort: str = Query(
        "order",
        description=(
            "排序方式：order|total|name|rounds|updated|joint|custom|"
            "dim:<维度key>（按某个维度平均分）|iv:<面试官名>（按某位面试官平均分）"
        ),
    ),
    desc: bool = Query(False, description="是否降序"),
    min_score: float | None = Query(None, description="只保留最高加权总分 >= 该值"),
    level: str | None = Query(None, description="按等级过滤：强烈推荐/推荐/待定/不推荐"),
    weights: str | None = Query(
        None,
        description='可选：覆盖维度权重（JSON），如 {"professional":30,"logic":25}；'
                    "不传则使用后端已保存的权重",
    ),
    interviewer_weights: str | None = Query(
        None,
        description='可选：覆盖面试官权重（JSON），如 {"王老师":2,"李老师":1}；'
                    "不传则使用后端已保存的权重",
    ),
):
    """
    汇总所有候选人的面试结果，支持多种排序（题目要求「可以按照得分排序」）：

      - 常规：按面试顺序 / 最高得分 / 联评综合分 / 已完成轮次 / 姓名；
      - 单维度：sort=dim:professional（按「专业基础」平均分排）；
      - 单面试官：sort=iv:王老师（按王老师给出的平均分排）；
      - 自定义加权：sort=custom（用人工设定的维度权重重算总分后排）。

    每位候选人会带上：
      - dimension_avgs：各维度在「所有已评分轮次」上的平均分；
      - interviewer_avgs：每位面试官的平均分；
      - custom_score：用当前生效（或本次传入）的维度权重重算的加权总分。
    """
    dim_weights = _parse_weight_param(weights) or weights_service.get_dimension_weights()
    iv_weights_param = _parse_weight_param(interviewer_weights)
    iv_weights = (
        iv_weights_param if iv_weights_param is not None
        else weights_service.get_interviewer_weights()
    )
    dim_customized = bool(weights is not None) or weights_service.is_dimension_weights_customized()
    iv_customized = bool(iv_weights)

    rows = db.list_candidates()
    items = []

    for r in rows:
        interviews = db.list_interviews(r["id"])
        completed = _completed_rounds(interviews)

        totals: list[float] = []
        for i in completed:
            sc = _jsonify(i.get("scores")) or {}
            t = i.get("total_score")
            if t is None:
                t = weighted_total(sc if isinstance(sc, dict) else {})
            if t is not None:
                totals.append(float(t))

        best = max(totals) if totals else None
        latest = totals[-1] if totals else None
        avg = round(sum(totals) / len(totals), 2) if totals else None
        last_updated = max((i.get("updated_at") or "" for i in interviews), default="")

        last_iv = completed[-1] if completed else None
        # 联评综合分：按「面试官权重」加权（未设定时 = 每位面试官等权）
        jt = joint_service.joint_evaluation(r["id"], interviewer_weights=iv_weights or None)

        # 各维度平均分 / 各面试官平均分（用于单维度、单面试官排序与展开明细）
        dim_avgs = joint_service.dimension_averages(r["id"])
        iv_avgs = joint_service.interviewer_averages(r["id"])
        custom = weighted_total(dim_avgs, dim_weights)

        items.append(
            {
                "candidate_id": r["id"],
                "name": r["name"],
                "student_no": r.get("student_no"),
                "major": r.get("major"),
                "grade": r.get("grade"),
                "position": r.get("position"),
                "order_index": r.get("order_index"),
                "resume_found": bool(r.get("resume_exists")),
                "rounds": len(completed),
                "best_score": round(best, 2) if best is not None else None,
                "latest_score": round(latest, 2) if latest is not None else None,
                "avg_score": avg,
                "level": grade_level(best),
                # ---- 自定义维度权重下的加权总分 ----
                "custom_score": custom,
                "custom_level": grade_level(custom),
                "dimension_avgs": dim_avgs,
                "dimension_breakdown": score_breakdown(dim_avgs),
                "interviewer_avgs": iv_avgs,
                # ---- 联评（多面试官综合） ----
                "interviewer_count": jt["interviewer_count"],
                "interviewers": [x["interviewer"] for x in jt["interviewers"]],
                "interviewer_detail": jt["interviewers"],
                "joint_score": jt["joint_score"],
                "joint_score_equal": jt["joint_score_equal"],
                "joint_level": jt["joint_level"],
                "joint_consensus": jt["consensus"],
                "joint_spread": jt["spread"],
                "last_comment": (last_iv or {}).get("comment"),
                "last_updated": last_updated,
                "has_ai_summary": bool((last_iv or {}).get("ai_summary")),
            }
        )

    if min_score is not None:
        items = [i for i in items if (i["best_score"] or -1) >= min_score]
    if level:
        items = [i for i in items if i["level"] == level]

    # ---------------------------------------------------------- 排序
    if sort.startswith("dim:"):
        dim_key = sort[4:]
        items.sort(
            key=lambda it: _num_key((it.get("dimension_avgs") or {}).get(dim_key)),
            reverse=desc,
        )
    elif sort.startswith("iv:"):
        iv_name = sort[3:]
        items.sort(
            key=lambda it: _num_key((it.get("interviewer_avgs") or {}).get(iv_name)),
            reverse=desc,
        )
    elif sort == "name":
        items.sort(key=lambda it: it.get("name") or "", reverse=desc)
    elif sort == "order":
        items.sort(
            key=lambda it: it.get("order_index")
            if it.get("order_index") is not None else 999999
        )
    elif sort == "updated":
        items.sort(key=lambda it: it.get("last_updated") or "", reverse=desc)
    else:
        field = SORTABLE.get(sort, "order_index")
        if field == "order_index":
            items.sort(
                key=lambda it: it.get("order_index")
                if it.get("order_index") is not None else 999999
            )
        else:
            items.sort(key=lambda it: _num_key(it.get(field)), reverse=desc)

    scored = [i["best_score"] for i in items if i["best_score"] is not None]
    customs = [i["custom_score"] for i in items if i["custom_score"] is not None]
    joints = [i["joint_score"] for i in items if i["joint_score"] is not None]
    multi = [i for i in items if (i["interviewer_count"] or 0) > 1]

    all_interviewers: list[str] = []
    for it in items:
        for name in it["interviewer_avgs"]:
            if name not in all_interviewers:
                all_interviewers.append(name)

    return {
        "ok": True,
        "sort": sort,
        "desc": desc,
        "total": len(items),
        "weights": {
            "dimensions": dim_weights,
            "dimension_percent": weights_service.to_percent(dim_weights),
            "dimension_defaults": weights_service.default_dimension_weights(),
            "dimension_default_percent": weights_service.to_percent(
                weights_service.default_dimension_weights()
            ),
            "dimensions_customized": dim_customized,
            "interviewers": iv_weights,
            "interviewer_percent": weights_service.to_percent(iv_weights) if iv_weights else {},
            "interviewers_customized": iv_customized,
            "dimension_labels": weights_service.DIMENSION_LABELS,
        },
        "interviewer_options": all_interviewers,
        # 维度定义（有序，含 label / weight / highlight）→ 前端不必硬编码维度
        "dimensions": settings.SCORE_DIMENSIONS,
        "statistics": {
            "candidates": len(items),
            "scored": len(scored),
            "unscored": len(items) - len(scored),
            "average": round(sum(scored) / len(scored), 2) if scored else None,
            "highest": max(scored) if scored else None,
            "lowest": min(scored) if scored else None,
            "custom_average": round(sum(customs) / len(customs), 2) if customs else None,
            "joint_average": round(sum(joints) / len(joints), 2) if joints else None,
            "multi_interviewer_candidates": len(multi),
            "level_distribution": {
                lv: sum(1 for i in items if i["level"] == lv)
                for lv in ("强烈推荐", "推荐", "待定", "不推荐", "未评分")
            },
        },
        "items": items,
    }


@router.get("/results/{candidate_id}")
def get_result_detail(candidate_id: int):
    cand = db.get_candidate(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")

    interviews = []
    for it in db.list_interviews(candidate_id):
        sc = _jsonify(it.get("scores")) or {}
        it["scores"] = sc
        it["breakdown"] = score_breakdown(sc if isinstance(sc, dict) else {})
        it["level"] = grade_level(it.get("total_score"))
        it["ai_evaluation"] = _jsonify(it.get("ai_evaluation"))
        interviews.append(it)

    totals = [float(i["total_score"]) for i in interviews
              if i.get("status") == "completed" and i.get("total_score") is not None]
    best = max(totals) if totals else None

    iv_weights = weights_service.get_interviewer_weights()
    dim_weights = weights_service.get_dimension_weights()
    dim_avgs = joint_service.dimension_averages(candidate_id)

    return {
        "ok": True,
        "candidate": {k: v for k, v in dict(cand).items()
                      if k not in ("resume_text",)},
        "resume_parsed": _jsonify(cand.get("resume_parsed")),
        "rounds": len([i for i in interviews if i.get("status") == "completed"]),
        "best_score": round(best, 2) if best is not None else None,
        "level": grade_level(best),
        "joint": joint_service.joint_evaluation(
            candidate_id, interviewer_weights=iv_weights or None
        ),
        "dimension_avgs": dim_avgs,
        "interviewer_avgs": joint_service.interviewer_averages(candidate_id),
        "custom_score": weighted_total(dim_avgs, dim_weights),
        "weights": {
            "dimensions": dim_weights,
            "interviewers": iv_weights,
            "dimensions_customized": weights_service.is_dimension_weights_customized(),
            "interviewers_customized": bool(iv_weights),
        },
        "dimensions": settings.SCORE_DIMENSIONS,
        "interviews": interviews,
    }


@router.get("/summary/joint")
def joint_ranking(desc: bool = Query(True, description="是否按联评综合分降序")):
    """联评综合分排行榜：一位候选人一个综合成绩（多面试官平均，可按面试官权重加权）。"""
    iv_weights = weights_service.get_interviewer_weights()
    rows = [
        r for r in joint_service.joint_overview(iv_weights or None)
        if r["joint_score"] is not None
    ]
    rows.sort(key=lambda r: r["joint_score"], reverse=desc)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {
        "ok": True,
        "count": len(rows),
        "weighted": bool(iv_weights),
        "interviewer_weights": iv_weights,
        "rule": (
            "联评综合分 = Σ(各面试官平均分 × 面试官权重) / Σ权重"
            if iv_weights
            else "联评综合分 = 各面试官平均分的平均（每位面试官等权）"
        ),
        "items": rows,
    }


@router.get("/summary/statistics")
def statistics():
    """首页统计卡片数据。"""
    rows = db.list_candidates()
    total = len(rows)
    with_resume = sum(1 for r in rows if r.get("resume_exists"))
    completed_cand = 0
    rounds_total = 0
    scores: list[float] = []

    for r in rows:
        ivs = [i for i in db.list_interviews(r["id"]) if i.get("status") == "completed"]
        if ivs:
            completed_cand += 1
        rounds_total += len(ivs)
        for i in ivs:
            if i.get("total_score") is not None:
                scores.append(float(i["total_score"]))

    order = None
    try:
        from backend.app.services.interview_order_service import load_interview_order

        order = load_interview_order()
    except Exception as exc:
        order = {"loaded": False, "message": str(exc)}

    return {
        "ok": True,
        "candidates": total,
        "candidates_with_resume": with_resume,
        "candidates_interviewed": completed_cand,
        "candidates_pending": total - completed_cand,
        "completed_rounds": rounds_total,
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
        "highest_score": max(scores) if scores else None,
        "interview_order": {
            "source": order.get("source"),
            "exists": order.get("exists"),
            "loaded": order.get("loaded"),
            "rows": len(order.get("rows") or []),
            "message": order.get("message"),
        },
    }
