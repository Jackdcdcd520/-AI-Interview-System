# -*- coding: utf-8 -*-
"""
轻量前端验证（不需要浏览器引擎）

在等待/缺少 Playwright 浏览器时使用，验证：
  1. Vite 能提供 index.html
  2. 所有 React 模块能被 Vite 成功编译（无 resolve / transform 错误）
  3. 前端通过 Vite 代理能拿到后端数据（真实 API 响应内容校验）
  4. 源码层面的关键结构检查（5 个页面存在、路由注册、API 出口唯一）

这不能替代真实浏览器渲染，但能确认"代码没有语法/依赖错误 + 前后端连通"。
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = "http://127.0.0.1:5173"
results: list[tuple[str, bool, str]] = []


def step(label, ok, detail=""):
    results.append((label, ok, detail))
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}" + (f"\n         → {detail}" if detail else ""))
    return ok


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "verify/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return -1, str(e)


def head(t):
    print(f"\n{'-' * 74}\n{t}\n{'-' * 74}")


def main() -> int:
    print("=" * 74)
    print("  前端轻量验证（HTTP + 源码结构）")
    print("=" * 74)

    # ---- 1. index.html ----
    head("1) Vite 提供 index.html")
    st, html = fetch(f"{FRONT}/")
    step("GET / 返回 200", st == 200, f"status={st}")
    step("包含 React 挂载点 #root", 'id="root"' in html)
    step("包含入口脚本 main.jsx", "/src/main.jsx" in html)

    # ---- 2. 模块编译 ----
    head("2) React 模块经 Vite 编译")
    modules = [
        "/src/main.jsx", "/src/App.jsx", "/src/api.js", "/src/styles.css",
        "/src/pages/HomePage.jsx", "/src/pages/InterviewPage.jsx",
        "/src/pages/CandidatesPage.jsx", "/src/pages/ResultsPage.jsx",
        "/src/pages/CandidateDetailPage.jsx",
    ]
    all_ok = True
    errs = []
    for m in modules:
        st, body = fetch(f"{FRONT}{m}")
        bad = ("Could not resolve" in body or "Transform failed" in body
               or "Internal server error" in body or "Failed to resolve" in body)
        if st != 200 or bad:
            all_ok = False
            errs.append(f"{m}(status={st}{', resolve-error' if bad else ''})")
    step(f"全部 {len(modules)} 个模块编译成功", all_ok,
         "; ".join(errs) if errs else "无 resolve / transform 错误")

    # ---- 3. 真实 API 数据经代理 ----
    head("3) 前端代理 → 后端真实数据")
    st, body = fetch(f"{FRONT}/api/health")
    ok = st == 200
    try:
        h = json.loads(body)
        ok = ok and h.get("ok") and h.get("ai", {}).get("active_provider")
    except Exception:
        h = {}
    step("GET /api/health 经代理成功", ok,
         f"AI={h.get('ai',{}).get('active_provider')}, 候选人={h.get('data',{}).get('candidates')}")

    st, body = fetch(f"{FRONT}/api/candidates")
    try:
        c = json.loads(body)
        items = c.get("items", [])
    except Exception:
        items = []
    step("候选人列表返回数据", st == 200 and len(items) >= 5,
         f"{len(items)} 人：" + "、".join(i["name"] for i in items[:6]))
    step("候选人含面试顺序字段", all(i.get("order_index") is not None for i in items),
         "order_index：" + ", ".join(str(i.get("order_index")) for i in items))

    st, body = fetch(f"{FRONT}/api/interview/current")
    try:
        cur = json.loads(body)
    except Exception:
        cur = {}
    step("当前面试候选人可获取",
         bool(cur.get("candidate")),
         f"{cur.get('candidate',{}).get('name')} 第 {cur.get('position')}/{cur.get('total')} 位")

    st, body = fetch(f"{FRONT}/api/results?sort=total&desc=True")
    try:
        res = json.loads(body)
        vals = [i["best_score"] for i in res.get("items", []) if i.get("best_score") is not None]
    except Exception:
        vals = []
    step("结果汇总按得分降序", vals == sorted(vals, reverse=True),
         f"分数序列 {vals}")

    # 简历文本能经代理拿到（面试页左栏数据源）
    if cur.get("candidate"):
        cid = cur["candidate"]["id"]
        st, body = fetch(f"{FRONT}/api/candidates/{cid}/resume")
        try:
            rz = json.loads(body)
        except Exception:
            rz = {}
        step("面试页简历数据可获取",
             rz.get("resume", {}).get("found") is True,
             f"{rz.get('resume',{}).get('filename')} / 抽取 {len(rz.get('text') or '')} 字")

    # ---- 4. 源码结构 ----
    head("4) 前端源码结构")
    src = ROOT / "frontend" / "src"
    pages = ["HomePage.jsx", "InterviewPage.jsx", "CandidatesPage.jsx",
             "ResultsPage.jsx", "CandidateDetailPage.jsx"]
    missing = [p for p in pages if not (src / "pages" / p).is_file()]
    step("5 个页面文件齐全", not missing, f"缺失：{missing}" if missing else "、".join(pages))

    app = (src / "App.jsx").read_text(encoding="utf-8")
    routes = re.findall(r'path="([^"]+)"', app)
    step("路由已注册（含面试/候选人/结果）",
         any("/interview" in r for r in routes)
         and any("/candidates" in r for r in routes)
         and any("/results" in r for r in routes),
         "路由：" + ", ".join(routes))

    api = (src / "api.js").read_text(encoding="utf-8")
    urls = re.findall(r"request\(\s*[`'\"]([^`'\"]+)", api)
    step("API 全部使用相对路径（便于改后端地址）",
         all(u.startswith("/") for u in urls),
         f"{len(urls)} 个端点，均以 / 开头")

    ip = (src / "pages" / "InterviewPage.jsx").read_text(encoding="utf-8")
    step("面试页维度改为后端下发（不再写死单一维度）",
         "normalizeDims" in ip and "d.dimensions" in ip,
         "normalizeDims + data.dimensions")
    step("面试页含「综合评分」放大区块（highlight 维度）",
         "star-dim-row--hl" in ip and "rate-hl" in ip,
         "star-dim-row--hl / rate-hl")

    # 兜底维度定义应与后端当前维度一致（后端不可用时才会用到它）
    _fb = re.search(r"const FALLBACK_DIMENSIONS = \[(.*?)\n\]", ip, re.S)
    _fb_txt = _fb.group(1) if _fb else ""
    _fb_n = len(re.findall(r"key:\s*'", _fb_txt))
    _be_n = None
    try:
        # 直连后端并强制绕过本机代理（否则 127.0.0.1 可能被 HTTP_PROXY 截走）
        _op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with _op.open("http://127.0.0.1:8000/api/settings/weights", timeout=10) as _r:
            _be_n = len((json.loads(_r.read().decode("utf-8")).get("dimensions") or {}))
    except Exception:
        _be_n = None
    step("前端兜底维度数与后端 config 一致",
         _be_n is not None and _fb_n == _be_n,
         f"前端兜底 {_fb_n} 个 / 后端 {_be_n} 个")
    step("面试页含下一位/上一位/保存按钮",
         all(k in ip for k in ["下一位", "上一位", "保存"]))

    # ---- 汇总 ----
    n_ok = sum(1 for _, o, _ in results if o)
    n_all = len(results)
    print(f"\n{'=' * 74}")
    print(f"轻量前端验证：{n_ok} / {n_all} 通过")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 74)
    if n_ok < n_all:
        print("\n未通过：")
        for l, o, d in results:
            if not o:
                print(f"  - {l} ({d})")

    out = Path(__file__).resolve().parent / "test_frontend_light_report.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total": n_all, "passed": n_ok, "failed": n_all - n_ok,
            "results": [{"label": l, "ok": o, "detail": d} for l, o, d in results],
        }, f, ensure_ascii=False, indent=2)
    print(f"报告已写入：{out}")
    return 0 if n_ok == n_all else 1


if __name__ == "__main__":
    sys.exit(main())
