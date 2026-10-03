# -*- coding: utf-8 -*-
"""
离线测试：联评综合评分（多面试官平均成绩）。

全部在临时目录 + 临时 DB 进行，绝不碰 E 盘原始数据、绝不写真实库。

覆盖：
  1. 无任何评分 → has_data=False，不报错
  2. 只有 1 位面试官 → 联评分 = 该面试官平均分
  3. 2 位面试官 → 联评分 = 两人平均分的平均
  4. 4 位面试官 → 等权平均（不被某位多面几轮放大权重）
  5. 同一面试官多轮 → 先取该面试官平均，再参与联评
  6. in_progress 但已打分 → 也计入联评
  7. 未打分的记录 → 不计入
  8. 分歧度：一致 → 高度一致；差异大 → 分歧较大
  9. 每人平均分四舍五入到 2 位；等级评定合理
 10. 只读：调用前后 interviews 行数不变
"""
import json
import shutil
import sys
from pathlib import Path

import tempfile

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ / "config"))
sys.path.insert(0, str(PROJ))

TMP = Path(tempfile.gettempdir()) / "joint_test"
if TMP.exists():
    shutil.rmtree(TMP)
TMP.mkdir(parents=True)

import settings  # noqa: E402

settings.DB_PATH = TMP / "joint.db"

from backend.app import db  # noqa: E402
from backend.app.services import joint_service as js  # noqa: E402

results = []


def check(label, ok, detail=""):
    results.append((label, ok, detail))
    print(("PASS " if ok else "FAIL ") + label + ((" | " + str(detail)[:100]) if detail else ""))


db.init_db()

# 维度定义取自 config/settings.py —— 改维度时本测试自动跟随
DKEYS = [d["key"] for d in settings.SCORE_DIMENSIONS]
DIM_W = {d["key"]: float(d["weight"]) for d in settings.SCORE_DIMENSIONS}


def uniform(v):
    """所有维度都给同一个分（联评分就等于该分值，与权重无关）。"""
    return {k: v for k in DKEYS}




def new_candidate(name, order):
    return db.upsert_candidate(
        {"name": name, "student_no": f"S{order:04d}", "order_index": order,
         "resume_exists": 0}
    )


def add_round(cid, rnd, scores: dict, interviewer=None, status="completed"):
    total = None
    if scores:
        hit = {k: v for k, v in scores.items() if k in DIM_W}
        wsum = sum(DIM_W[k] for k in hit)
        total = round(sum(hit[k] * DIM_W[k] for k in hit) / wsum, 2)
    db.save_interview({
        "candidate_id": cid, "round": rnd,
        "interviewer": interviewer,
        "scores": json.dumps(scores, ensure_ascii=False) if scores else None,
        "total_score": total,
        "status": status,
        "comment": None,
    })
    return total


# ---------------- 1. 没有任何评分 ----------------
c1 = new_candidate("空数据同学", 1)
j = js.joint_evaluation(c1)
check("无评分 → has_data=False 且不报错", j["has_data"] is False and j["joint_score"] is None,
      f"joint={j['joint_score']}")
check("无评分 → 面试官数为 0", j["interviewer_count"] == 0)
check("无评分 → 等级为「未评分」", j["joint_level"] == "未评分", j["joint_level"])

# ---------------- 2. 只有 1 位面试官 ----------------
c2 = new_candidate("单人评同学", 2)
t = add_round(c2, 1, uniform(80), interviewer="王老师")
j = js.joint_evaluation(c2)
check("1 位面试官 → 联评分 = 该面试官平均分",
      j["joint_score"] == 80.0, f"joint={j['joint_score']} total={t}")
check("1 位面试官 → consensus = 仅 1 位面试官", j["consensus"] == "仅 1 位面试官",
      j["consensus"])

# ---------------- 3. 2 位面试官 ----------------
c3 = new_candidate("双人评同学", 3)
add_round(c3, 1, uniform(60), interviewer="面试官A")
add_round(c3, 2, uniform(80), interviewer="面试官B")
j = js.joint_evaluation(c3)
check("2 位面试官 → 联评分 = (60+80)/2 = 70",
      j["joint_score"] == 70.0, f"joint={j['joint_score']}")
check("2 位面试官 → 人数统计正确", j["interviewer_count"] == 2, j["interviewer_count"])
check("2 位面试官 → 明细含两人各自均分",
      {x["interviewer"]: x["avg_score"] for x in j["interviewers"]} ==
      {"面试官A": 60.0, "面试官B": 80.0},
      str([(x["interviewer"], x["avg_score"]) for x in j["interviewers"]]))
check("2 位面试官 → 保留最高/最低", j["best_score"] == 80.0 and j["lowest_score"] == 60.0,
      f"{j['best_score']}/{j['lowest_score']}")

# ---------------- 4. 4 位面试官，其中一位面了 3 轮（等权检查） ----------------
c4 = new_candidate("四人评同学", 4)
add_round(c4, 1, uniform(100), interviewer="面试官A")
add_round(c4, 2, uniform(100), interviewer="面试官A")
add_round(c4, 3, uniform(100), interviewer="面试官A")
add_round(c4, 4, uniform(70), interviewer="面试官B")
add_round(c4, 5, uniform(70), interviewer="面试官C")
add_round(c4, 6, uniform(70), interviewer="面试官D")
j = js.joint_evaluation(c4)
# A=100（3 轮）、B=C=D=70 → 等权平均 = (100+70+70+70)/4 = 77.5
check("4 位面试官 → 等权平均 77.5（多面几轮不放大权重）",
      j["joint_score"] == 77.5, f"joint={j['joint_score']}")
check("4 位面试官 → A 的 3 轮先合并为 100",
      [x for x in j["interviewers"] if x["interviewer"] == "面试官A"][0]["avg_score"] == 100.0)
check("4 位面试官 → 轮次总数为 6", j["rounds_considered"] == 6, j["rounds_considered"])
check("4 位面试官 → 等级为「推荐」", j["joint_level"] == "推荐", j["joint_level"])

# ---------------- 5. 同一面试官多轮取平均 ----------------
c5 = new_candidate("多轮同人", 5)
add_round(c5, 1, uniform(50), interviewer="张老师")
add_round(c5, 2, uniform(90), interviewer="张老师")
j = js.joint_evaluation(c5)
check("同一面试官 2 轮 → 取平均 70",
      j["joint_score"] == 70.0 and j["interviewers"][0]["rounds"] == 2,
      f"joint={j['joint_score']} rounds={j['interviewers'][0]['rounds']}")

# ---------------- 6. in_progress 但已打分 → 计入 ----------------
c6 = new_candidate("进行中同学", 6)
add_round(c6, 1, uniform(85),
          interviewer="李老师", status="in_progress")
j = js.joint_evaluation(c6)
check("in_progress 但已打分 → 计入联评",
      j["joint_score"] == 85.0, f"joint={j['joint_score']}")

# ---------------- 7. 未打分的记录 → 不计入 ----------------
c7 = new_candidate("只开轮未打分", 7)
add_round(c7, 1, {}, interviewer="赵老师", status="in_progress")
j = js.joint_evaluation(c7)
check("空评分轮次 → 不计入联评",
      j["has_data"] is False and j["rounds_considered"] == 0,
      f"rounds={j['rounds_considered']}")

# ---------------- 8. 分歧度标签 ----------------
c8 = new_candidate("一致同学", 8)
add_round(c8, 1, uniform(80), interviewer="A")
add_round(c8, 2, uniform(82), interviewer="B")
j = js.joint_evaluation(c8)
check("分数接近 → 高度一致", j["consensus"] == "高度一致", j["consensus"])

c9 = new_candidate("分歧同学", 9)
add_round(c9, 1, uniform(50), interviewer="A")
add_round(c9, 2, uniform(95), interviewer="B")
j = js.joint_evaluation(c9)
check("分数差异大 → 分歧较大", j["consensus"] == "分歧较大", j["consensus"])
check("分歧较大 → 保留 spread 差值", j["spread"] == 45.0, j["spread"])

# ---------------- 9. 未填写面试官 → 归入「（未填写面试官）」 ----------------
c10 = new_candidate("无名面试官", 10)
add_round(c10, 1, uniform(70), interviewer=None)
j = js.joint_evaluation(c10)
check("未填写面试官 → 使用占位名",
      j["interviewers"][0]["interviewer"] == js.DEFAULT_INTERVIEWER,
      j["interviewers"][0]["interviewer"])

# ---------------- 10. 只读校验：行数不变 ----------------
before = len(db.list_interviews(c4))
js.joint_evaluation(c4)
js.joint_evaluation(c4)
after = len(db.list_interviews(c4))
check("联评计算只读（记录数不变）", before == after, f"{before} -> {after}")

# ---------------- 11. 排行榜总览 ----------------
ov = js.joint_overview()
check("联评总览覆盖所有候选人数", len(ov) == db.count_candidates(),
      f"{len(ov)} / {db.count_candidates()}")
check("总览含联评分数与人数", all("joint_score" in r and "interviewer_count" in r for r in ov))

# ---------------- 汇总 ----------------
n_pass = sum(1 for _, ok, _ in results if ok)
print(f"\n== {n_pass}/{len(results)} 通过 ==")
sys.exit(0 if n_pass == len(results) else 1)
