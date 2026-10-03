# -*- coding: utf-8 -*-
"""
评分服务：把「各维度原始分」换算成「加权总分」，并提供校验与等级划分。

规则与前端共享同一份维度定义（settings.SCORE_DIMENSIONS），
因此前端改维度不会与后端脱节（改配置即可，两处同时生效）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "config"))
import settings  # noqa: E402

DIMENSION_KEYS = [d["key"] for d in settings.SCORE_DIMENSIONS]
DIMENSION_LABELS = {d["key"]: d["label"] for d in settings.SCORE_DIMENSIONS}
DIMENSION_WEIGHTS = {d["key"]: d["weight"] for d in settings.SCORE_DIMENSIONS}


class ScoreValidationError(ValueError):
    """评分数值非法（越界 / 非数字 / 未知维度）。"""


def validate_scores(raw: dict | None) -> dict[str, float]:
    """
    校验并归一化评分字典。
    - 未知维度直接忽略（不报错，避免前端加字段就 500）；
    - 数值必须在 [SCORE_MIN, SCORE_MAX]，否则抛错（异常由 API 层转 400）。
    """
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ScoreValidationError("scores 必须是对象（维度 -> 分值）")

    out: dict[str, float] = {}
    for k, v in raw.items():
        if k not in DIMENSION_WEIGHTS:
            continue
        if v is None or v == "":
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            raise ScoreValidationError(f"维度 {DIMENSION_LABELS.get(k, k)} 的分值不是数字：{v!r}")
        if fv < settings.SCORE_MIN or fv > settings.SCORE_MAX:
            raise ScoreValidationError(
                f"维度 {DIMENSION_LABELS.get(k, k)} 的分值 {fv} 超出允许范围 "
                f"[{settings.SCORE_MIN:g}, {settings.SCORE_MAX:g}]"
            )
        out[k] = round(fv, 2)
    return out


def weighted_total(scores: dict | None, weights: dict | None = None) -> float | None:
    """
    加权总分。
    只对"已打分的维度"做权重归一化：
        total = Σ(分值 × 权重) / Σ(已填维度的权重)
    这样部分打分时不会因为缺项被无谓拉低，全部维度都填时就是标准加权平均。

    weights 为可选的人工设定权重（{维度key: 权重}）；
    不传时使用 config/settings.py 中的默认权重 —— 因此既有调用行为完全不变。
    权重可以是任意正数（如 30 / 25 / 20 / 15 / 10 的百分比写法），
    内部会自动归一化，不必保证合计为 1 或 100。
    """
    scores = scores or {}
    w = weights if weights else DIMENSION_WEIGHTS

    def _w(k: str) -> float:
        try:
            return float(w.get(k, 0))
        except (TypeError, ValueError):
            return 0.0

    hit = {k: float(v) for k, v in scores.items() if k in DIMENSION_WEIGHTS and v is not None}
    if not hit:
        return None
    wsum = sum(_w(k) for k in hit)
    if wsum <= 0:
        # 人工设定的权重把已评维度全部设成了 0 → 退化为等权，避免总分凭空消失
        wsum = float(len(hit))
        raw = sum(hit.values())
    else:
        raw = sum(hit[k] * _w(k) for k in hit)
    return round(raw / wsum, 2)


def grade_level(total: float | None) -> str:
    if total is None:
        return "未评分"
    if total >= 85:
        return "强烈推荐"
    if total >= 75:
        return "推荐"
    if total >= 60:
        return "待定"
    return "不推荐"


def score_breakdown(scores: dict | None) -> list[dict]:
    """给结果页/详情页用的逐维度明细。"""
    scores = scores or {}
    out = []
    for d in settings.SCORE_DIMENSIONS:
        v = scores.get(d["key"])
        out.append(
            {
                "key": d["key"],
                "label": d["label"],
                "weight": d["weight"],
                "weight_pct": f"{d['weight'] * 100:.0f}%",
                "highlight": bool(d.get("highlight")),   # 前端据此放大显示（综合评分）
                "score": v,
                "weighted": round(float(v) * d["weight"], 2) if v is not None else None,
            }
        )
    return out
