# -*- coding: utf-8 -*-
"""
离线测试：从面试顺序表同步候选人（sync_candidates_from_order）。
全部在临时目录进行：临时 Excel / 临时简历 / 临时 DB，绝不碰 E 盘原始数据。
"""
import sys
import shutil
from pathlib import Path

import tempfile

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ / "config"))
sys.path.insert(0, str(PROJ))

TMP = Path(tempfile.gettempdir()) / "sync_test"
if TMP.exists():
    shutil.rmtree(TMP)
TMP.mkdir(parents=True)
(DATA := TMP / "data").mkdir()
(RESUMES := TMP / "resumes").mkdir()

import settings  # noqa: E402

# ---- 把服务指向临时目录 ----
settings.INTERVIEW_ORDER_XLSX = DATA / "interview_order.xlsx"
settings.RESUME_DIR = RESUMES
settings.DB_PATH = TMP / "test.db"

from backend.app import db  # noqa: E402
from backend.app.services import interview_order_service as ios  # noqa: E402

results = []


def check(label, ok, detail=""):
    results.append((label, ok, detail))
    print(("PASS " if ok else "FAIL ") + label + ((" | " + str(detail)[:90]) if detail else ""))


# ---- 1. 造临时顺序表（3 行：1 已有 + 1 新人有简历 + 1 新人无简历） ----
from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws.title = "面试顺序"
ws.append(["序号", "姓名", "学号", "专业", "应聘岗位", "手机"])
ws.append([1, "张明", "20210101", "计算机科学与技术", "后端开发", "13800000001"])
ws.append([2, "测试新人A", "20290101", "软件工程", "前端开发", "13800000002"])
ws.append([3, "测试新人B", "20290102", "数据科学", "数据分析", "13800000003"])
order_path = DATA / "interview_order.xlsx"
wb.save(order_path)
check("造临时顺序表 Excel", order_path.is_file())

# ---- 2. 造临时简历：张明（已有候选人，已有标记不动的场景见下）与测试新人A ----
(RESUMES / "张明_后端开发.txt").write_text("张明的简历内容：Python / FastAPI。", encoding="utf-8")
(RESUMES / "测试新人A_前端开发.txt").write_text("测试新人A的简历内容：React / TS。", encoding="utf-8")
check("造临时简历文件", (RESUMES / "测试新人A_前端开发.txt").is_file())

# ---- 3. 初始化临时库：预置「张明」（无简历标记）与「库里多余」 ----
db.init_db()
db.upsert_candidate({
    "name": "张明", "student_no": "20210101", "major": "旧专业",
    "order_index": 5, "resume_exists": 0,
    "resume_file": None, "resume_path": None,
    "resume_text": "已有解析文本不应被冲掉", "resume_parsed": '{"level":"推荐"}',
})
db.upsert_candidate({
    "name": "库里多余", "student_no": "20990101", "order_index": 9,
    "resume_exists": 0,
})
n0 = db.count_candidates()
check("预置候选人（张明 + 库里多余）", n0 == 2, f"n={n0}")

# ---- 4. 第一次同步：张明更新；A/B 新增；A 自动挂简历；多余的人不被删 ----
r1 = ios.sync_candidates_from_order()
check("同步 ok", r1.get("ok") is True, r1.get("message"))
check("读到 3 行", r1.get("rows") == 3)
check("新增 2 人（A/B）", len(r1.get("added") or []) == 2, r1.get("added"))
check("更新 1 人（张明）", r1.get("updated") == 1)
check("张明自动挂上简历", "张明" in (r1.get("resume_attached") or []),
      r1.get("resume_attached"))

c_zm = [c for c in db.list_candidates() if c["name"] == "张明"][0]
check("张明 order_index 被 Excel 更新（5→1）", c_zm["order_index"] == 1,
      f"order={c_zm['order_index']}")
check("张明专业被 Excel 更新", c_zm["major"] == "计算机科学与技术", c_zm["major"])
check("张明已有 resume_text 保留不被冲掉",
      c_zm.get("resume_text") == "已有解析文本不应被冲掉")
check("张明 resume_exists 置 1", c_zm["resume_exists"] == 1)

c_a = [c for c in db.list_candidates() if c["name"] == "测试新人A"][0]
check("新人A 入库并挂简历", c_a["resume_exists"] == 1 and c_a["order_index"] == 2,
      f"exists={c_a['resume_exists']}, order={c_a['order_index']}")

c_b = [c for c in db.list_candidates() if c["name"] == "测试新人B"][0]
check("新人B 入库（无简历）", c_b["resume_exists"] == 0)

check("Excel 没有的人不被删除（库里多余仍在）",
      any(c["name"] == "库里多余" for c in db.list_candidates()))
check("总人数 = 2 + 2", db.count_candidates() == 4, f"n={db.count_candidates()}")

# ---- 5. 第二次同步：幂等（不再新增） ----
r2 = ios.sync_candidates_from_order()
check("第二次同步幂等（added=0）", len(r2.get("added") or []) == 0, r2.get("message"))
check("第二次同步 updated=3", r2.get("updated") == 3, r2.get("updated"))
check("人数仍为 4", db.count_candidates() == 4)

# ---- 6. 面试记录不被同步破坏：给张明写一条面试，再同步，记录仍在 ----
import json as _json
db.save_interview({"candidate_id": c_zm["id"], "round": 1,
                   "scores": _json.dumps(
                       {settings.SCORE_DIMENSIONS[0]["key"]: 80}, ensure_ascii=False),
                   "status": "completed",
                   "total_score": 80.0})
ios.sync_candidates_from_order()
ivs = db.list_interviews(c_zm["id"])
check("同步后张明的面试记录仍在", len(ivs) >= 1, f"{len(ivs)} 条")

# ---- 汇总 ----
n_pass = sum(1 for _, ok, _ in results if ok)
print(f"\n== {n_pass}/{len(results)} 通过 ==")
sys.exit(0 if n_pass == len(results) else 1)
