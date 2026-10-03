# -*- coding: utf-8 -*-
"""联评（多面试官综合评分）服务。

背景：一位候选人可能被 1 位、2 位、3~4 位面试官分别面试并打分，
需要一个「综合成绩」把所有面试官的评价合到一起。

计算规则（避免某位面试官多面几轮就放大其权重）：
  1. 只统计「已完成」的面试记录（status=completed，或 in_progress 但已打分）；
  2. 每位面试官先算自己的平均分（该面试官所有已评分轮次的平均）；
  3. 联评综合分 = 各面试官平均分的平均 —— 每位面试官权重相同；
  4. 同时给出分歧度（各面试官平均分的标准差）、最高/最低面试官分数，
     便于看出「评委意见是否一致」。

数据安全：全程只读 interview.db，不写不改任何记录。
"""
from __future__ import annotations

import json
import statistics

from backend.app import db
from backend.app.services.scoring_service import grade_level, weighted_total

DEFAULT_INTERVIEWER = "（未填写面试官）"


def jsonify(v):
    """scores 字段在库里是 JSON 字符串，这里安全还原为 dict。"""
    if isinstance(v, str) and v:
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


def completed_rounds(interviews: list[dict]) -> list[dict]:
    """哪些记录算「已完成的面试」（与结果汇总页口径一致）。"""
    out = []
    for i in interviews:
        if i.get("status") == "completed":
            out.append(i)
            continue
        sc = jsonify(i.get("scores"))
        if isinstance(sc, dict) and any(v is not None for v in sc.values()):
            out.append(i)
    return out


def score_of(rec: dict) -> float | None:
    """取一条面试记录的加权总分（缺失则用评分现算）。"""
    t = rec.get("total_score")
    if t is None:
        sc = jsonify(rec.get("scores")) or {}
        t = weighted_total(sc if isinstance(sc, dict) else {})
    return round(float(t), 2) if t is not None else None


def _consensus(std: float | None, n: int) -> str:
    if n <= 1:
        return "仅 1 位面试官"
    if std is None:
        return "样本不足"
    if std <= 4:
        return "高度一致"
    if std <= 8:
        return "基本一致"
    return "分歧较大"


def joint_evaluation(candidate_id: int, interviewer_weights: dict | None = None) -> dict:
    """
    某位候选人的联评综合评分明细。

    interviewer_weights（可选）：人工设定的面试官权重 {面试官名: 权重}。
      - 不传 / 传空 → 每位面试官等权（与历史行为完全一致）；
      - 传了 → 联评综合分 = Σ(面试官平均分 × 权重) / Σ权重，
        未在权重表里出现的面试官默认权重 1（即「只调整个别人」也能用）。
    分歧度（σ）仍按各面试官平均分计算，与权重无关。
    """
    interviews = db.list_interviews(candidate_id)
    completed = completed_rounds(interviews)

    by_name: dict[str, list[float]] = {}
    round_rows: list[dict] = []

    for rec in completed:
        s = score_of(rec)
        if s is None:
            continue
        name = (rec.get("interviewer") or "").strip() or DEFAULT_INTERVIEWER
        by_name.setdefault(name, []).append(s)
        round_rows.append(
            {
                "round": rec.get("round"),
                "interviewer": name,
                "total_score": s,
                "comment": rec.get("comment"),
                "updated_at": rec.get("updated_at") or rec.get("submitted_at"),
            }
        )

    interviewers = []
    for name, vals in by_name.items():
        avg = round(sum(vals) / len(vals), 2)
        interviewers.append(
            {
                "interviewer": name,
                "rounds": len(vals),
                "scores": [round(v, 2) for v in vals],
                "avg_score": avg,
                "best_score": round(max(vals), 2),
                "level": grade_level(avg),
            }
        )
    # 分数高的面试官排前面
    interviewers.sort(key=lambda x: (-x["avg_score"], x["interviewer"]))

    avgs = [i["avg_score"] for i in interviewers]
    equal_joint = round(sum(avgs) / len(avgs), 2) if avgs else None

    # ---- 面试官权重（人工设定）；未设定时与等权结果完全一致 ----
    weights_map: dict[str, float] = {}
    if interviewer_weights:
        for k, v in interviewer_weights.items():
            name = str(k).strip()
            if not name:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv >= 0:
                weights_map[name] = fv
    weights_applied = bool(weights_map)
    for iv in interviewers:
        iv["weight"] = round(weights_map.get(iv["interviewer"], 1.0), 4)
    if avgs:
        pairs = [(iv["avg_score"], iv["weight"]) for iv in interviewers]
        weighted_joint = round(
            sum(v * w for v, w in pairs) / sum(w for _, w in pairs), 2
        ) if sum(w for _, w in pairs) > 0 else equal_joint
    else:
        weighted_joint = None
    joint = weighted_joint if weights_applied else equal_joint

    all_scores = [v for vals in by_name.values() for v in vals]

    std = round(statistics.pstdev(avgs), 2) if len(avgs) > 1 else None
    spread = round(max(avgs) - min(avgs), 2) if len(avgs) > 1 else 0.0

    return {
        "ok": True,
        "candidate_id": candidate_id,
        "has_data": bool(interviewers),
        "interviewer_count": len(interviewers),
        "joint_score": joint,
        "joint_score_equal": equal_joint,
        "weights_applied": weights_applied,
        "joint_level": grade_level(joint),
        "best_score": round(max(all_scores), 2) if all_scores else None,
        "lowest_score": round(min(all_scores), 2) if all_scores else None,
        "avg_all_rounds": round(sum(all_scores) / len(all_scores), 2) if all_scores else None,
        "rounds_considered": len(round_rows),
        "spread": spread,
        "std": std,
        "consensus": _consensus(std, len(avgs)),
        "interviewers": interviewers,
        "rounds": sorted(round_rows, key=lambda r: (r.get("round") or 0)),
        "rule": (
            "联评综合分 = Σ(各面试官平均分 × 面试官权重) / Σ权重"
            if weights_applied
            else "联评综合分 = 各面试官平均分的平均（每位面试官等权，避免多面几轮放大权重）"
        ),
    }


def joint_overview(interviewer_weights: dict | None = None) -> list[dict]:
    """全部候选人的联评综合分（供排行榜 / 汇总使用）。"""
    out = []
    for row in db.list_candidates():
        j = joint_evaluation(row["id"], interviewer_weights=interviewer_weights)
        out.append(
            {
                "candidate_id": row["id"],
                "name": row.get("name"),
                "order_index": row.get("order_index"),
                "major": row.get("major"),
                "position": row.get("position"),
                "interviewer_count": j["interviewer_count"],
                "joint_score": j["joint_score"],
                "joint_score_equal": j["joint_score_equal"],
                "joint_level": j["joint_level"],
                "spread": j["spread"],
                "consensus": j["consensus"],
            }
        )
    return out


def dimension_averages(candidate_id: int) -> dict[str, float]:
    """
    某位候选人在**所有已评分轮次**上的各维度平均分。
    用于结果页「按某个维度排序」以及自定义权重下的加权总分重算。
    """
    from backend.app.services.scoring_service import DIMENSION_KEYS

    acc: dict[str, list[float]] = {k: [] for k in DIMENSION_KEYS}
    for rec in completed_rounds(db.list_interviews(candidate_id)):
        sc = jsonify(rec.get("scores"))
        if not isinstance(sc, dict):
            continue
        for k in DIMENSION_KEYS:
            v = sc.get(k)
            if isinstance(v, (int, float)):
                acc[k].append(float(v))
    return {
        k: round(sum(vs) / len(vs), 2)
        for k, vs in acc.items()
        if vs
    }


def interviewer_averages(candidate_id: int) -> dict[str, float]:
    """某位候选人「每位面试官的平均分」{面试官名: 平均分}（用于按面试官排序）。"""
    acc: dict[str, list[float]] = {}
    for rec in completed_rounds(db.list_interviews(candidate_id)):
        s = score_of(rec)
        if s is None:
            continue
        name = (rec.get("interviewer") or "").strip() or DEFAULT_INTERVIEWER
        acc.setdefault(name, []).append(s)
    return {k: round(sum(vs) / len(vs), 2) for k, vs in acc.items()}
