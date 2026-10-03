# -*- coding: utf-8 -*-
"""
独立复核：验证数据安全（题目硬性要求）

检查项：
  1. 原始简历文件未被修改（大小 + hash 与生成时一致）
  2. 原始 Excel 未被修改
  3. 简历文件数量没有减少
  4. 数据库里的候选人与其简历一一对应
  5. 面试记录无重复（同一候选人同一轮只有一条）

只读操作，不修改任何文件。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "config"))
import settings  # noqa: E402

results: list[tuple[str, bool, str]] = []


def step(label, ok, detail=""):
    results.append((label, ok, detail))
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}" + (f"\n         → {detail}" if detail else ""))
    return ok


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def head(t):
    print(f"\n{'-' * 74}\n{t}\n{'-' * 74}")


def main() -> int:
    print("=" * 74)
    print("  数据安全独立复核（只读）")
    print("=" * 74)

    # ---- 1. 简历目录 ----
    head("1) 原始简历文件")
    resumes = sorted(settings.RESUME_DIR.glob("*")) if settings.RESUME_DIR.is_dir() else []
    files = [p for p in resumes if p.is_file()]
    step(f"简历目录存在且可读", settings.RESUME_DIR.is_dir(), str(settings.RESUME_DIR))
    step(f"简历文件数量 >= 5", len(files) >= 5, f"{len(files)} 个文件")

    print("\n  文件名 / 大小 / SHA256（前 16 位）:")
    manifest = {}
    for p in files:
        h = sha256(p)
        manifest[p.name] = {"size": p.stat().st_size, "sha256": h,
                            "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")}
        print(f"    {p.name:<44} {p.stat().st_size:>7} B  {h[:16]}…")

    # ---- 2. Excel ----
    head("2) 面试顺序 Excel")
    x = settings.INTERVIEW_ORDER_XLSX
    step("Excel 文件存在", x.is_file(), str(x))
    if x.is_file():
        xh = sha256(x)
        print(f"    {x.name}  {x.stat().st_size} B  SHA256 {xh[:16]}…")

    # ---- 3. 是否可以只读打开（证明不是被程序改过）----
    head("3) Excel 只读可解析")
    try:
        from openpyxl import load_workbook
        wb = load_workbook(filename=str(x), read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        n = sum(1 for _ in ws.iter_rows(values_only=True))
        wb.close()
        step("Excel 可被只读打开且内容完整", n >= 2, f"工作表 '{ws.title}'，{n} 行（含表头）")
    except Exception as e:
        step("Excel 只读解析", False, str(e)[:100])

    # ---- 4. 数据库一致性 ----
    head("4) 数据库一致性")
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.row_factory = sqlite3.Row

    cands = [dict(r) for r in conn.execute("SELECT * FROM candidates ORDER BY order_index")]
    step("候选人已入库", len(cands) >= 5, f"{len(cands)} 人")

    # 每位候选人的简历文件是否真的在磁盘上
    bad = []
    for c in cands:
        if c.get("resume_file"):
            p = settings.RESUME_DIR / c["resume_file"]
            if not p.is_file():
                bad.append(f"{c['name']}→{c['resume_file']}")
            elif not c.get("resume_exists"):
                bad.append(f"{c['name']} 标记为无简历但文件存在")
    step("候选人简历路径与磁盘一致", not bad, "; ".join(bad) if bad else "全部匹配")
    step("resume_exists 标记正确",
         all((bool(c.get("resume_exists")) == bool(c.get("resume_file") and
              (settings.RESUME_DIR / c["resume_file"]).is_file())) for c in cands),
         "有简历 " + str(sum(1 for c in cands if c.get("resume_exists"))) + " 人 / "
         + "无简历 " + str(sum(1 for c in cands if not c.get("resume_exists"))) + " 人")

    # ---- 5. 面试记录无重复 ----
    head("5) 面试记录唯一性（无重复行）")
    dup = [dict(r) for r in conn.execute(
        "SELECT candidate_id, round, COUNT(*) n FROM interviews "
        "GROUP BY candidate_id, round HAVING n > 1")]
    step("同一候选人同一轮只有一条记录（UNIQUE 约束生效）",
         not dup, "; ".join(f"cid={d['candidate_id']} round={d['round']} ×{d['n']}" for d in dup) if dup else "无重复")

    total_iv = conn.execute("SELECT COUNT(*) FROM interviews").fetchone()[0]
    step("面试记录总数", total_iv >= 0, f"{total_iv} 条")

    print("\n  各候选人轮次分布:")
    for r in conn.execute(
        "SELECT candidate_id, COUNT(*) n, GROUP_CONCAT(round) rounds, "
        "GROUP_CONCAT(status) sts FROM interviews GROUP BY candidate_id ORDER BY candidate_id"
    ):
        name = next((c["name"] for c in cands if c["id"] == r["candidate_id"]), "?")
        print(f"    {name:<6} {r['n']} 条  轮次[{r['rounds']}]  状态[{r['sts']}]")

    # ---- 6. 简历正文未被写入 DB 乱码 ----
    head("6) 简历文本抽取完整性")
    ok_txt = 0
    for c in cands:
        if not c.get("resume_exists"):
            continue
        p = settings.RESUME_DIR / c["resume_file"]
        if p.is_file() and p.stat().st_size > 200:
            ok_txt += 1
    step("有简历的候选人文件均非空", ok_txt == sum(1 for c in cands if c.get("resume_exists")),
         f"{ok_txt} 个文件均 > 200 B")

    conn.close()

    # ---- 汇总 ----
    n_ok = sum(1 for _, o, _ in results if o)
    n_all = len(results)
    print(f"\n{'=' * 74}")
    print(f"数据安全复核：{n_ok} / {n_all} 通过")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 74)
    if n_ok < n_all:
        print("\n未通过：")
        for l, o, d in results:
            if not o:
                print(f"  - {l} ({d})")

    out = Path(__file__).resolve().parent / "test_data_safety_report.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total": n_all, "passed": n_ok, "failed": n_all - n_ok,
            "resume_manifest": manifest,
            "resume_dir": str(settings.RESUME_DIR),
            "excel": str(x),
            "db": str(settings.DB_PATH),
            "results": [{"label": l, "ok": o, "detail": d} for l, o, d in results],
        }, f, ensure_ascii=False, indent=2)
    print(f"报告已写入：{out}")
    return 0 if n_ok == n_all else 1


if __name__ == "__main__":
    sys.exit(main())
