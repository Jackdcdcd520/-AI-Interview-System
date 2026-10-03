# -*- coding: utf-8 -*-
"""
一键运行全部测试

用法：
    python tests/run_all.py

需要：
  - 后端已启动（127.0.0.1:8000）
  - 前端已启动（127.0.0.1:5173）—— 仅前端相关测试需要

  会依次运行：
  1. test_api.py           接口正确性（A~M 验收项）
  2. test_flow.py          完整业务闭环
  3. test_data_safety.py   数据安全复核（只读）
  4. test_import_sync.py   名单同步导入（离线临时库）
  5. test_frontend_light.py 前端轻量验证（HTTP + 结构）
  6. test_browser.py       浏览器渲染验证（需 playwright，缺失则跳过）
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
PY = sys.executable

BACKEND_URL = "http://127.0.0.1:8000"
FRONT_PORT = 5173


def child_env() -> dict:
    """
    子进程环境：强制绕过 HTTP 代理访问本机。
    （本机若设了 HTTP_PROXY，urllib 会把 127.0.0.1 也走代理 → 502，测试会假失败。）
    """
    env = dict(os.environ)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    return env


# --------------------------------------------------------------- 环境自检
def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def backend_ready(timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/api/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def start_backend():
    """
    后端没起时自动拉起一个，测试结束后由调用方关闭。
    这样 `python tests/run_all.py` 一条命令就能跑完整套，
    不必先手动开服务（也避免服务被会话回收导致测试中途 500）。
    """
    env = child_env()
    (ROOT / "logs").mkdir(parents=True, exist_ok=True)
    log = (ROOT / "logs" / "test_backend.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [PY, "-m", "uvicorn", "backend.app.main:app",
         "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(ROOT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    for _ in range(60):          # 最多等 30 秒
        if backend_ready():
            break
        time.sleep(0.5)
    return proc


def run(name: str, script: str, required: bool = True) -> dict:
    print("\n" + "=" * 76)
    print(f"  ▶ {name}")
    print("=" * 76)
    p = TESTS / script
    if not p.is_file():
        print(f"  跳过：{script} 不存在")
        return {"name": name, "status": "MISSING", "returncode": None, "seconds": 0}

    t0 = time.time()
    proc = subprocess.run(
        [PY, str(p)],
        cwd=str(ROOT),
        env=child_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    dt = round(time.time() - t0, 1)

    # 打印输出（便于排查）
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr and proc.returncode not in (0, 1, 2):
        print("--- stderr ---")
        print(proc.stderr.rstrip()[-2000:])

    status = {0: "PASS", 1: "FAIL", 2: "SKIP"}.get(proc.returncode, f"ERR({proc.returncode})")
    return {"name": name, "status": status, "returncode": proc.returncode, "seconds": dt}


def main() -> int:
    print("#" * 76)
    print("#  学生面试管理与智能评估系统 V1 —— 全量测试")
    print("#" * 76)

    plan = [
        ("接口正确性测试（A~M）", "test_api.py", True),
        ("完整业务闭环测试", "test_flow.py", True),
        ("数据安全复核（只读）", "test_data_safety.py", True),
        ("名单同步导入测试（离线临时库）", "test_import_sync.py", True),
        ("联评综合评分测试（离线临时库）", "test_joint.py", True),
        ("评分权重与多维排序（离线临时库）", "test_weights.py", True),
        ("前端轻量验证", "test_frontend_light.py", False),
        ("浏览器渲染验证", "test_browser.py", False),
    ]

    # 可选：只跑指定套件，例如
    #   python tests/run_all.py test_browser        （只跑浏览器验证）
    #   python tests/run_all.py api browser          （跑多个，按脚本名关键字匹配）
    only = sys.argv[1:]
    if only:
        picked = [p for p in plan if any(k in p[1] for k in only)]
        if not picked:
            print(f"  未匹配到套件：{only}；可选：{[p[1] for p in plan]}")
            return 2
        print(f"\n  仅运行：{[p[1] for p in picked]}")
        plan = picked

    # ---- 服务自检：后端没起就自动拉起（前端另需手动/脚本启动） ----
    backend_proc = None
    try:
        if backend_ready():
            print("\n  后端已在运行，直接复用（127.0.0.1:8000）")
        else:
            print("\n  后端未运行 → 自动启动一个临时实例（测试结束后自动关闭）")
            backend_proc = start_backend()
            if backend_ready():
                print("  后端已就绪 ✅")
            else:
                print("  ⚠ 后端启动超时，依赖后端的用例会失败；见 logs/test_backend.log")

        if not port_open("127.0.0.1", FRONT_PORT):
            print(f"  ⚠ 前端 {FRONT_PORT} 未运行："
                  "前端轻量验证与浏览器验证会失败。"
                  "可先双击 scripts\\start_all_lan.bat 再重跑。")
        else:
            print(f"  前端已在运行（127.0.0.1:{FRONT_PORT}）")

        out = []
        for name, script, req in plan:
            out.append(run(name, script, req))
    finally:
        if backend_proc is not None:
            print("\n  关闭本次自动启动的临时后端…")
            try:
                backend_proc.terminate()
                backend_proc.wait(timeout=10)
            except Exception:
                pass

    print("\n" + "#" * 76)
    print("#  汇总")
    print("#" * 76)
    print(f"  {'测试':<28} {'结果':<10} {'耗时':>8}")
    print("  " + "-" * 50)
    for r in out:
        print(f"  {r['name']:<28} {r['status']:<10} {r['seconds']:>7}s")

    n_pass = sum(1 for r in out if r["status"] == "PASS")
    n_fail = sum(1 for r in out if r["status"] == "FAIL")
    n_skip = sum(1 for r in out if r["status"] in ("SKIP", "MISSING"))

    print("\n  " + f"通过 {n_pass} / 失败 {n_fail} / 跳过 {n_skip}")
    print("  " + ("全部通过 ✅" if n_fail == 0 else f"有 {n_fail} 项失败 ❌"))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
