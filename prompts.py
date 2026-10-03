# -*- coding: utf-8 -*-
"""AI Prompt 模板集中管理（只有 DeepSeek provider 会用到，mock 不需要）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "config"))
import settings  # noqa: E402

RESUME_EXTRACT_SYSTEM = (
    "你是一名严谨的简历信息抽取助手。"
    "只能依据用户提供的简历原文抽取信息，绝对不允许编造或推测不存在的内容。"
    "找不到的字段一律返回 null。"
    "必须只输出一个 JSON 对象，不要输出任何解释文字。"
)

RESUME_JSON_SCHEMA = {
    "name": "姓名(string|null)",
    "student_no": "学号(string|null)",
    "major": "专业(string|null)",
    "grade": "年级/届别(string|null)",
    "degree": "学历(string|null)",
    "position": "应聘岗位(string|null)",
    "phone": "手机号(string|null)",
    "email": "邮箱(string|null)",
    "skills": ["技能关键词(string数组)"],
    "summary": "一句话概括该候选人(string)",
}


def resume_extract_user(text: str, filename: str = "") -> str:
    dims = "、".join(d["label"] for d in settings.SCORE_DIMENSIONS)
    return (
        f"文件名：{filename}\n"
        f"请从下面的简历原文中抽取字段，返回 JSON，字段定义：\n"
        f"{json.dumps(RESUME_JSON_SCHEMA, ensure_ascii=False, indent=2)}\n\n"
        f"提示：本系统后续会从这些维度评估候选人——{dims}。\n"
        f"如果简历中出现了与该岗位相关的经历，可放入 summary。\n\n"
        f"===== 简历原文开始 =====\n{text[:12000]}\n===== 简历原文结束 ====="
    )


INTERVIEW_SUMMARY_SYSTEM = (
    "你是一名面试记录整理助手。请用 3~5 句中文，客观总结该候选人的面试表现，"
    "包含：整体印象、得分体现出的优势与短板、面试官评价要点。"
    "只依据给定数据，不要编造事实，不要输出 JSON。"
)


def interview_summary_user(payload: dict) -> str:
    cand = payload.get("candidate") or {}
    dims = {d["key"]: d["label"] for d in settings.SCORE_DIMENSIONS}
    scores = payload.get("scores") or {}
    pretty = {dims.get(k, k): v for k, v in scores.items()}
    return (
        f"候选人：{cand.get('name')} | 专业：{cand.get('major')} | "
        f"应聘岗位：{cand.get('position')}\n"
        f"第 {payload.get('round', 1)} 轮面试\n"
        f"各维度得分：{json.dumps(pretty, ensure_ascii=False)}\n"
        f"加权总分：{payload.get('total_score')}\n"
        f"面试官评价：{payload.get('comment') or '（无）'}"
    )


EVALUATE_SYSTEM = (
    "你是一名资深招聘评估专家。请基于给定的面试评分与简历信息，"
    "输出严格 JSON，字段：summary(string)、level(string，"
    "取值必须为 强烈推荐/推荐/待定/不推荐 之一)、"
    "strengths(string数组)、weaknesses(string数组)、suggestion(string)。"
    "结论必须与分数一致，不要编造简历中没有的经历。只输出 JSON。"
)


def evaluate_user(payload: dict) -> str:
    cand = payload.get("candidate") or {}
    dims = {d["key"]: d["label"] for d in settings.SCORE_DIMENSIONS}
    scores = payload.get("scores") or {}
    pretty = {dims.get(k, k): v for k, v in scores.items()}
    resume_parsed = cand.get("resume_parsed")
    if isinstance(resume_parsed, str):
        try:
            resume_parsed = json.loads(resume_parsed)
        except Exception:
            resume_parsed = {"raw": resume_parsed[:800]}
    return (
        f"候选人：{cand.get('name')} | 专业：{cand.get('major')} | "
        f"学历：{cand.get('degree')} | 应聘岗位：{cand.get('position')}\n"
        f"简历要点：{json.dumps(resume_parsed, ensure_ascii=False)[:2000]}\n"
        f"各维度得分：{json.dumps(pretty, ensure_ascii=False)}\n"
        f"加权总分：{payload.get('total_score')}\n"
        f"面试官评价：{payload.get('comment') or '（无）'}\n"
        f"请给出评估结论。"
    )
