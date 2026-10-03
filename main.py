# -*- coding: utf-8 -*-
"""
学生面试管理与智能评估系统 V1 —— 后端主入口（FastAPI）

启动：
    cd <项目根目录>
    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

或直接：
    python backend/app/main.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

# --- 让 `import settings`（config/ 下）与 `backend.app.*` 都能被解析 ---
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "config"))

import settings  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from backend.app import db  # noqa: E402
from backend.app.api import ai_routes, candidates, interview, results, weights  # noqa: E402

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=(
        "本地运行的学生面试管理与智能评估系统。"
        "AI 能力通过独立 Provider 模块提供（默认 mock，可切换 deepseek）。"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------- 全局异常兜底
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    题目验收标准 M：异常不能导致服务崩溃。
    任何未捕获异常都转成结构化 500，并把堆栈写到日志文件。
    """
    tb = traceback.format_exc()
    try:
        settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with (settings.LOGS_DIR / "backend_error.log").open("a", encoding="utf-8") as f:
            f.write(f"\n=== {request.method} {request.url.path} ===\n{tb}\n")
    except Exception:
        pass
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
            "path": request.url.path,
            "hint": "服务未崩溃，可继续操作；详情见 logs/backend_error.log",
        },
    )


# --------------------------------------------------------------- 路由注册
app.include_router(candidates.router, prefix=settings.API_PREFIX, tags=["candidates"])
app.include_router(interview.router, prefix=settings.API_PREFIX, tags=["interview"])
app.include_router(results.router, prefix=settings.API_PREFIX, tags=["results"])
app.include_router(weights.router, prefix=settings.API_PREFIX, tags=["settings"])
app.include_router(ai_routes.router, prefix=settings.API_PREFIX, tags=["ai"])


@app.get(f"{settings.API_PREFIX}/health", tags=["system"])
def health():
    """健康检查 + 配置快照（前端首页用它展示环境信息）。"""
    from backend.app.ai import available_providers, get_provider

    prov = get_provider()
    try:
        n_cand = db.count_candidates()
    except Exception:
        n_cand = -1

    return {
        "ok": True,
        "app": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "config": settings.describe(),
        "ai": {
            "active_provider": prov.name,
            "providers": available_providers(),
            "note": "未配置 API Key 时自动使用 mock，系统功能完整可用。",
        },
        "data": {
            "candidates": n_cand,
            "db_path": str(settings.DB_PATH),
            "resume_dir": str(settings.RESUME_DIR),
        },
    }


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    print("=" * 68)
    print(f"  {settings.APP_TITLE} v{settings.APP_VERSION}")
    print("=" * 68)
    for k, v in settings.describe().items():
        print(f"  {k:<24} = {v}")
    print("=" * 68)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=False,
        app_dir=str(_PROJECT_ROOT),
    )
