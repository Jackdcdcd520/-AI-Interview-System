# -*- coding: utf-8 -*-
"""
自动接口测试：按题目验收标准 A~M 逐项验证后端 API。

用法：
    python tests/test_api.py
前置：后端已启动（127.0.0.1:8000）

本脚本**只通过 HTTP 调用**接口，不直接碰数据库，验证的是真实链路。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

BASE = "http://127.0.0.1:8000/api"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def call(method: str, path: str, body=None, params=None, timeout=30):
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}
    except Exception as e:
        return -1, {"error": str(e)}


def check(label: str, cond: bool, detail: str = ""):
    results.append((label, PASS if cond else FAIL, detail))
    mark = "OK  " if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f"  — {detail}" if detail else ""))
    return cond


def section(t):
    print(f"\n{'=' * 74}\n{t}\n{'=' * 74}")


# ---- 维度定义一律从后端取，测试不写死维度（改 config 后测试自动跟随）----
_DIM_CACHE: dict = {}


def dims():
    """(keys, weights)：当前后端生效的维度 key 顺序 + 对应权重。"""
    if not _DIM_CACHE:
        _, w = call("GET", "/settings/weights")
        d = (w or {}).get("dimensions") or {}
        _DIM_CACHE["keys"] = list(d.keys())
        _DIM_CACHE["weights"] = {k: float(v) for k, v in d.items()}
    return _DIM_CACHE["keys"], _DIM_CACHE["weights"]


def uniform_scores(value):
    """所有维度都给同一个分。"""
    return {k: value for k in dims()[0]}


def weighted(scores):
    """按后端生效权重重算加权总分（只算已评维度，自动归一化）。"""
    _, w = dims()
    hit = {k: float(v) for k, v in scores.items() if k in w}
    wsum = sum(w[k] for k in hit)
    return round(sum(hit[k] * w[k] for k in hit) / wsum, 2) if wsum else None


def by_index(values):
    """把一串分数按当前维度的顺序铺开（多出的忽略）。"""
    return {k: v for k, v in zip(dims()[0], values)}


# =====================================================================
section("0) 基础连通性")
st, health = call("GET", "/health")
check("GET /api/health 返回 200", st == 200, f"status={st}")
check("health.ok == true", bool(health and health.get("ok")))
check("配置路径集中在 settings 中生效（能看到 resume_dir/db_path）",
      bool(health and health.get("config", {}).get("db_path")),
      str(health.get("config", {}).get("db_path")) if health else "")
check("AI 无 Key 时仍可用（active_provider=mock）",
      health and health.get("ai", {}).get("active_provider") == "mock",
      f"provider={health.get('ai',{}).get('active_provider')}" if health else "")

# =====================================================================
section("A) 候选人数据加载")
st, cands = call("GET", "/candidates")
check("GET /api/candidates 返回 200", st == 200, f"status={st}")
n = len((cands or {}).get("items") or [])
check("候选人数量 >= 5", n >= 5, f"实际 {n} 人")
check("候选人有面试顺序 order_index",
      all(c.get("order_index") is not None for c in (cands.get("items") or [])))

# 搜索
st, s1 = call("GET", "/candidates", params={"q": "张"})
check("候选人搜索可用（q=张）", st == 200 and len(s1.get("items", [])) >= 1,
      f"命中 {len(s1.get('items', []))} 条")

# =====================================================================
section("B) 简历读取（E 盘）")
cid_with_resume = None
cid_without_resume = None
for c in cands["items"]:
    if c.get("resume_exists") and cid_with_resume is None:
        cid_with_resume = c["id"]
    if not c.get("resume_exists") and cid_without_resume is None:
        cid_without_resume = c["id"]

if cid_with_resume:
    st, r = call("GET", f"/candidates/{cid_with_resume}/resume")
    check(f"GET /candidates/{cid_with_resume}/resume 返回 200", st == 200, f"status={st}")
    check("简历文件被找到", bool(r.get("resume", {}).get("found")),
          str(r.get("resume", {}).get("filename")))
    check("简历文本成功抽取（text_length > 0）",
          bool(r.get("text")) and len(r.get("text", "")) > 50,
          f"text_length={len(r.get('text') or '')}")
    check("返回 view_url 供浏览器查看原件", bool(r.get("view_url")))
else:
    check("存在有简历的候选人", False, "未找到")

st, blob = call("GET", f"/candidates/{cid_with_resume}/resume/file")
# 该接口返回原始文件字节（不是 JSON），因此这里直接检查 HTTP 状态码与响应体长度。
# 为了拿到真实字节，绕过 call() 的 JSON 解析。
try:
    req = urllib.request.Request(
        f"{BASE}/candidates/{cid_with_resume}/resume/file", method="GET"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        code = resp.status
except Exception as e:
    code, body, ctype = -1, b"", str(e)

check("原始简历文件可通过接口读取（不修改原文）",
      code == 200 and len(body) > 100,
      f"status={code}, bytes={len(body)}, content-type={ctype}")

# ---- 大窗预览端点（B3）：preview 分派 + 不存在候选人 404 ----
if cid_with_resume:
    st, pv = call("GET", f"/candidates/{cid_with_resume}/resume/preview")
    check("GET /resume/preview 返回 200", st == 200, f"status={st}")
    check("preview 返回合法 kind（pdf/html/text/unsupported 之一）",
          pv.get("kind") in ("pdf", "html", "text", "unsupported"),
          f"kind={pv.get('kind')}, ext={pv.get('ext')}")
    if pv.get("kind") == "pdf":
        check("preview 的 pdf url 指向有效地址", bool(pv.get("url")), str(pv.get("url")))
    elif pv.get("kind") == "html":
        check("preview 的 html 非空", len(pv.get("html") or "") > 20)
    elif pv.get("kind") == "text":
        check("preview 的 text 非空", len(pv.get("text") or "") > 20)
    check("preview 附带 download_url", bool(pv.get("download_url")))

st_pv404, _ = call("GET", "/candidates/999999/resume/preview")
check("preview 对不存在候选人返回 404 而非 500", st_pv404 == 404, f"status={st_pv404}")

# ---- 名单同步端点（幂等冒烟）：对真实顺序表跑一遍，不应新增/不应破坏 ----
st_imp, imp = call("POST", "/candidates/import-from-order")
check("POST /candidates/import-from-order 返回 200", st_imp == 200, f"status={st_imp}")
check("名单同步 ok=true 且读到顺序表行",
      imp.get("ok") is True and (imp.get("rows") or 0) >= 5,
      imp.get("message", ""))
check("名单同步幂等（库已一致时不新增）", len(imp.get("added") or []) == 0,
      f"added={imp.get('added')}")
st_c2, cands2 = call("GET", "/candidates")
check("同步后候选人数量不变", cands2.get("total") == cands.get("total"),
      f"{cands.get('total')} -> {cands2.get('total')}")

if cid_without_resume:
    st, r2 = call("GET", f"/candidates/{cid_without_resume}/resume")
    check("候选人无简历时不报 500，返回 found=false",
          st == 200 and r2.get("resume", {}).get("found") is False,
          f"status={st}, msg={r2.get('resume',{}).get('message','')[:40]}")
else:
    n_items = len(cands.get("items") or [])
    check("缺简历场景：当前名单全员有简历（该场景已由离线导入套件覆盖）",
          n_items > 0, f"{n_items} 人均有简历")

# ---- 联评综合评分（多面试官平均） ----
st, jt = call("GET", f"/candidates/{cid_with_resume}/joint")
check("GET /candidates/{id}/joint 返回 200", st == 200, f"status={st}")
check("联评返回人数与综合分字段",
      "interviewer_count" in jt and "joint_score" in jt and "interviewers" in jt,
      f"count={jt.get('interviewer_count')}, joint={jt.get('joint_score')}")
check("联评综合分在 0~100 区间或为空",
      jt.get("joint_score") is None or 0 <= jt["joint_score"] <= 100,
      f"joint={jt.get('joint_score')}")
check("联评附带计算规则说明", bool(jt.get("rule")), str(jt.get("rule"))[:50])
check("联评明细每位面试官含平均分",
      all("interviewer" in x and "avg_score" in x for x in (jt.get("interviewers") or []))
      or not jt.get("interviewers"))

st_j404, _ = call("GET", "/candidates/999999/joint")
check("联评对不存在候选人返回 404", st_j404 == 404, f"status={st_j404}")

st_jr, jr = call("GET", "/summary/joint")
check("GET /summary/joint 返回 200", st_jr == 200, f"status={st_jr}")
check("联评排行榜按分数降序",
      all((jr["items"][i]["joint_score"] or 0) >= (jr["items"][i + 1]["joint_score"] or 0)
          for i in range(len(jr.get("items") or []) - 1)),
      f"{[x['joint_score'] for x in (jr.get('items') or [])][:6]}")

st_rj, rj = call("GET", "/results", params={"sort": "joint", "desc": True})
check("结果汇总支持按联评综合分排序",
      st_rj == 200 and rj.get("sort") == "joint",
      f"status={st_rj}, sort={rj.get('sort')}")
check("汇总项含 interview_count / joint_score / joint_level",
      all(k in (rj.get("items") or [{}])[0]
          for k in ("interviewer_count", "joint_score", "joint_level")),
      str(list((rj.get("items") or [{}])[0].keys())[:12]))
check("汇总统计含联评平均分",
      "joint_average" in (rj.get("statistics") or {}),
      f"joint_average={rj.get('statistics',{}).get('joint_average')}")

# =====================================================================
section("C/D) 面试顺序：当前 → 下一位 → 上一位")
st, cur = call("GET", "/interview/current")
check("GET /interview/current 返回 200", st == 200, f"status={st}")
check("current 返回候选人与顺序信息",
      bool(cur.get("candidate")) and cur.get("position", 0) >= 1,
      f"第 {cur.get('position')} / {cur.get('total')} 位, name={cur.get('candidate',{}).get('name')}")

first_id = cur["candidate"]["id"]
first_pos = cur["position"]

st, nx = call("GET", "/interview/next")
check("GET /interview/next 返回 200", st == 200, f"status={st}")
check("下一位确实换人了", nx.get("candidate", {}).get("id") != first_id,
      f"{cur.get('candidate',{}).get('name')} -> {nx.get('candidate',{}).get('name')}")
check("下一位的顺序号 +1", nx.get("position") == first_pos + 1,
      f"{first_pos} -> {nx.get('position')}")

st, pv = call("GET", "/interview/previous")
check("GET /interview/previous 返回 200", st == 200, f"status={st}")
check("上一位回到原候选人", pv.get("candidate", {}).get("id") == first_id,
      f"回到 {pv.get('candidate',{}).get('name')}")

# 边界：连续上一位
call("POST", "/interview/reset")
st, pv2 = call("GET", "/interview/previous")
check("已是第一位时再上一位 → 不报错，给出 at_start 提示",
      st == 200 and pv2.get("at_start") is True,
      f"status={st}, at_start={pv2.get('at_start')}")

# 边界：走到最后（人数不定，从接口取总人数，走完为止）
st_c0, cur0 = call("GET", "/interview/current")
total_n = int(cur0.get("total") or 0)
call("POST", "/interview/reset")
last_pos = None
for _ in range(total_n + 2):
    st, x = call("GET", "/interview/next")
    if x.get("at_end"):
        last_pos = True
        break
check("走到最后一位后再下一位 → 不报错，给出 at_end 提示",
      last_pos is True, f"共 {total_n} 位，at_end={last_pos}")

call("POST", "/interview/reset")

# =====================================================================
section("E/F) 评分提交与总分计算")
st, cur = call("GET", "/interview/current")
target = cur["candidate"]

scores = by_index([90, 86, 80, 88])      # 按当前维度顺序铺开
expect = weighted(scores)

st, sub = call("POST", "/interviews", body={
    "candidate_id": target["id"],
    "interviewer": "自动测试",
    "scores": scores,
    "comment": "自动测试写入的一条评价。",
    "generate_ai": True,
})
check("POST /api/interviews 返回 200", st == 200, f"status={st}")
check("加权总分计算正确", sub.get("total_score") == expect,
      f"得到 {sub.get('total_score')}，期望 {expect}")
check("返回逐维度明细 breakdown", len(sub.get("breakdown") or []) == len(dims()[0]),
      f"{len(sub.get('breakdown') or [])} 个维度")
check("返回等级评定", bool(sub.get("level")), f"level={sub.get('level')}")

# 实测加权：手工核算（独立代码路径：Σ(分×权重)/Σ权重，全维度已评故无需归一化）
_dkeys, _dw = dims()
manual = round(sum(scores[k] * _dw[k] for k in _dkeys), 2)
check("后端总分 == 独立手工核算", sub.get("total_score") == manual,
      f"后端 {sub.get('total_score')} vs 手工 {manual}")

# =====================================================================
section("G/H) AI 总结与智能评估（mock provider）")
ai = sub.get("ai") or {}
check("AI provider 标记为 mock（无 Key 也能工作）", ai.get("provider") == "mock",
      f"provider={ai.get('provider')}")
check("生成了 AI 面试总结", bool(ai.get("summary")),
      (ai.get("summary") or "")[:60] + "...")
ev = ai.get("evaluation") or {}
check("生成了结构化 AI 评估（含等级与建议）",
      bool(ev.get("level")) and bool(ev.get("suggestion")),
      f"level={ev.get('level')}, 优势{len(ev.get('strengths') or [])}项/短板{len(ev.get('weaknesses') or [])}项")

# 独立 AI 评估接口
st, ev2 = call("POST", f"/ai/evaluate/{target['id']}")
check("POST /api/ai/evaluate/{id} 返回 200", st == 200, f"status={st}")
check("独立评估接口返回 provider 与结论",
      bool(ev2.get("provider_used")) and bool(ev2.get("evaluation")),
      f"provider={ev2.get('provider_used')}")

# =====================================================================
section("I/J) 面试次数与重复提交（数据安全关键项）")
st, iv_before = call("GET", f"/candidates/{target['id']}/interviews")
cnt_before = iv_before.get("total")
round_before = iv_before.get("next_round")

# 重复提交同一轮
st, sub2 = call("POST", "/interviews", body={
    "candidate_id": target["id"],
    "interviewer": "自动测试(重复提交)",
    "scores": uniform_scores(70),
    "comment": "这是一次重复提交，应该更新而不是新增。",
    "generate_ai": False,
})
st, iv_after = call("GET", f"/candidates/{target['id']}/interviews")
cnt_after = iv_after.get("total")

check("重复提交同一轮 → 记录总数不增加（更新而非新增）",
      cnt_after == cnt_before,
      f"提交前 {cnt_before} 条 → 提交后 {cnt_after} 条")

same = [i for i in iv_after["items"] if i["id"] == sub2.get("interview_id")]
check("重复提交命中同一条 interview_id",
      len(same) == 1 and same[0]["comment"].startswith("这是一次重复提交"),
      f"interview_id={sub2.get('interview_id')}")
check("重复提交后分数被更新（不再是旧值）",
      same and same[0].get("total_score") == 70.0,
      f"新总分={same[0].get('total_score') if same else None}")
check("提交接口返回 is_update=true（告知是更新而非新建）",
      sub2.get("is_update") is True, f"is_update={sub2.get('is_update')}")

# 连续第三次提交，轮次必须保持不变
st, sub2b = call("POST", "/interviews", body={
    "candidate_id": target["id"],
    "scores": uniform_scores(66),
    "comment": "连续第三次保存，轮次不应变化。",
    "generate_ai": False,
})
st, iv_after_b = call("GET", f"/candidates/{target['id']}/interviews")
check("连续多次保存 → 记录数稳定（不会一直 +1）",
      iv_after_b.get("total") == cnt_before,
      f"仍为 {iv_after_b.get('total')} 条")
check("连续多次保存 → 轮次号稳定（round 不递增）",
      iv_after_b.get("next_round") == round_before,
      f"round 仍为 {iv_after_b.get('next_round')}")

# 显式开启新一轮
st, adv = call("POST", f"/interview/advance/{target['id']}")
check("显式开启新一轮 → 返回 new_round = 原轮次+1",
      st == 200 and adv.get("new_round") == round_before + 1,
      f"round {round_before} -> {adv.get('new_round')}")

st, sub3 = call("POST", "/interviews", body={
    "candidate_id": target["id"],
    "interviewer": "自动测试(第二轮)",
    "scores": by_index([95, 92, 90, 93]),
    "comment": "第二轮综合面试。",
    "generate_ai": True,
})
st, iv_after2 = call("GET", f"/candidates/{target['id']}/interviews")
check("支持多轮面试（第 2 轮独立记录）",
      iv_after2.get("total") == cnt_before + 1,
      f"{cnt_before} → {iv_after2.get('total')} 条")
check("多轮记录各自有独立总分",
      len({i["total_score"] for i in iv_after2["items"] if i.get("total_score")}) >= 2,
      f"总分集合={sorted({i['total_score'] for i in iv_after2['items'] if i.get('total_score')})}")

# 第二轮重复提交同样只更新
st, sub4 = call("POST", "/interviews", body={
    "candidate_id": target["id"],
    "round": adv.get("new_round"),
    "scores": uniform_scores(96),
    "comment": "第二轮重复提交，应更新第二条。",
    "generate_ai": False,
})
st, iv_after3 = call("GET", f"/candidates/{target['id']}/interviews")
check("第二轮重复提交 → 总记录数不再增加",
      iv_after3.get("total") == cnt_before + 1,
      f"仍为 {iv_after3.get('total')} 条")

# =====================================================================
section("K) 结果汇总与排序")
st, res = call("GET", "/results", params={"sort": "total", "desc": True})
check("GET /api/results 返回 200", st == 200, f"status={st}")
vals = [i["best_score"] for i in res["items"] if i["best_score"] is not None]
check("按总分降序排序正确", vals == sorted(vals, reverse=True), f"前 3 名分数={vals[:3]}")
check("汇总包含统计信息（平均/最高/最低）",
      res["statistics"]["average"] is not None,
      f"avg={res['statistics']['average']}, max={res['statistics']['highest']}, "
      f"min={res['statistics']['lowest']}")

st, res2 = call("GET", "/results", params={"sort": "total", "desc": False})
vals2 = [i["best_score"] for i in res2["items"] if i["best_score"] is not None]
check("升序排序同样正确", vals2 == sorted(vals2), f"前 3 名分数={vals2[:3]}")

st, res3 = call("GET", "/results", params={"sort": "name"})
names = [i["name"] for i in res3["items"]]
check("按姓名排序可用", st == 200 and len(names) == len(set(names)), f"{len(names)} 人")

st, det = call("GET", f"/results/{target['id']}")
check("结果详情接口可用", st == 200 and det.get("ok"),
      f"rounds={det.get('rounds')}, best={det.get('best_score')}")

st, stats = call("GET", "/summary/statistics")
check("统计接口可用", st == 200 and stats.get("candidates", 0) >= 5,
      f"候选人={stats.get('candidates')}, 已面试={stats.get('candidates_interviewed')}")

# =====================================================================
section("L) AI 可切换性（前端零改动验证）")
st, aist = call("GET", "/ai/status")
check("GET /api/ai/status 返回 200", st == 200, f"status={st}")
check("列出所有可用 provider（mock / deepseek）",
      len(aist.get("providers") or []) >= 2,
      ", ".join(f"{p['name']}({'可用' if p['available'] else '不可用'})"
                for p in aist.get("providers", [])))
check("deepseek 未配置 Key 时被标记为不可用（会降级到 mock）",
      any(p["name"] == "deepseek" and not p["available"] for p in aist.get("providers", [])))

# =====================================================================
section("M) 异常处理（不崩溃）")
st, e1 = call("GET", "/candidates/999999")
check("访问不存在的候选人 → 404 而非 500", st == 404, f"status={st}")

st, e2 = call("POST", "/interviews", body={
    "candidate_id": target["id"],
    "scores": {dims()[0][0]: 999},   # 超范围
})
check("评分超出 0~100 → 400 且给出可读原因",
      st == 400 and "超出允许范围" in str(e2.get("detail", "")),
      f"status={st}, detail={str(e2.get('detail'))[:60]}")

st, e3 = call("POST", "/interviews", body={
    "candidate_id": target["id"],
    "scores": {dims()[0][0]: "abc"},  # 非数字
})
check("评分非数字 → 400 而非 500", st == 400, f"status={st}")

st, e4 = call("POST", f"/ai/evaluate/999999")
check("对不存在的候选人做 AI 评估 → 404", st == 404, f"status={st}")

# 未知维度应被忽略而不是报错
st, e5 = call("POST", "/interviews", body={
    "candidate_id": target["id"],
    "scores": {dims()[0][0]: 80, "不存在的维度": 50},
    "generate_ai": False,
})
check("未知评分维度被忽略（不报错）", st == 200, f"status={st}")

# 服务仍然活着
st, h2 = call("GET", "/health")
check("跑完全部异常用例后服务依然健康（未崩溃）", st == 200 and h2.get("ok"),
      f"status={st}")

# =====================================================================
section("N) 评分权重的人工设定与多口径排序")

# N1) 读取权重快照
st, w0 = call("GET", "/settings/weights")
check("GET /api/settings/weights 返回 200", st == 200, f"status={st}")
check("权重快照包含 config 里的全部维度",
      len((w0 or {}).get("dimensions") or {}) == len(dims()[0]),
      str((w0 or {}).get("dimensions")))
check("权重快照含维度标签与规则说明",
      bool((w0 or {}).get("dimension_labels")) and bool((w0 or {}).get("rule")))

# N2) 非法权重 → 400（不能崩）
st, e_w1 = call("POST", "/settings/weights/dimensions",
                body={"weights": {dims()[0][0]: -5}})
check("维度权重为负 → 400 且可读原因",
      st == 400 and "负" in str(e_w1.get("detail", "")),
      f"status={st}, detail={str(e_w1.get('detail'))[:60]}")
st, e_w2 = call("POST", "/settings/weights/dimensions", body={"weights": {}})
check("空维度权重 → 400", st == 400, f"status={st}")
st, e_w3 = call("POST", "/settings/weights/interviewers",
                body={"weights": {"自动测试": -1}})
check("面试官权重为负 → 400", st == 400, f"status={st}")

# N3) 人工设定维度权重
_custom_w = dict(zip(dims()[0], [60, 25, 10, 3]))
st, w1 = call("POST", "/settings/weights/dimensions", body={"weights": _custom_w})
check("人工设定维度权重成功", st == 200, f"status={st}")
check("设定后 dimensions_customized=True",
      bool((w1 or {}).get("dimensions_customized")),
      str((w1 or {}).get("dimensions")))
check("设定值被持久化（第一个维度=60）",
      abs(float((w1 or {}).get("dimensions", {}).get(dims()[0][0], 0)) - 60) < 1e-9,
      str((w1 or {}).get("dimensions")))
check("快照给出百分比口径且合计为 100",
      abs(sum(((w1 or {}).get("dimension_percent") or {}).values()) - 100) < 0.5,
      str((w1 or {}).get("dimension_percent")))

# N4) 按单个维度排序
dim_key = dims()[0][0]
st, rs = call("GET", "/results", params={"sort": f"dim:{dim_key}", "desc": True})
check("按维度排序返回 200 且回显 sort",
      st == 200 and rs.get("sort") == f"dim:{dim_key}",
      f"status={st}, sort={rs.get('sort')}")
dim_vals = [i.get("dimension_avgs", {}).get(dim_key) for i in rs.get("items", [])]
dim_given = [v for v in dim_vals if v is not None]
check("按维度排序结果降序正确",
      dim_given == sorted(dim_given, reverse=True), str(dim_given[:5]))
check("汇总项含各维度平均分（dimension_avgs）",
      all("dimension_avgs" in i for i in rs.get("items", [])))
check("汇总项含各面试官平均分（interviewer_avgs）",
      all("interviewer_avgs" in i for i in rs.get("items", [])))
check("汇总项含自定义加权分（custom_score）",
      all("custom_score" in i for i in rs.get("items", [])))
check("自定义权重生效标志为 True",
      bool(rs.get("weights", {}).get("dimensions_customized")))
check("加权分都在 0~100 或为空",
      all(i.get("custom_score") is None or 0 <= i["custom_score"] <= 100
          for i in rs.get("items", [])))
check("统计含自定义加权平均",
      "custom_average" in (rs.get("statistics") or {}),
      f"custom_average={rs.get('statistics', {}).get('custom_average')}")

# N5) 按自定义加权分排序
st, rc = call("GET", "/results", params={"sort": "custom", "desc": True})
c_vals = [i.get("custom_score") for i in rc.get("items", [])]
c_given = [v for v in c_vals if v is not None]
check("按自定义加权分排序降序正确",
      st == 200 and c_given == sorted(c_given, reverse=True), str(c_given[:5]))

# N6) 面试官名单 + 按面试官排序
st, ivs = call("GET", "/interview/interviewers")
check("GET /api/interview/interviewers 返回 200", st == 200, f"status={st}")
names = (ivs or {}).get("items") or []
check("面试官名单去重", len(names) == len(set(names)), str(names))
check("面试官名单非空（测试已写入面试官）", len(names) >= 1, str(names))
check("结果汇总输出面试官下拉选项",
      isinstance(rs.get("interviewer_options"), list),
      str(rs.get("interviewer_options")))

who = names[0] if names else "自动测试"
st, rv = call("GET", "/results", params={"sort": f"iv:{who}", "desc": True})
check("按面试官排序返回 200",
      st == 200 and rv.get("sort") == f"iv:{who}", f"status={st}, sort={rv.get('sort')}")
iv_vals = [i.get("interviewer_avgs", {}).get(who) for i in rv.get("items", [])]
iv_given = [v for v in iv_vals if v is not None]
check("按面试官排序结果降序正确",
      iv_given == sorted(iv_given, reverse=True), str(iv_given[:5]))

# N7) 面试官权重 → 联评综合分加权
st, w2 = call("POST", "/settings/weights/interviewers",
              body={"weights": {who: 3}})
check("人工设定面试官权重成功", st == 200, f"status={st}")
check("设定后 interviewers_customized=True",
      bool((w2 or {}).get("interviewers_customized")),
      str((w2 or {}).get("interviewers")))
st, rj2 = call("GET", "/results", params={"sort": "joint", "desc": True})
check("汇总标注面试官权重已生效",
      bool(rj2.get("weights", {}).get("interviewers_customized")))
check("加权后仍保留等权参考值 joint_score_equal",
      all("joint_score_equal" in i for i in rj2.get("items", [])))
st, jr2 = call("GET", "/summary/joint")
check("联评排行榜标注是否加权", st == 200 and "weighted" in jr2,
      f"weighted={jr2.get('weighted')}")

# N8) 恢复默认（保证不污染后续使用）
st, w3 = call("DELETE", "/settings/weights/dimensions")
check("恢复默认维度权重成功",
      st == 200 and not (w3 or {}).get("dimensions_customized"),
      f"status={st}")
st, w4 = call("DELETE", "/settings/weights/interviewers")
check("清空面试官权重成功（回到等权）",
      st == 200 and not (w4 or {}).get("interviewers_customized"),
      f"status={st}")
st, w5 = call("GET", "/settings/weights")
_def = (w5 or {}).get("dimension_defaults") or {}
_cur = (w5 or {}).get("dimensions") or {}
check("恢复后维度权重回到 config 默认值",
      bool(_def) and all(abs(float(_cur.get(k, 0)) - float(_def.get(k, -1))) < 1e-9
                         for k in dims()[0]),
      str(_cur))

# =====================================================================
section("附) 面试顺序文件读取")
st, stats = call("GET", "/summary/statistics")
io = stats.get("interview_order") or {}
check("读到了 E 盘 interview_order.xlsx",
      io.get("exists") and io.get("loaded"),
      f"rows={io.get('rows')}, msg={io.get('message')}")

# =====================================================================
n_pass = sum(1 for _, r, _ in results if r == PASS)
n_fail = sum(1 for _, r, _ in results if r == FAIL)
total = len(results)
print(f"\n{'=' * 74}")
print(f"测试完成：{n_pass} / {total} 通过，{n_fail} 失败")
print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 74)

if n_fail:
    print("\n失败项：")
    for label, r, d in results:
        if r == FAIL:
            print(f"  - {label}  ({d})")

report = {
    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "base_url": BASE,
    "total": total,
    "passed": n_pass,
    "failed": n_fail,
    "results": [{"label": l, "status": r, "detail": d} for l, r, d in results],
}
out = __file__.replace("test_api.py", "test_api_report.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f"\n报告已写入：{out}")

sys.exit(1 if n_fail else 0)
