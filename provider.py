# -*- coding: utf-8 -*-
"""
AI Provider 抽象层

核心设计（题目硬性要求）：
  - 上层（API / 前端）只依赖 `get_provider()` 返回的统一接口；
  - 切换 AI 实现只需改配置（AI_PROVIDER），**前端代码一行都不用动**；
  - 没有 API Key 时系统仍能完整运行（默认 mock provider）。

统一接口：
  provider.name                                     -> str
  provider.is_available()                           -> bool
  provider.extract_resume(text, filename)           -> dict
  provider.summarize_interview(payload)             -> str
  provider.evaluate_candidate(payload)              -> dict

新增一个 AI 后端 = 新增一个子类 + 在 _REGISTRY 注册，不改任何调用方。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "config"))
import settings  # noqa: E402


class AIProviderError(RuntimeError):
    """AI 调用失败。上层捕获后必须降级（不能用异常把接口打崩）。"""


class BaseAIProvider:
    name = "base"

    # ---- 子类必须实现 -------------------------------------------------
    def is_available(self) -> bool:
        raise NotImplementedError

    def extract_resume(self, text: str, filename: str = "") -> dict:
        """从简历文本抽取结构化信息 -> {name, student_no, major, grade, ...}"""
        raise NotImplementedError

    def summarize_interview(self, payload: dict) -> str:
        """生成面试总结文本。"""
        raise NotImplementedError

    def evaluate_candidate(self, payload: dict) -> dict:
        """生成智能评估 -> {summary, strengths[], weaknesses[], suggestion, ...}"""
        raise NotImplementedError

    # ---- 公共工具 -----------------------------------------------------
    @staticmethod
    def _ask_json(prompt: str) -> Any:
        """给子类用：向模型提问并解析 JSON（容错提取 ```json 代码块）。"""
        raise NotImplementedError


# =====================================================================
# Mock Provider —— 纯规则实现，零依赖、零网络、永远可用（默认）
# =====================================================================
class MockAIProvider(BaseAIProvider):
    """
    无 API Key 也能跑的规则型 Provider。
    它不是"假功能"：抽取/总结/评估都基于真实输入文本做确定性计算，
    结果可复现，且已足够支撑面试流程闭环。接入 DeepSeek 后由真实模型接管。
    """
    name = "mock"

    _MAJOR_KEYWORDS = [
        "计算机科学与技术", "软件工程", "人工智能", "数据科学与大数据技术",
        "网络工程", "信息安全", "电子信息工程", "通信工程", "自动化",
        "机械工程", "机械设计制造及其自动化", "电气工程及其自动化",
        "材料科学与工程", "土木工程", "工商管理", "会计学", "金融学",
        "市场营销", "汉语言文学", "英语", "数学与应用数学", "物理学", "化学",
    ]
    _DEGREE_KEYWORDS = ["博士", "硕士", "研究生", "本科", "学士", "大专", "专科"]
    _SKILL_KEYWORDS = [
        "Python", "Java", "C++", "C#", "JavaScript", "TypeScript", "Go", "Rust",
        "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis",
        "Django", "Flask", "FastAPI", "Spring", "SpringBoot", "React", "Vue",
        "Node.js", "Docker", "Kubernetes", "Linux", "Git",
        "机器学习", "深度学习", "PyTorch", "TensorFlow", "数据分析", "爬虫",
        "SolidWorks", "AutoCAD", "ANSYS", "MATLAB", "PLC", "STM32", "嵌入式",
        "Photoshop", "Excel", "PowerPoint", "WPS",
    ]
    _POSITION_KEYWORDS = [
        "后端开发", "前端开发", "全栈开发", "算法工程师", "数据分析师",
        "测试工程师", "运维工程师", "产品经理", "机械设计", "电气工程师",
        "嵌入式开发", "硬件工程师", "技术支持", "销售", "人力资源", "财务",
    ]

    def is_available(self) -> bool:
        return True

    def extract_resume(self, text: str, filename: str = "") -> dict:
        import re

        text = text or ""
        flat = re.sub(r"[ \t\u3000]+", " ", text)
        result: dict[str, Any] = {"extracted_by": self.name, "confidence": "rule-based"}

        # --- 姓名：优先"姓名/名字：X"，否则取首行 2~4 个中文字符 ---
        m = re.search(r"(?:姓\s*名|名字|Name)\s*[:：]?\s*([\u4e00-\u9fa5]{2,4})", flat, re.I)
        if m:
            result["name"] = m.group(1)
        else:
            for line in [l.strip() for l in flat.splitlines() if l.strip()][:5]:
                if 2 <= len(line) <= 4 and re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", line):
                    result["name"] = line
                    break

        # --- 学号 ---
        m = re.search(r"(?:学\s*号|学籍号|Student\s*I[Dd])\s*[:：]?\s*([A-Za-z0-9\-]{4,20})", flat, re.I)
        if m:
            result["student_no"] = m.group(1)
        else:
            m = re.search(r"\b(20\d{2}\d{4,10})\b", flat)
            if m:
                result["student_no"] = m.group(1)

        # --- 专业 ---
        for kw in self._MAJOR_KEYWORDS:
            if kw in flat:
                result["major"] = kw
                break

        # --- 学历 / 年级 ---
        for kw in self._DEGREE_KEYWORDS:
            if kw in flat:
                result["degree"] = kw
                break
        m = re.search(r"(大[一二三四]|研[一二三]|应届|20\d{2}\s*届)", flat)
        if m:
            result["grade"] = m.group(1)

        # --- 联系方式 ---
        m = re.search(r"1[3-9]\d{9}", flat)
        if m:
            result["phone"] = m.group(0)
        m = re.search(r"[\w.\-+]+@[\w\-]+\.[\w.\-]+", flat)
        if m:
            result["email"] = m.group(0)

        # --- 应聘岗位 ---
        m = re.search(r"(?:应聘|意向|目标)\s*(?:岗位|职位)\s*[:：]?\s*([^\n，,。;；]{2,20})", flat)
        if m:
            result["position"] = m.group(1).strip()
        else:
            for kw in self._POSITION_KEYWORDS:
                if kw in flat:
                    result["position"] = kw
                    break

        # --- 技能 ---
        skills = [s for s in self._SKILL_KEYWORDS if s.lower() in flat.lower()]
        result["skills"] = skills

        # --- 实习/项目经历条数（粗估，用于评估参考）---
        proj_hits = len(re.findall(r"(?:项目|实习|实践)经历|项目名称|实习经历", flat))
        result["experience_blocks"] = proj_hits

        # --- 文本统计 ---
        result["text_length"] = len(text)
        result["filename"] = filename
        return result

    def summarize_interview(self, payload: dict) -> str:
        cand = payload.get("candidate") or {}
        scores = payload.get("scores") or {}
        dims = {d["key"]: d["label"] for d in settings.SCORE_DIMENSIONS}
        total = payload.get("total_score")

        parts = []
        parts.append(
            f"{cand.get('name', '该候选人')}"
            f"（{cand.get('major') or '专业未填'}）"
            f"{'第' + str(payload.get('round', 1)) + '轮' if payload.get('round', 1) > 1 else ''}"
            f"面试已完成。"
        )
        if scores:
            pairs = "、".join(f"{dims.get(k, k)} {v} 分" for k, v in scores.items())
            parts.append(f"各维度得分：{pairs}。")
        if total is not None:
            parts.append(f"加权总分 {total} 分（满分 {settings.SCORE_MAX:.0f}）。")

        if scores:
            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
            hi_key, hi_val = ranked[0]
            lo_key, lo_val = ranked[-1]
            parts.append(
                f"相对优势在于{dims.get(hi_key, hi_key)}（{hi_val} 分），"
                f"相对短板是{dims.get(lo_key, lo_key)}（{lo_val} 分）。"
            )

        comment = (payload.get("comment") or "").strip()
        if comment:
            parts.append(f"面试官补充评价：{comment}")
        parts.append(f"（本总结由 {self.name} provider 生成）")
        return "".join(parts)

    def evaluate_candidate(self, payload: dict) -> dict:
        scores = payload.get("scores") or {}
        dims = settings.SCORE_DIMENSIONS
        total = payload.get("total_score")
        if total is None and scores:
            total = sum(scores.get(d["key"], 0) * d["weight"] for d in dims)
            total = round(total, 2)

        # 优势/短板按"加权贡献"排序，比单纯比分数更贴近真实评估
        contrib = [(d, scores.get(d["key"], 0) * d["weight"]) for d in dims if d["key"] in scores]
        contrib.sort(key=lambda x: x[1], reverse=True)

        strengths, weaknesses = [], []
        for d, c in contrib[:2]:
            v = scores.get(d["key"], 0)
            if v >= 60:
                strengths.append(f"{d['label']}表现良好（{v} 分）")
        for d, c in contrib[-2:]:
            v = scores.get(d["key"], 0)
            if v < 70:
                weaknesses.append(f"{d['label']}有待加强（{v} 分）")

        if total is None:
            level, suggestion = "数据不足", "尚未完成评分，无法给出建议。"
        elif total >= 85:
            level, suggestion = "强烈推荐", "综合表现优秀，建议进入下一轮或直接推荐录用。"
        elif total >= 75:
            level, suggestion = "推荐", "整体达到岗位要求，建议进入下一轮深入考察。"
        elif total >= 60:
            level, suggestion = "待定", "基础尚可但有明显短板，建议加试或对比其他候选人后再定。"
        else:
            level, suggestion = "不推荐", "当前表现与岗位要求差距较大，建议暂不进入下一轮。"

        return {
            "provider": self.name,
            "total_score": total,
            "level": level,
            "summary": (
                f"综合加权得分 {total} 分，评价等级：{level}。"
                if total is not None else "暂无评分数据。"
            ),
            "strengths": strengths or ["暂无明显突出项"],
            "weaknesses": weaknesses or ["暂无明显短板"],
            "suggestion": suggestion,
            "dimension_detail": [
                {
                    "key": d["key"],
                    "label": d["label"],
                    "weight": d["weight"],
                    "score": scores.get(d["key"]),
                    "weighted": round(scores.get(d["key"], 0) * d["weight"], 2)
                    if d["key"] in scores else None,
                }
                for d in dims
            ],
        }


# =====================================================================
# DeepSeek Provider —— 真实大模型（需要 API Key）
# =====================================================================
class DeepSeekAIProvider(BaseAIProvider):
    """
    通过 DeepSeek 官方 OpenAI 兼容接口调用。
    失败时由 API 层捕获并自动降级到 MockAIProvider，保证服务不崩。
    """
    name = "deepseek"

    def __init__(self) -> None:
        self.api_key = settings.DEEPSEEK_API_KEY
        self.base_url = settings.DEEPSEEK_BASE_URL.rstrip("/")
        self.model = settings.DEEPSEEK_MODEL
        self.timeout = settings.AI_TIMEOUT_SECONDS

    def is_available(self) -> bool:
        return bool(self.api_key)

    # ---------------------------------------------------------------- HTTP
    def _chat(self, messages: list[dict], json_mode: bool = False) -> str:
        import urllib.error
        import urllib.request

        if not self.api_key:
            raise AIProviderError("未配置 DEEPSEEK_API_KEY，无法调用 DeepSeek。")

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise AIProviderError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise AIProviderError(f"DeepSeek 请求失败: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIProviderError(f"DeepSeek 返回格式异常: {data}") from exc

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """容错解析：模型可能返回 ```json ... ``` 包裹。"""
        s = (raw or "").strip()
        if s.startswith("```"):
            s = s.split("```")[1]
            if s.lstrip().lower().startswith("json"):
                s = s.lstrip()[4:]
        s = s.strip().strip("`").strip()
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            i, j = s.find("{"), s.rfind("}")
            if i >= 0 and j > i:
                return json.loads(s[i:j + 1])
            raise AIProviderError(f"无法解析模型返回的 JSON: {raw[:300]}")

    # ---------------------------------------------------------------- 接口实现
    def extract_resume(self, text: str, filename: str = "") -> dict:
        from .prompts import RESUME_EXTRACT_SYSTEM, resume_extract_user

        raw = self._chat(
            [
                {"role": "system", "content": RESUME_EXTRACT_SYSTEM},
                {"role": "user", "content": resume_extract_user(text, filename)},
            ],
            json_mode=True,
        )
        data = self._parse_json(raw)
        data["extracted_by"] = self.name
        return data

    def summarize_interview(self, payload: dict) -> str:
        from .prompts import INTERVIEW_SUMMARY_SYSTEM, interview_summary_user

        return self._chat(
            [
                {"role": "system", "content": INTERVIEW_SUMMARY_SYSTEM},
                {"role": "user", "content": interview_summary_user(payload)},
            ]
        ).strip()

    def evaluate_candidate(self, payload: dict) -> dict:
        from .prompts import EVALUATE_SYSTEM, evaluate_user

        raw = self._chat(
            [
                {"role": "system", "content": EVALUATE_SYSTEM},
                {"role": "user", "content": evaluate_user(payload)},
            ],
            json_mode=True,
        )
        data = self._parse_json(raw)
        data["provider"] = self.name
        return data


# =====================================================================
# 工厂 —— 全局唯一入口
# =====================================================================
_REGISTRY: dict[str, type[BaseAIProvider]] = {
    "mock": MockAIProvider,
    "deepseek": DeepSeekAIProvider,
}


def get_provider(name: str | None = None) -> BaseAIProvider:
    """
    取得 AI Provider 实例。
    - 未指定则用配置里的 AI_PROVIDER；
    - 名称未知 / 实例不可用（如无 Key）→ **自动降级**为 mock，保证系统永远能跑。
    """
    wanted = (name or settings.AI_PROVIDER or "mock").lower().strip()
    cls = _REGISTRY.get(wanted)
    if cls is None:
        print(f"[ai][WARN] 未知 provider '{wanted}'，降级为 mock")
        return MockAIProvider()
    inst = cls()
    if not inst.is_available():
        print(f"[ai][WARN] provider '{wanted}' 不可用（可能缺少 API Key），降级为 mock")
        return MockAIProvider()
    return inst


def available_providers() -> list[dict]:
    out = []
    for key, cls in _REGISTRY.items():
        try:
            ok = cls().is_available()
        except Exception:
            ok = False
        out.append({"name": key, "available": ok})
    return out
