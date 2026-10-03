# -*- coding: utf-8 -*-
"""评分权重 API：维度权重 / 面试官权重的人工设定、读取与重置。

为什么单独放一个模块？
  权重属于「评分规则」而不是「面试数据」，接口语义与 candidates/interview/results
  都不同；单独成文件便于日后扩展（例如保存多套「评分方案」供不同场次切换）。

数据安全：只读写系统自己的 interview.db（app_meta 表），
不触碰 E 盘的原始简历与面试顺序表。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services import weights_service

router = APIRouter()


class DimensionWeightsPayload(BaseModel):
    weights: dict[str, float] = Field(
        default_factory=dict,
        description="维度权重，例如 {'professional': 30, 'logic': 25}；"
                    "可只传部分维度，也无需合计为 100（会自动归一化）",
    )


class InterviewerWeightsPayload(BaseModel):
    weights: dict[str, float] = Field(
        default_factory=dict,
        description="面试官权重，例如 {'王老师': 2, '李老师': 1}；"
                    "未出现的面试官默认权重 1，等价于等权",
    )


def _snapshot_response() -> dict:
    return {"ok": True, **weights_service.snapshot()}


@router.get("/settings/weights", tags=["settings"])
def get_weights():
    """读取当前生效的权重（维度权重 + 面试官权重 + 是否被人工改过）。"""
    return _snapshot_response()


@router.post("/settings/weights/dimensions", tags=["settings"])
def set_dimension_weights(payload: DimensionWeightsPayload):
    """人工设定各评分维度的权重（用于重算加权总分）。"""
    try:
        weights_service.set_dimension_weights(payload.weights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _snapshot_response()


@router.delete("/settings/weights/dimensions", tags=["settings"])
def reset_dimension_weights():
    """恢复 config/settings.py 里写的默认维度权重。"""
    weights_service.reset_dimension_weights()
    return _snapshot_response()


@router.post("/settings/weights/interviewers", tags=["settings"])
def set_interviewer_weights(payload: InterviewerWeightsPayload):
    """人工设定各面试官的权重（用于联评综合分加权）。"""
    try:
        weights_service.set_interviewer_weights(payload.weights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _snapshot_response()


@router.delete("/settings/weights/interviewers", tags=["settings"])
def reset_interviewer_weights():
    """清空面试官权重 → 回到每位面试官等权。"""
    weights_service.reset_interviewer_weights()
    return _snapshot_response()
