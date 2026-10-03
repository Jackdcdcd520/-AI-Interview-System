# -*- coding: utf-8 -*-
"""
生成测试数据：5 名模拟候选人 + 简历文件 + interview_order.xlsx

数据安全：
  - 只**新增**文件，已存在的文件默认跳过（加 --force 才覆盖，覆盖前会备份为 .bak）；
  - 不会删除任何已有文件。
用法：
    python scripts/make_test_data.py            # 缺什么补什么
    python scripts/make_test_data.py --force    # 强制重建（先备份）
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "config"))

import settings  # noqa: E402

# ---------------------------------------------------------------- 模拟候选人
CANDIDATES = [
    {
        "order": 1,
        "name": "张明",
        "student_no": "20220101",
        "major": "计算机科学与技术",
        "grade": "大四",
        "position": "后端开发",
        "phone": "13800000001",
        "email": "zhangming@example.edu.cn",
        "resume_file": "张明_后端开发.pdf.txt",
        "profile": "基础扎实、项目经历完整的后端方向学生",
    },
    {
        "order": 2,
        "name": "李雪",
        "student_no": "20220102",
        "major": "软件工程",
        "grade": "大四",
        "position": "前端开发",
        "phone": "13800000002",
        "email": "lixue@example.edu.cn",
        "resume_file": "李雪_前端开发.docx.txt",
        "profile": "注重用户体验、有实际上线项目的前端方向学生",
    },
    {
        "order": 3,
        "name": "王强",
        "student_no": "20220103",
        "major": "机械设计制造及其自动化",
        "grade": "大四",
        "position": "机械设计",
        "phone": "13800000003",
        "email": "wangqiang@example.edu.cn",
        "resume_file": "王强_机械设计.txt",
        "profile": "动手能力强、有竞赛获奖经历的机械方向学生",
    },
    {
        "order": 4,
        "name": "赵晓婷",
        "student_no": "20220104",
        "major": "数据科学与大数据技术",
        "grade": "大四",
        "position": "数据分析师",
        "phone": "13800000004",
        "email": "zhaoxiaoting@example.edu.cn",
        "resume_file": "赵晓婷_数据分析师.txt",
        "profile": "数据分析工具熟练、有实习经历的数据方向学生",
    },
    {
        "order": 5,
        "name": "陈浩然",
        "student_no": "20220105",
        "major": "电子信息工程",
        "grade": "大四",
        "position": "嵌入式开发",
        "phone": "13800000005",
        "email": "chenhaoran@example.edu.cn",
        "resume_file": "陈浩然_嵌入式开发.txt",
        "profile": "嵌入式软硬件都碰过、但项目深度一般的电子方向学生",
    },
    {
        "order": 6,
        "name": "孙悦",
        "student_no": "20220106",
        "major": "工商管理",
        "grade": "大三",
        "position": "产品经理",
        "phone": "13800000006",
        "email": "sunyue@example.edu.cn",
        "resume_file": None,   # 故意留一位无简历，用于验证"缺简历不崩溃"
        "profile": "沟通能力强、跨专业转产品方向的学生（测试无简历场景）",
    },
]

# ---------------------------------------------------------------- 简历正文模板
RESUME_TEMPLATES = {
    "张明": """姓名：张明
学号：20220101
专业：计算机科学与技术
年级：大四
应聘岗位：后端开发
手机：13800000001
邮箱：zhangming@example.edu.cn

【教育背景】
2022.09 - 2026.06  某某大学  计算机科学与技术  本科
主修课程：数据结构、操作系统、计算机网络、数据库系统、算法设计与分析
GPA：3.7 / 4.0   专业排名：8 / 120

【专业技能】
- 编程语言：Python（熟练）、Java（熟练）、C++（了解）、Go（了解）
- Web 框架：FastAPI、Django、Spring Boot
- 数据库：MySQL、PostgreSQL、Redis、MongoDB
- 工程工具：Git、Docker、Linux、Postman、Nginx
- 其它：熟悉 RESTful API 设计，了解微服务与消息队列基本概念

【项目经历】
1. 校园二手交易平台（后端负责人，2024.03 - 2024.09）
   - 使用 FastAPI + MySQL + Redis 实现用户、商品、订单三大模块共 40 余个接口；
   - 引入 Redis 缓存热点商品列表，QPS 从 120 提升至约 900；
   - 用 Docker Compose 编排服务，编写 GitHub Actions 完成自动测试与部署。
   - 项目在校内上线试运行，累计注册用户约 2000 人。

2. 分布式任务调度小工具（个人项目，2025.02 - 2025.05）
   - 基于 Python + Celery + Redis 实现定时与延时任务调度；
   - 支持任务失败重试与超时告警，编写了较完整的单元测试（覆盖率约 80%）。

【实习经历】
2025.07 - 2025.09  某某科技有限公司  后端开发实习生
- 参与公司内部数据接口重构，把 12 个老接口迁移到 FastAPI；
- 优化了 3 处慢 SQL，平均响应时间从 800ms 降到 150ms 左右。

【获奖情况】
- 2024 年蓝桥杯软件类省赛二等奖
- 2024 学年校级一等奖学金
""",
    "李雪": """姓名：李雪
学号：20220102
专业：软件工程
年级：大四
应聘岗位：前端开发
手机：13800000002
邮箱：lixue@example.edu.cn

【教育背景】
2022.09 - 2026.06  某某大学  软件工程  本科
主修课程：Web 前端技术、人机交互、软件工程、数据结构、数据库原理
GPA：3.5 / 4.0

【专业技能】
- 前端框架：React（熟练）、Vue（熟练）、Ant Design、Element Plus
- 语言与基础：JavaScript（熟练）、TypeScript（熟练）、HTML5、CSS3
- 工程化：Vite、Webpack、npm、Git、ESLint
- 设计协作：熟练使用 Figma 还原设计稿，了解响应式与无障碍基本规范
- 后端了解：Node.js + Express 写过简单接口，了解 MySQL 基本使用

【项目经历】
1. 校园活动报名与签到系统（前端负责人，2024.10 - 2025.03）
   - 使用 React + TypeScript + Ant Design 开发管理端与用户端共 20 余个页面；
   - 实现报名表单动态校验与二维码签到，活动报名转化率提升约 25%；
   - 首屏加载优化：路由懒加载 + 图片压缩，Lighthouse 性能分从 62 提到 91。

2. 个人作品集网站（个人项目，2025.06）
   - 使用 Vite + React 搭建，部署在静态托管平台；
   - 实现深色模式切换与滚动动画，移动端适配完整。

【实习经历】
2025.07 - 2025.09  某某互联网公司  前端开发实习生
- 参与营销活动页开发，独立完成 6 个活动页面并按时上线；
- 主动沉淀了一套活动页公共组件，被团队另外 3 个项目复用。

【获奖情况】
- 2024 年校级"互联网+"创新创业大赛三等奖
- 2025 年某某设计大赛（Web 组）优秀奖
""",
    "王强": """姓名：王强
学号：20220103
专业：机械设计制造及其自动化
年级：大四
应聘岗位：机械设计
手机：13800000003
邮箱：wangqiang@example.edu.cn

【教育背景】
2022.09 - 2026.06  某某大学  机械设计制造及其自动化  本科
主修课程：机械原理、机械设计、理论力学、材料力学、机械制造技术基础、液压与气压传动
GPA：3.6 / 4.0

【专业技能】
- 设计软件：SolidWorks（熟练，含装配体与工程图）、AutoCAD（熟练）
- 仿真分析：ANSYS（了解，做过简单静力学分析）、MATLAB（了解）
- 加工了解：熟悉车、铣、钻等常规加工工艺，会用游标卡尺、千分尺等量具
- 编程：会 C 语言基础，能用 STM32 做简单控制

【项目经历】
1. 小型自动分拣装置设计（团队 3 人，负责结构设计，2024.11 - 2025.05）
   - 使用 SolidWorks 完成整机三维建模，共 86 个零件、5 个主要装配体；
   - 设计凸轮与连杆机构实现物料分拣，实测分拣成功率约 95%；
   - 绘制 12 张零件图与 2 张装配图，图纸一次通过指导教师审核。

2. 减速器结构设计课程设计（个人，2025.03）
   - 完成二级圆柱齿轮减速器的参数计算与结构设计，输出完整设计说明书；
   - 在 ANSYS 中对关键轴做静力学分析，校核结果满足安全系数要求。

【竞赛经历】
- 2024 年全国大学生机械创新设计大赛  省级二等奖
- 2025 年校级工程训练综合能力竞赛  一等奖（负责结构部分）

【实习经历】
2025.07 - 2025.08  某某装备制造有限公司  结构设计实习生
- 协助工程师完成 2 套工装夹具的三维建模与出图；
- 参与车间装配跟线，记录并反馈了 5 处图纸与实物不符的问题。
""",
    "赵晓婷": """姓名：赵晓婷
学号：20220104
专业：数据科学与大数据技术
年级：大四
应聘岗位：数据分析师
手机：13800000004
邮箱：zhaoxiaoting@example.edu.cn

【教育背景】
2022.09 - 2026.06  某某大学  数据科学与大数据技术  本科
主修课程：概率论与数理统计、数据库原理、数据挖掘、机器学习、Python 数据分析、数据可视化
GPA：3.8 / 4.0   专业排名：5 / 96

【专业技能】
- 数据分析：Python（Pandas、NumPy、SciPy）、SQL（熟练，复杂查询与窗口函数）
- 机器学习：scikit-learn、PyTorch（入门），熟悉常见分类回归与聚类方法
- 可视化：Matplotlib、Seaborn、ECharts、Tableau（了解）
- 工具：Excel（熟练，数据透视与 Power Query）、Git、Linux 基础

【项目经历】
1. 某电商用户流失预测（课程项目负责人，2024.09 - 2025.01）
   - 处理约 30 万条用户行为数据，完成清洗、特征工程与建模全流程；
   - 对比逻辑回归、随机森林、XGBoost 三种模型，随机森林 AUC 达到 0.86；
   - 输出特征重要性分析，识别出"最近登录间隔""优惠券使用率"为关键因子。

2. 校园食堂消费数据分析（个人项目，2025.04）
   - 基于 8 万条匿名消费记录，用 SQL + Pandas 分析就餐时段与窗口偏好；
   - 制作交互式可视化看板，为食堂窗口调整提供了数据参考。

【实习经历】
2025.07 - 2025.10  某某数据科技公司  数据分析实习生
- 负责日常业务报表搭建与维护，把原需 2 小时的手工周报压缩到自动生成；
- 参与一次用户分层分析，输出分层运营建议并被业务方采纳 2 条。

【获奖情况】
- 2024 年全国大学生数学建模竞赛  省级一等奖
- 2025 年校级数据分析挑战赛  二等奖
""",
    "陈浩然": """姓名：陈浩然
学号：20220105
专业：电子信息工程
年级：大四
应聘岗位：嵌入式开发
手机：13800000005
邮箱：chenhaoran@example.edu.cn

【教育背景】
2022.09 - 2026.06  某某大学  电子信息工程  本科
主修课程：模拟电子技术、数字电子技术、单片机原理与应用、嵌入式系统设计、信号与系统
GPA：3.3 / 4.0

【专业技能】
- 嵌入式：STM32（较熟练，会标准库与 HAL 库）、C 语言（熟练）
- 硬件：Altium Designer 画过双层板，会焊接与基本电路调试
- 通信：了解 UART、I2C、SPI、CAN 基本使用
- 其它：Python 基础、Linux 基本命令、Git 基本操作

【项目经历】
1. 基于 STM32 的智能鱼缸监控系统（个人，2024.12 - 2025.04）
   - 使用 STM32F103 + DHT11 + 水位传感器采集环境数据；
   - 通过 OLED 本地显示，并用 ESP8266 上传数据到自建服务器；
   - 实现自动补光与定时投喂，实物运行基本稳定，偶尔出现传感器读数跳变。

2. 电子设计课程实践：简易数字频率计（小组 2 人，2024.05）
   - 负责单片机部分程序编写，实现 1Hz~1MHz 频率测量功能。

【竞赛经历】
- 2024 年全国大学生电子设计竞赛  参与奖
- 2025 年校级嵌入式竞赛  三等奖

【自我评价】
动手意愿强，硬件软件都愿意学，但项目深度和系统设计经验还有明显不足，
希望在实习中系统性地补齐工程规范与调试能力。
""",
}

# 故意不生成孙悦的简历 → 验证"简历缺失不崩溃"


def _write_text(path: Path, content: str, force: bool) -> str:
    if path.exists() and not force:
        return f"SKIP(已存在)  {path}"
    if path.exists() and force:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"WROTE         {path}  ({path.stat().st_size} B)"


def write_resumes(force: bool) -> list[str]:
    logs = []
    settings.RESUME_DIR.mkdir(parents=True, exist_ok=True)
    for c in CANDIDATES:
        fn = c.get("resume_file")
        if not fn:
            logs.append(f"SKIP(故意无简历) {c['name']} —— 用于测试缺失简历场景")
            continue
        body = RESUME_TEMPLATES.get(c["name"])
        if not body:
            continue
        logs.append(_write_text(settings.RESUME_DIR / fn, body, force))
    return logs


def write_interview_order(force: bool) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    path = settings.INTERVIEW_ORDER_XLSX
    if path.exists() and not force:
        return f"SKIP(已存在)  {path}"

    if path.exists() and force:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "面试顺序"

    headers = ["序号", "姓名", "学号", "专业", "年级", "应聘岗位",
               "手机", "邮箱", "简历文件", "面试官"]
    ws.append(headers)

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="4472C4")
    for i, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=i)
        cell.font = head_font
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for c in CANDIDATES:
        ws.append([
            c["order"], c["name"], c["student_no"], c["major"], c["grade"],
            c["position"], c["phone"], c["email"], c.get("resume_file") or "", "",
        ])

    widths = [6, 10, 12, 26, 8, 14, 14, 28, 26, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    ws.freeze_panes = "A2"

    wb.save(str(path))
    return f"WROTE         {path}  ({path.stat().st_size} B)"


def write_sample_interviews(force: bool) -> list[str]:
    """
    写入 2 条**已完成**的历史面试记录（用于演示汇总/排序）。
    遵循数据安全：已存在的记录 UPSERT 更新，不新增重复行。
    """
    sys.path.insert(0, str(PROJECT_ROOT))
    from backend.app import db

    db.init_db()
    logs = []

    sys.path.insert(0, str(PROJECT_ROOT / "config"))
    import settings as _settings
    _keys = [d["key"] for d in _settings.SCORE_DIMENSIONS]

    def _scores(values):
        """按当前配置的维度顺序铺开分数（改维度后示例数据自动跟随）。"""
        return {k: v for k, v in zip(_keys, values)}

    samples = [
        {
            "student_no": "20220101", "round": 1, "interviewer": "王老师",
            "scores": _scores([88, 85, 78, 90, 86]),
            "comment": "项目讲得很清楚，工程规范意识不错；表达略紧张，可以再放松一点。",
        },
        {
            "student_no": "20220102", "round": 1, "interviewer": "王老师",
            "scores": _scores([80, 78, 92, 85, 84]),
            "comment": "表达非常流畅，作品集完成度高；基础理论部分还可以再深入一些。",
        },
    ]

    from backend.app.services.scoring_service import weighted_total

    for s in samples:
        conn = db.connect()
        try:
            row = conn.execute(
                "SELECT id FROM candidates WHERE student_no = ?", (s["student_no"],)
            ).fetchone()
        finally:
            conn.close()

        if not row:
            logs.append(f"SKIP(候选人不存在) {s['student_no']}")
            continue

        cid = row["id"]
        existing = db.get_interview(cid, s["round"])
        if existing and existing.get("status") == "completed" and not force:
            logs.append(f"SKIP(已有记录)  {s['student_no']} 第 {s['round']} 轮")
            continue

        total = weighted_total(s["scores"])
        iid = db.save_interview({
            "candidate_id": cid,
            "round": s["round"],
            "interviewer": s["interviewer"],
            "scores": json.dumps(s["scores"], ensure_ascii=False),
            "total_score": total,
            "comment": s["comment"],
            "ai_summary": None,
            "ai_evaluation": None,
            "ai_provider": None,
            "status": "completed",
        })
        logs.append(f"UPSERT(示例记录) interview_id={iid} 总分={total}")
    return logs


def sync_candidates_to_db(force: bool) -> list[str]:
    """把候选人与简历信息写入 SQLite（幂等 upsert）。"""
    sys.path.insert(0, str(PROJECT_ROOT))
    from backend.app import db

    db.init_db()
    logs = []
    for c in CANDIDATES:
        fn = c.get("resume_file")
        rpath = settings.RESUME_DIR / fn if fn else None
        exists = bool(rpath and rpath.is_file())
        cid = db.upsert_candidate({
            "name": c["name"],
            "student_no": c["student_no"],
            "major": c["major"],
            "grade": c["grade"],
            "position": c["position"],
            "phone": c["phone"],
            "email": c["email"],
            "resume_file": fn,
            "resume_path": str(rpath) if rpath else None,
            "resume_exists": exists,
            "order_index": c["order"],
        })
        logs.append(
            f"UPSERT candidate id={cid:<3} {c['name']:<4} 顺序={c['order']} "
            f"简历={'有' if exists else '无'}"
        )
    return logs


def main() -> int:
    ap = argparse.ArgumentParser(description="生成面试系统测试数据")
    ap.add_argument("--force", action="store_true", help="覆盖已存在文件（先备份为 .bak）")
    ap.add_argument("--skip-interviews", action="store_true", help="不写入示例面试记录")
    args = ap.parse_args()

    print("=" * 72)
    print("生成测试数据")
    print(f"  简历目录 : {settings.RESUME_DIR}")
    print(f"  数据目录 : {settings.DATA_DIR}")
    print(f"  数据库   : {settings.DB_PATH}")
    print(f"  force    : {args.force}")
    print("=" * 72)

    all_logs: list[str] = []
    all_logs += ["--- 1) 简历文件 ---"] + write_resumes(args.force)
    all_logs += ["--- 2) 面试顺序 Excel ---", write_interview_order(args.force)]
    all_logs += ["--- 3) 候选人写入数据库 ---"] + sync_candidates_to_db(args.force)
    if not args.skip_interviews:
        all_logs += ["--- 4) 示例面试记录 ---"] + write_sample_interviews(args.force)

    for line in all_logs:
        print(line)

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "resume_dir": str(settings.RESUME_DIR),
        "interview_order_xlsx": str(settings.INTERVIEW_ORDER_XLSX),
        "db_path": str(settings.DB_PATH),
        "candidates": len(CANDIDATES),
        "logs": all_logs,
    }
    out = settings.DATA_DIR / "test_data_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入: {out}")
    print("\n完成。接下来启动后端：scripts\\start_backend.bat 或 "
          "python -m uvicorn backend.app.main:app --port 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
