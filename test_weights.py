# -*- coding: utf-8 -*-
"""
离线测试：评分权重的人工设定（维度权重 + 面试官权重）与多口径排序基础数据。

全部在临时目录 + 临时 DB 进行，绝不碰 E 盘原始数据、绝不写真实库。

覆盖：
  1. 默认维度权重来自 config/settings.py
  2. 人工设定维度权重（可只改部分，其余保留默认）
  3. 非法权重（负数 / 全 0 / 非数字 / 全是未知维度）→ 抛错
  4. 恢复默认维度权重
  5. 自定义权重重算加权总分（无需合计为 100，自动归一化）
  6. 面试官权重的设定 / 读取 / 重置
  7. 面试官权重为负 → 抛错
  8. 联评综合分按面试官权重加权（两人：2:1）
  9. 未出现在权重表里的面试官默认权重 1
 10. 权重全为 1 → 结果与等权完全一致
 11. dimension_averages：跨轮次取各维度平均
 12. interviewer_averages：每位面试官的平均分
 13. 只读校验：计算前后 interviews 行数不变
"""
import json
import shutil
import sys
from pathlib import Path

import tempfile

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ / "config"))
sys.path.insert(0, str(PROJ))

TMP = Path(tempfile.gettempdir()) / "weights_test"
if TMP.exists():
    shutil.rmtree(TMP)
TMP.mkdir(parents=True)

import settings  # noqa: E402

settings.DB_PATH = TMP / "weights.db"

from backend.app import db  # noqa: E402
from backend.app.services import joint_service as js  # noqa: E402
from backend.app.services import weights_service as ws  # noqa: E402
from backend.app.services.scoring_service import weighted_total  # noqa: E402

results = []


def check(label, ok, detail=""):
    results.append((label, ok, detail))
    print(("PASS " if ok else "FAIL ") + label + ((" | " + str(detail)[:120]) if detail else ""))


def expect_error(label, fn, keyword=""):
    try:
        fn()
    except ValueError as exc:
        ok = (keyword in str(exc)) if keyword else True
        check(label, ok, f"ValueError: {exc}")
        return
    except Exception as exc:            # noqa: BLE001
        check(label, False, f"抛出非 ValueError：{type(exc).__name__}: {exc}")
        return
    check(label, False, "没有抛错（应当拒绝非法输入）")


db.init_db()

# 维度定义直接取自 config/settings.py（改配置后本测试自动跟随，无需手改）
DKEYS = [d["key"] for d in settings.SCORE_DIMENSIONS]
DEFAULT_W = {d["key"]: float(d["weight"]) for d in settings.SCORE_DIMENSIONS}
K0, K1, K2, K3 = (DKEYS + DKEYS + DKEYS + DKEYS)[:4]
NDIM = len(DKEYS)
ALL90 = {k: 90 for k in DKEYS}
ALL60 = {k: 60 for k in DKEYS}
ALL30 = {k: 30 for k in DKEYS}


def new_candidate(name, order):
    return db.upsert_candidate(
        {"name": name, "student_no": f"W{order:04d}", "order_index": order,
         "resume_exists": 0}
    )


DEFAULT_W = {d["key"]: float(d["weight"]) for d in settings.SCORE_DIMENSIONS}


def add_round(cid, rnd, scores: dict, interviewer=None, status="completed"):
    total = None
    if scores:
        hit = {k: v for k, v in scores.items() if k in DEFAULT_W}
        wsum = sum(DEFAULT_W[k] for k in hit)
        total = round(sum(hit[k] * DEFAULT_W[k] for k in hit) / wsum, 2)
    db.save_interview({
        "candidate_id": cid, "round": rnd,
        "interviewer": interviewer,
        "scores": json.dumps(scores, ensure_ascii=False) if scores else None,
        "total_score": total,
        "status": status,
        "comment": None,
    })
    return total


# ============================================================ 1. 默认权重
w = ws.get_dimension_weights()
check(f"默认维度权重来自 settings（{NDIM} 维，与 config 一致）",
      w == DEFAULT_W and all(abs(w[k] - DEFAULT_W[k]) < 1e-9 for k in DKEYS),
      str(w))
check("未设定时 is_dimension_weights_customized=False", ws.is_dimension_weights_customized() is False)
check("未设定时面试官权重为空（= 等权）", ws.get_interviewer_weights() == {})

# ============================================================ 2. 设定维度权重
saved = ws.set_dimension_weights({K0: 60, K1: 40})
check("只传部分维度 → 其余保留默认",
      saved[K0] == 60 and saved[K1] == 40
      and abs(saved[K2] - DEFAULT_W[K2]) < 1e-9,
      str(saved))
check("设定后 customized=True", ws.is_dimension_weights_customized() is True)

# ============================================================ 3. 非法输入
expect_error("负权重 → 抛错", lambda: ws.set_dimension_weights({K0: -1}), "负数")
expect_error("全 0 权重 → 抛错", lambda: ws.set_dimension_weights({K0: 0}), "大于 0")
expect_error("非数字权重 → 抛错", lambda: ws.set_dimension_weights({K0: "abc"}), "不是数字")
expect_error("全是未知维度 → 抛错", lambda: ws.set_dimension_weights({"nope": 1}), "有效维度")
expect_error("空对象 → 抛错", lambda: ws.set_dimension_weights({}), "至少")

check("非法输入未污染已保存的权重（仍是 60/40）",
      ws.get_dimension_weights()[K0] == 60)

# ============================================================ 4. 未知维度被忽略
mix = ws.set_dimension_weights({K0: 50, K1: 30, "unknown_dim": 999})
check("未知维度被忽略、合法维度生效",
      mix[K0] == 50 and mix[K1] == 30 and "unknown_dim" not in mix,
      str(mix))

# ============================================================ 5. 自定义权重重算加权总分
ws.set_dimension_weights(dict(zip(DKEYS, [60, 40, 20, 15][:NDIM])))
w2 = ws.get_dimension_weights()
t = weighted_total({K0: 80, K1: 60}, w2)
check("自定义权重重算：(80×60 + 60×40)/(60+40) = 72",
      t == 72.0, f"total={t}")
t_norm = weighted_total({K0: 100, K1: 100}, w2)
check("满分维度 → 加权后仍是 100", t_norm == 100.0, f"total={t_norm}")
t_default = weighted_total({K0: 80, K1: 60})
check("不传权重 → 仍用默认权重（行为不变）",
      abs(t_default - (80 * DEFAULT_W[K0] + 60 * DEFAULT_W[K1])
          / (DEFAULT_W[K0] + DEFAULT_W[K1])) < 0.01,
      f"total={t_default}")

# ============================================================ 6. 恢复默认
back = ws.reset_dimension_weights()
check("恢复默认 → 权重回到 config 默认值",
      abs(back[K0] - DEFAULT_W[K0]) < 1e-9, str(back))
check("恢复默认 → customized=False", ws.is_dimension_weights_customized() is False)

# ============================================================ 7. 面试官权重
iw = ws.set_interviewer_weights({"王老师": 2, "李老师": 1})
check("面试官权重保存成功", iw == {"王老师": 2.0, "李老师": 1.0}, str(iw))
check("面试官权重 customized=True", ws.is_interviewer_weights_customized() is True)
expect_error("面试官负权重 → 抛错",
             lambda: ws.set_interviewer_weights({"王老师": -2}), "负数")
expect_error("非数字面试官权重 → 抛错",
             lambda: ws.set_interviewer_weights({"王老师": "x"}), "不是数字")
check("非法输入未污染已保存值", ws.get_interviewer_weights() == {"王老师": 2.0, "李老师": 1.0})

# ============================================================ 8. 联评按面试官权重加权
c1 = new_candidate("加权同学", 1)
add_round(c1, 1, ALL90, interviewer="王老师")
add_round(c1, 2, ALL60, interviewer="李老师")

j_eq = js.joint_evaluation(c1)
check("不传权重 → 等权平均 (90+60)/2 = 75",
      j_eq["joint_score"] == 75.0 and j_eq["joint_score_equal"] == 75.0,
      f"joint={j_eq['joint_score']}")
check("不传权重 → weights_applied=False", j_eq["weights_applied"] is False)

j_w = js.joint_evaluation(c1, interviewer_weights={"王老师": 2, "李老师": 1})
check("按 2:1 加权 → (90×2 + 60×1)/3 = 80",
      j_w["joint_score"] == 80.0, f"joint={j_w['joint_score']}")
check("加权后仍保留等权参考值 75", j_w["joint_score_equal"] == 75.0)
check("weights_applied=True", j_w["weights_applied"] is True)
check("面试官明细带 weight 字段",
      {x["interviewer"]: x["weight"] for x in j_w["interviewers"]} ==
      {"王老师": 2.0, "李老师": 1.0},
      str([(x["interviewer"], x["weight"]) for x in j_w["interviewers"]]))
check("加权不改变分歧度（σ 仍按平均分算）", j_w["spread"] == 30.0, f"spread={j_w['spread']}")
check("加权后规则说明随之变化", "权重" in j_w["rule"], j_w["rule"])

# ============================================================ 9. 未在权重表 → 默认 1
c2 = new_candidate("三人评同学", 2)
add_round(c2, 1, ALL90, interviewer="A")
add_round(c2, 2, ALL60, interviewer="B")
add_round(c2, 3, ALL30, interviewer="C")
j3 = js.joint_evaluation(c2, interviewer_weights={"A": 2})
check("只给 A 加权 2、B/C 默认 1 → (90×2+60+30)/4 = 67.5",
      j3["joint_score"] == 67.5, f"joint={j3['joint_score']}")
check("B/C 的生效权重为 1",
      {x["interviewer"]: x["weight"] for x in j3["interviewers"]}["B"] == 1.0)

# ============================================================ 10. 权重全为 1 → 等于等权
j1 = js.joint_evaluation(c2, interviewer_weights={"A": 1, "B": 1, "C": 1})
check("权重全为 1 → 与等权结果一致",
      j1["joint_score"] == j1["joint_score_equal"] == 60.0, f"joint={j1['joint_score']}")

# ============================================================ 11. 维度平均
c3 = new_candidate("维度平均同学", 3)
_r1 = {k: v for k, v in zip(DKEYS, [80, 90, 70, 60, 50])}
_r2 = {k: v for k, v in zip(DKEYS, [60, 70, 90, 80, 70])}
add_round(c3, 1, _r1, interviewer="A")
add_round(c3, 2, _r2, interviewer="B")
da = js.dimension_averages(c3)
check(f"dimension_averages 跨轮取平均：{K0}=(80+60)/2=70",
      da[K0] == 70.0, str(da))
check(f"dimension_averages 覆盖全部 {NDIM} 个维度", len(da) == NDIM, f"keys={sorted(da)}")
check(f"{K1}=(90+70)/2=80", da[K1] == 80.0, f"{K1}={da[K1]}")

# 自定义权重排序依据：只看第一个维度
ws.set_dimension_weights({K0: 100, **{k: 0 for k in DKEYS if k != K0}})
da2 = js.dimension_averages(c3)
t_dim = weighted_total(da2, ws.get_dimension_weights())
check(f"按「只看 {K0}」的权重重算 → 等于其平均分 70",
      t_dim == 70.0, f"total={t_dim}")
ws.reset_dimension_weights()

# ============================================================ 12. 面试官平均
ia = js.interviewer_averages(c3)
check("interviewer_averages：A 与 B 各一条",
      set(ia.keys()) == {"A", "B"}, str(ia))

# ============================================================ 13. 只读校验
before = len(db.list_interviews(c3))
js.joint_evaluation(c3)
js.dimension_averages(c3)
js.interviewer_averages(c3)
ws.get_dimension_weights()
after = len(db.list_interviews(c3))
check("权重与联评计算全程只读（记录数不变）", before == after, f"{before} -> {after}")

# ============================================================ 14. 快照
ws.set_interviewer_weights({"X": 3})
snap = ws.snapshot()
check("snapshot 含维度/面试官权重与标签",
      "dimensions" in snap and "interviewers" in snap and "dimension_labels" in snap)
check("snapshot 反映最新的面试官权重", snap["interviewers"] == {"X": 3.0}, str(snap["interviewers"]))
ws.reset_interviewer_weights()
check("重置面试官权重 → 空（等权）", ws.get_interviewer_weights() == {})

# ============================================================ 汇总
n_pass = sum(1 for _, ok, _ in results if ok)
print(f"\n== {n_pass}/{len(results)} 通过 ==")
sys.exit(0 if n_pass == len(results) else 1)
