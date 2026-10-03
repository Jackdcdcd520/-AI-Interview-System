# -*- coding: utf-8 -*-
"""
InterviewSystem 全局配置（唯一配置源）

设计原则：
  1. 所有路径 / 端口 / AI 配置集中在本文件，其它模块一律从这里导入，禁止散落硬编码。
  2. 优先读取同目录下的 settings.json（便于用户不碰代码地调整路径）。
  3. 目录不存在时自动创建（resumes / data / database），不存在的简历目录只给警告不报错。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# ---------------------------------------------------------------- 项目根定位
CONFIG_DIR = Path(__file__).resolve().parent            # .../InterviewSystem/config
PROJECT_ROOT = CONFIG_DIR.parent                        # .../InterviewSystem
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
LOGS_DIR = PROJECT_ROOT / "logs"


def _load_json_config() -> dict:
    """读取 settings.json（若存在）。用户可在其中覆盖 E 盘路径等。"""
    f = CONFIG_DIR / "settings.json"
    if f.is_file():
        try:
            with f.open("r", encoding="utf-8") as fp:
                return json.load(fp) or {}
        except Exception as exc:            # 配置坏了不能拖垮整个系统
            print(f"[config][WARN] settings.json 解析失败，改用默认配置：{exc}")
    return {}


_USER_CFG = _load_json_config()


def _cfg(key: str, default):
    return _USER_CFG.get(key, default)


# ---------------------------------------------------------------- E 盘数据区
# 简历与面试数据默认放 E 盘（题目要求）；E 盘不可用时回落到项目内 data/ 目录。
E_ROOT = Path(_cfg("e_root", r"E:\InterviewSystem"))

RESUME_DIR = Path(_cfg("resume_dir", str(E_ROOT / "Resumes")))
DATA_DIR = Path(_cfg("data_dir", str(E_ROOT / "Data")))
DB_DIR = Path(_cfg("db_dir", str(E_ROOT / "Database")))

INTERVIEW_ORDER_XLSX = Path(
    _cfg("interview_order_xlsx", str(DATA_DIR / "interview_order.xlsx"))
)
DB_PATH = Path(_cfg("db_path", str(DB_DIR / "interview.db")))

# 仅这些目录需要"必须存在"（缺失则创建）；简历目录缺失只警告
for _d in (DATA_DIR, DB_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"[config][WARN] 无法创建目录 {_d}：{exc}")


# ---------------------------------------------------------------- 服务端口
BACKEND_HOST = _cfg("backend_host", "127.0.0.1")
BACKEND_PORT = int(_cfg("backend_port", 8000))
FRONTEND_HOST = _cfg("frontend_host", "127.0.0.1")
FRONTEND_PORT = int(_cfg("frontend_port", 5173))

BACKEND_BASE_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

# CORS 允许来源（Vite 默认端口 + 后端自身）
CORS_ORIGINS = _cfg(
    "cors_origins",
    [
        f"http://{FRONTEND_HOST}:{FRONTEND_PORT}",
        f"http://localhost:{FRONTEND_PORT}",
        f"http://127.0.0.1:{FRONTEND_PORT}",
        BACKEND_BASE_URL,
    ],
)

# ---------------------------------------------------------------- AI Provider
# AI_PROVIDER: mock（默认，无需 API Key） | deepseek
# 切换方式：改这里 / 改 settings.json / 设环境变量 INTERVIEW_AI_PROVIDER
AI_PROVIDER = os.environ.get(
    "INTERVIEW_AI_PROVIDER", _cfg("ai_provider", "mock")
).strip().lower()

DEEPSEEK_API_KEY = os.environ.get(
    "DEEPSEEK_API_KEY", _cfg("deepseek_api_key", "")
).strip()
DEEPSEEK_BASE_URL = _cfg("deepseek_base_url", "https://api.deepseek.com")
DEEPSEEK_MODEL = _cfg("deepseek_model", "deepseek-chat")
AI_TIMEOUT_SECONDS = int(_cfg("ai_timeout_seconds", 60))

# ---------------------------------------------------------------- 简历预览
# .doc（老格式）用本机 Word/WPS COM 转成 PDF 后预览；转换结果缓存在项目内，
# 不写 E 盘数据区（原始简历永远只读）。
DOC_PREVIEW_CACHE_DIR = Path(
    _cfg("doc_preview_cache_dir", str(PROJECT_ROOT / ".cache" / "doc_preview"))
)
DOC_CONVERT_TIMEOUT_SECONDS = int(_cfg("doc_convert_timeout_seconds", 60))

# ---------------------------------------------------------------- 业务参数
# 四个评分维度（前端与后端共用同一份定义，避免两处不一致）
# highlight=True 的维度在前端做「放大显示」（综合评分 = 面试官总体印象分）。
SCORE_DIMENSIONS = _cfg(
    "score_dimensions",
    [
        {"key": "character", "label": "性格沟通", "weight": 0.30},
        {"key": "ability", "label": "工作能力", "weight": 0.30},
        {"key": "potential", "label": "发展潜力", "weight": 0.20},
        {"key": "overall", "label": "综合评分", "weight": 0.20, "highlight": True},
    ],
)
SCORE_MIN = float(_cfg("score_min", 0))
SCORE_MAX = float(_cfg("score_max", 100))

# 所有 API 统一前缀
API_PREFIX = "/api"

APP_TITLE = "学生面试管理与智能评估系统"
APP_VERSION = "1.0.0"


def describe() -> dict:
    """给 /api/health 与启动日志用的配置快照（不含密钥明文）。"""
    return {
        "project_root": str(PROJECT_ROOT),
        "e_root": str(E_ROOT),
        "resume_dir": str(RESUME_DIR),
        "resume_dir_exists": RESUME_DIR.is_dir(),
        "data_dir": str(DATA_DIR),
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.is_file(),
        "interview_order_xlsx": str(INTERVIEW_ORDER_XLSX),
        "interview_order_exists": INTERVIEW_ORDER_XLSX.is_file(),
        "backend": BACKEND_BASE_URL,
        "frontend": f"http://{FRONTEND_HOST}:{FRONTEND_PORT}",
        "ai_provider": AI_PROVIDER,
        "ai_key_configured": bool(DEEPSEEK_API_KEY),
        "settings_json": str(CONFIG_DIR / "settings.json"),
        "version": APP_VERSION,
    }


if __name__ == "__main__":
    print(json.dumps(describe(), ensure_ascii=False, indent=2))
