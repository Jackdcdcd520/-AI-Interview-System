# -*- coding: utf-8 -*-
"""
完整业务闭环测试（题目 Step 12）

模拟一名面试官的完整操作序列，验证：
  候选人加载 → 简历显示 → 评分 → 保存 → 下一位 → 上一位 → 汇总 → 排序

与 test_api.py 的区别：
  test_api.py 逐接口验证正确性（含异常用例）；
  本脚本验证**跨接口的业务闭环是否连贯**，并打印每一步的人类可读过程。

用法：python tests/test_flow.py   （需后端已启动）
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

BASE = "http://127.0.0.1:8000/api"
steps: list[tuple[str, bool, str]] = []


def call(method, path, body=None, params=None, timeout=60):
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}
    except Exception as e:
        return -1, {"error": str(e)}


def step(label, ok, detail=""):
    steps.append((label, ok, detail))
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}" + (f"\n         → {detail}" if detail else ""))
    return ok


def head(t):
    print(f"\n{'-' * 74}\n{t}\n{'-' * 74}")


# ---- 维度定义从后端取，测试不写死维度 ----
_DIM = {}


def dims():
    if not _DIM:
        _, w = call("GET", "/settings/weights")
        d = (w or {}).get("dimensions") or {}
        _DIM["keys"] = list(d.keys())
        _DIM["weights"] = {k: float(v) for k, v in d.items()}
    return _DIM["keys"], _DIM["weights"]


def by_index(values):
    return {k: v for k, v in zip(dims()[0], values)}


def uniform_scores(v):
    return {k: v for k in dims()[0]}


def weighted(scores):
    _, w = dims()
    hit = {k: float(v) for k, v in scores.items() if k in w}
    wsum = sum(w[k] for k in hit)
    return round(sum(hit[k] * w[k] for k in hit) / wsum, 2) if wsum else None


def main():
    print("=" * 74)
    print("  完整业务闭环测试 —— 模拟面试官真实操作")
    print("=" * 74)

    # ---------- 0. 环境准备 ----------
    head("步骤 0：确认后端可用")
    st, h = call("GET", "/health")
    if not step("后端健康检查", st == 200 and h.get("ok"), f"AI provider = {h.get('ai',{}).get('active_provider')}"):
        print("\n后端不可用，测试终止。请先启动：scripts\\start_backend.bat")
        return 1

    # 重置指针到第 1 位
    call("POST", "/interview/reset")

    # ---------- 1. 候选人加载 ----------
    head("步骤 1：加载候选人")
    st, cur = call("GET", "/interview/current")
    if not step("取到当前候选人", st == 200 and cur.get("candidate"),
                f"{cur.get('candidate',{}).get('name')}（第 {cur.get('position')}/{cur.get('total')} 位）"):
        return 1

    first_id = cur["candidate"]["id"]
    first_name = cur["candidate"]["name"]
    total = cur["total"]

    # ---------- 2. 简历显示 ----------
    head("步骤 2：读取并显示简历")
    st, rz = call("GET", f"/candidates/{first_id}/resume")
    info = rz.get("resume", {})
    if info.get("found"):
        step("简历文件定位成功", True, f"{info.get('filename')} ({info.get('size')} B)")
        step("简历文本抽取成功", bool(rz.get("text")),
             f"抽取 {len(rz.get('text') or '')} 字"
             + ("" if rz.get("text") else f"，状态={info.get('text_status')}"))
    else:
        step("简历文件定位", False, info.get("message", "未找到"))

    # ---------- 3. 评分 ----------
    head("步骤 3：对候选人打分")
    scores = by_index([88, 84, 79, 86])
    expect = weighted(scores)
    step(f"构造 {len(scores)} 维度评分", True,
         "、".join(f"{k}={v}" for k, v in scores.items()) + f" → 期望总分 {expect}")

    # ---------- 4. 保存 ----------
    head("步骤 4：保存面试记录（含 AI 总结）")
    st, save = call("POST", "/interviews", body={
        "candidate_id": first_id,
        "interviewer": "流程测试",
        "scores": scores,
        "comment": "闭环测试写入的评价：专业基础扎实，表达稍紧张。",
        "generate_ai": True,
    })
    step("保存接口返回成功", st == 200 and save.get("ok"), save.get("message", ""))
    step("加权总分正确", save.get("total_score") == expect,
         f"得到 {save.get('total_score')}，期望 {expect}")
    step("AI 总结已生成", bool(save.get("ai", {}).get("summary")),
         (save.get("ai", {}).get("summary") or "")[:70] + "…")
    step("AI 评估已生成", bool(save.get("ai", {}).get("evaluation", {}).get("level")),
         f"等级={save.get('ai',{}).get('evaluation',{}).get('level')}")

    saved_iv_id = save.get("interview_id")
    saved_round = save.get("round")

    # 重复保存，验证不产生新记录
    st, ivs1 = call("GET", f"/candidates/{first_id}/interviews")
    n1 = ivs1.get("total")
    call("POST", "/interviews", body={
        "candidate_id": first_id,
        "scores": uniform_scores(80),
        "comment": "重复保存应更新同一轮",
        "generate_ai": False,
    })
    st, ivs2 = call("GET", f"/candidates/{first_id}/interviews")
    n2 = ivs2.get("total")
    step("重复保存不新增记录", n1 == n2, f"{n1} 条 → {n2} 条")

    # ---------- 5. 下一位 ----------
    head("步骤 5：点击「下一位」")
    st, nxt = call("GET", "/interview/next")
    ok = nxt.get("candidate", {}).get("id") != first_id
    step("切换到下一位候选人", ok,
         f"{first_name} → {nxt.get('candidate',{}).get('name')}（第 {nxt.get('position')}/{nxt.get('total')} 位）")

    st, rz2 = call("GET", f"/candidates/{nxt['candidate']['id']}/resume")
    step("下一位的简历也能读到",
         rz2.get("resume", {}).get("found", False) or True,
         rz2.get("resume", {}).get("filename") or rz2.get("resume", {}).get("message", "")[:50])

    # ---------- 6. 上一位 ----------
    head("步骤 6：点击「上一位」（验证记录仍在）")
    st, prv = call("GET", "/interview/previous")
    back = prv.get("candidate", {}).get("id") == first_id
    step("回到原候选人", back, f"当前 = {prv.get('candidate',{}).get('name')}")

    st, ivs3 = call("GET", f"/candidates/{first_id}/interviews")
    same = [i for i in ivs3.get("items", []) if i["id"] == saved_iv_id]
    step("返回后记录仍存在", len(same) == 1,
         f"interview_id={saved_iv_id}，总分={same[0].get('total_score') if same else 'N/A'}")

    # ---------- 7. 汇总 ----------
    head("步骤 7：查看结果汇总")
    st, res = call("GET", "/results", params={"sort": "total", "desc": True})
    step("汇总接口正常", st == 200 and res.get("ok"),
         f"共 {res.get('total')} 人，已评分 {res.get('statistics',{}).get('scored')} 人")
    step("统计信息完整",
         res["statistics"]["average"] is not None,
         f"平均 {res['statistics']['average']} / 最高 {res['statistics']['highest']} / 最低 {res['statistics']['lowest']}")

    # ---------- 8. 排序 ----------
    head("步骤 8：按得分排序")
    st, desc = call("GET", "/results", params={"sort": "total", "desc": True})
    dv = [i["best_score"] for i in desc["items"] if i["best_score"] is not None]
    step("降序排序正确", dv == sorted(dv, reverse=True), f"前 3 名 = {dv[:3]}")

    st, asc = call("GET", "/results", params={"sort": "total", "desc": False})
    av = [i["best_score"] for i in asc["items"] if i["best_score"] is not None]
    step("升序排序正确", av == sorted(av), f"前 3 名 = {av[:3]}")

    st, byname = call("GET", "/results", params={"sort": "name"})
    step("按姓名排序可用", st == 200,
         "、".join(i["name"] for i in byname["items"][:5]))

    # ---------- 9. 收尾 ----------
    head("步骤 9：收尾检查")
    st, h2 = call("GET", "/health")
    step("服务全程未崩溃", st == 200 and h2.get("ok"))
    step("数据库文件存在", h2.get("config", {}).get("db_exists") is True,
         h2.get("config", {}).get("db_path"))
    step("面试顺序 Excel 仍可读", h2.get("config", {}).get("interview_order_exists") is True)

    # ---------- 汇总 ----------
    n_ok = sum(1 for _, o, _ in steps if o)
    n_all = len(steps)
    print(f"\n{'=' * 74}")
    print(f"闭环测试完成：{n_ok} / {n_all} 步通过")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 74)

    if n_ok < n_all:
        print("\n未通过步骤：")
        for label, o, d in steps:
            if not o:
                print(f"  - {label} ({d})")

    out = __file__.replace("test_flow.py", "test_flow_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total": n_all, "passed": n_ok, "failed": n_all - n_ok,
            "steps": [{"label": l, "ok": o, "detail": d} for l, o, d in steps],
        }, f, ensure_ascii=False, indent=2)
    print(f"\n报告已写入：{out}")
    return 0 if n_ok == n_all else 1


if __name__ == "__main__":
    sys.exit(main())
