# -*- coding: utf-8 -*-
"""评分权重服务：维度权重 + 面试官权重的人工设定与持久化。

设计要点：
  1. 默认维度权重来自 config/settings.py 的 SCORE_DIMENSIONS（唯一配置源）；
  2. 人工设定的权重保存在 interview.db 的 app_meta 表 ——
     只写系统自己的库，绝不动原始简历 / 面试顺序表；
  3. 面试官权重默认「未设定」（等价于每位面试官权重 1 = 等权），
     只在联评综合分的计算里生效，不影响单轮存档分；
  4. 保存时做基本校验（非负、至少一项、合计 > 0），非法输入抛 ValueError 由 API 层转 400。

为什么持久化到数据库而不是前端 localStorage？
  面试官经常换设备（答辩现场多台电脑 / 手机），权重属于「评分规则」，
  放后端可让所有端看到同一套规则，避免每台机器各调一套导致结果不一致。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "config"))
import settings  # noqa: E402

from backend.app import db  # noqa: E402

META_DIM_WEIGHTS = "dimension_weights"      # app_meta key：维度权重覆盖值
META_IV_WEIGHTS = "interviewer_weights"     # app_meta key：面试官权重

DIMENSION_KEYS = [d["key"] for d in settings.SCORE_DIMENSIONS]
DIMENSION_LABELS = {d["key"]: d["label"] for d in settings.SCORE_DIMENSIONS}
DEFAULT_DIM_WEIGHTS = {d["key"]: float(d["weight"]) for d in settings.SCORE_DIMENSIONS}


# ------------------------------------------------------------------ 内部工具
def _read_json_meta(key: str) -> dict:
    raw = db.meta_get(key)
    if not raw:
        return {}
    try:
        v = json.loads(raw)
    except Exception:
        return {}
    return v if isinstance(v, dict) else {}


def _as_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def to_percent(d: dict) -> dict[str, float]:
    """
    把任意单位的权重换算成「合计 100 的百分比」，供前端展示。
    这样默认权重（0.30 的小数写法）和用户手填的 60/25/10/3/2
    在前端看起来是同一套口径，不会出现 6000% 这种乌龙。
    """
    total = sum(v for v in d.values() if isinstance(v, (int, float)) and v > 0)
    if total <= 0:
        return {k: 0.0 for k in d}
    return {k: round(v / total * 100, 1) for k, v in d.items()}


# ------------------------------------------------------------------ 维度权重
def default_dimension_weights() -> dict[str, float]:
    """config/settings.py 里写的默认权重。"""
    return dict(DEFAULT_DIM_WEIGHTS)


def get_dimension_weights() -> dict[str, float]:
    """当前生效的维度权重（人工设定优先，未设定/非法项回落默认）。"""
    saved = _read_json_meta(META_DIM_WEIGHTS)
    out = dict(DEFAULT_DIM_WEIGHTS)
    for k, v in saved.items():
        if k not in DEFAULT_DIM_WEIGHTS:
            continue
        fv = _as_float(v)
        if fv is not None and fv >= 0:
            out[k] = round(fv, 4)
    return out


def is_dimension_weights_customized() -> bool:
    """是否与默认权重不同（用于前端决定要不要显示「加权分」列）。"""
    cur = get_dimension_weights()
    for k, default_v in DEFAULT_DIM_WEIGHTS.items():
        if abs(cur.get(k, 0) - default_v) > 1e-9:
            return True
    return False


def set_dimension_weights(weights: dict | None) -> dict[str, float]:
    """
    人工设定维度权重。允许只传部分维度（其余保留默认），
    但至少要有一项，且合计必须大于 0（否则全部为 0 无法归一化）。
    """
    if not isinstance(weights, dict) or not weights:
        raise ValueError("请至少给出一个维度的权重")

    clean: dict[str, float] = {}
    for k, v in weights.items():
        if k not in DEFAULT_DIM_WEIGHTS:
            continue                          # 未知维度直接忽略（向前兼容）
        fv = _as_float(v)
        if fv is None:
            raise ValueError(f"维度「{DIMENSION_LABELS.get(k, k)}」的权重不是数字：{v!r}")
        if fv < 0:
            raise ValueError(f"维度「{DIMENSION_LABELS.get(k, k)}」的权重不能为负数：{fv}")
        clean[k] = round(fv, 4)

    if not clean:
        raise ValueError("没有识别到任何有效维度，权重未修改")
    if sum(clean.values()) <= 0:
        raise ValueError("权重之和必须大于 0")

    db.meta_set(META_DIM_WEIGHTS, json.dumps(clean, ensure_ascii=False))
    return get_dimension_weights()


def reset_dimension_weights() -> dict[str, float]:
    """恢复 config 里的默认权重。"""
    db.meta_set(META_DIM_WEIGHTS, "{}")
    return get_dimension_weights()


# ------------------------------------------------------------------ 面试官权重
def get_interviewer_weights() -> dict[str, float]:
    """面试官权重；返回空 dict 表示「等权」（未做任何人工设定）。"""
    saved = _read_json_meta(META_IV_WEIGHTS)
    out: dict[str, float] = {}
    for k, v in saved.items():
        name = str(k).strip()
        if not name:
            continue
        fv = _as_float(v)
        if fv is not None and fv >= 0:
            out[name] = round(fv, 4)
    return out


def is_interviewer_weights_customized() -> bool:
    """存在人工设定的面试官权重，且不是「所有人都是 1」的等价情况。"""
    w = get_interviewer_weights()
    if not w:
        return False
    vals = list(w.values())
    return any(abs(v - vals[0]) > 1e-9 for v in vals) or abs(vals[0] - 1.0) > 1e-9


def set_interviewer_weights(weights: dict | None) -> dict[str, float]:
    """人工设定面试官权重（key=面试官名，value=权重，默认 1）。"""
    if not isinstance(weights, dict):
        raise ValueError("权重必须是「面试官 -> 权重」的对象")

    clean: dict[str, float] = {}
    for k, v in weights.items():
        name = str(k).strip()
        if not name:
            continue
        fv = _as_float(v)
        if fv is None:
            raise ValueError(f"面试官「{name}」的权重不是数字：{v!r}")
        if fv < 0:
            raise ValueError(f"面试官「{name}」的权重不能为负数：{fv}")
        clean[name] = round(fv, 4)

    if clean and sum(clean.values()) <= 0:
        raise ValueError("所有面试官的权重不能同时为 0")

    db.meta_set(META_IV_WEIGHTS, json.dumps(clean, ensure_ascii=False))
    return get_interviewer_weights()


def reset_interviewer_weights() -> dict[str, float]:
    """清空面试官权重 → 回到「每位面试官等权」。"""
    db.meta_set(META_IV_WEIGHTS, "{}")
    return {}


# ------------------------------------------------------------------ 通用计算
def weighted_average(pairs: list[tuple[float, float]], *, fallback_equal: bool = True):
    """
    归一化加权平均。
      pairs = [(分值, 权重), ...]
    规则：
      - 权重合计 > 0 → Σ(分值×权重) / Σ权重；
      - 权重全为 0（或未提供）→ fallback_equal 时退化为等权平均，否则返回 None。
    """
    if not pairs:
        return None
    wsum = sum(w for _, w in pairs)
    if wsum <= 0:
        if not fallback_equal:
            return None
        wsum = float(len(pairs))
        pairs = [(v, 1.0) for v, _ in pairs]
    return round(sum(v * w for v, w in pairs) / wsum, 2)


def dimension_percent() -> dict[str, float]:
    """当前维度权重的百分比口径（合计 100），前端展示用。"""
    return to_percent(get_dimension_weights())


def interviewer_percent() -> dict[str, float]:
    """当前面试官权重的百分比口径（合计 100）；未设定时返回空 dict（= 等权）。"""
    return to_percent(get_interviewer_weights())


def snapshot() -> dict:
    """给 API / 前端用的权重快照。"""
    dim = get_dimension_weights()
    iv = get_interviewer_weights()
    return {
        "dimensions": dim,
        "dimension_percent": to_percent(dim),
        "dimension_defaults": default_dimension_weights(),
        "dimension_default_percent": to_percent(DEFAULT_DIM_WEIGHTS),
        "dimensions_customized": is_dimension_weights_customized(),
        "interviewers": iv,
        "interviewer_percent": to_percent(iv) if iv else {},
        "interviewers_customized": is_interviewer_weights_customized(),
        "dimension_labels": DIMENSION_LABELS,
        "rule": (
            "维度权重：加权总分 = Σ(维度得分×维度权重) / Σ(已评维度权重)；"
            "面试官权重：联评综合分 = Σ(面试官平均分×面试官权重) / Σ权重（未设则等权）。"
        ),
    }
