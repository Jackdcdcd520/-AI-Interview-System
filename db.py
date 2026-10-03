# -*- coding: utf-8 -*-
"""
SQLite 数据访问层（标准库 sqlite3，无额外依赖）

数据安全约定（题目硬性要求）：
  - 只 INSERT / UPDATE 系统自己的 interview.db；
  - 绝不 DROP / DELETE 原始数据；
  - 重复提交同一位候选人的同一轮次 → **UPDATE 当前记录**，不新增重复行
    （唯一约束 UNIQUE(candidate_id, round) + UPSERT 实现）。
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "config"))
import settings  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT    NOT NULL,
    student_no        TEXT,
    major             TEXT,
    grade             TEXT,
    position          TEXT,              -- 应聘岗位
    phone             TEXT,
    email             TEXT,
    resume_file       TEXT,              -- 简历文件名（相对 Resumes 目录）
    resume_path       TEXT,              -- 简历绝对路径
    resume_exists     INTEGER DEFAULT 0,
    resume_text       TEXT,              -- 抽取出的简历纯文本（缓存）
    resume_parsed     TEXT,              -- AI/规则抽取的结构化 JSON 字符串
    order_index       INTEGER,           -- 面试顺序（1 起）
    imported_at       TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    UNIQUE(student_no)
);

CREATE TABLE IF NOT EXISTS interviews (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id      INTEGER NOT NULL,
    round             INTEGER NOT NULL DEFAULT 1,   -- 第几轮面试
    interviewer       TEXT,                          -- 面试官
    scores            TEXT,                          -- JSON: {维度key: 分值}
    total_score       REAL,                          -- 加权总分
    comment           TEXT,                          -- 面试官评价
    ai_summary        TEXT,                          -- AI 总结
    ai_evaluation     TEXT,                          -- AI 智能评估（JSON）
    ai_provider       TEXT,
    status            TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress | completed
    started_at        TEXT,
    submitted_at      TEXT,
    updated_at        TEXT NOT NULL,
    FOREIGN KEY (candidate_id) REFERENCES candidates(id),
    UNIQUE(candidate_id, round)
);

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect() -> sqlite3.Connection:
    """建立连接（row_factory=Row，便于直接转 dict）。"""
    conn = sqlite3.connect(str(settings.DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """建表（幂等）。绝不删除已有数据。"""
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO app_meta(key, value) VALUES (?, ?)",
            ("schema_version", "1"),
        )
        conn.commit()
    finally:
        conn.close()


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ candidates
def upsert_candidate(c: dict[str, Any]) -> int:
    """按 student_no 或 name 幂等写入/更新候选人，返回 candidate_id。"""
    conn = connect()
    try:
        existing = None
        if c.get("student_no"):
            existing = conn.execute(
                "SELECT id FROM candidates WHERE student_no = ?", (c["student_no"],)
            ).fetchone()
        if existing is None and not c.get("student_no"):
            existing = conn.execute(
                "SELECT id FROM candidates WHERE name = ?", (c["name"],)
            ).fetchone()

        now = _now()
        payload = {
            "name": c.get("name"),
            "student_no": c.get("student_no"),
            "major": c.get("major"),
            "grade": c.get("grade"),
            "position": c.get("position"),
            "phone": c.get("phone"),
            "email": c.get("email"),
            "resume_file": c.get("resume_file"),
            "resume_path": c.get("resume_path"),
            "resume_exists": int(bool(c.get("resume_exists"))),
            "resume_text": c.get("resume_text"),
            "resume_parsed": c.get("resume_parsed"),
            "order_index": c.get("order_index"),
            "updated_at": now,
        }

        if existing:
            cid = existing["id"]
            sets = ", ".join(f"{k} = :{k}" for k in payload)
            conn.execute(f"UPDATE candidates SET {sets} WHERE id = :cid",
                         {**payload, "cid": cid})
        else:
            payload["imported_at"] = now
            cols = ", ".join(payload)
            ph = ", ".join(f":{k}" for k in payload)
            cur = conn.execute(f"INSERT INTO candidates ({cols}) VALUES ({ph})", payload)
            cid = cur.lastrowid
        conn.commit()
        return cid
    finally:
        conn.close()


def list_candidates() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT c.*,
                      (SELECT COUNT(*) FROM interviews i
                        WHERE i.candidate_id = c.id AND i.status = 'completed') AS completed_rounds,
                      (SELECT MAX(i.total_score) FROM interviews i
                        WHERE i.candidate_id = c.id AND i.status = 'completed') AS best_score
                 FROM candidates c
                ORDER BY COALESCE(c.order_index, 999999), c.id"""
        ).fetchall()
        return rows_to_dicts(rows)
    finally:
        conn.close()


def get_candidate(cid: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM candidates WHERE id = ?", (cid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_candidates() -> int:
    conn = connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    finally:
        conn.close()


# ------------------------------------------------------------------ interviews
def get_interview(candidate_id: int, round_no: int = 1) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM interviews WHERE candidate_id = ? AND round = ?",
            (candidate_id, round_no),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_interview_by_id(iid: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM interviews WHERE id = ?", (iid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_interview(payload: dict[str, Any]) -> int:
    """
    幂等保存一轮面试记录：
      UNIQUE(candidate_id, round) → 已存在则 UPDATE（题目要求：不无限生成重复记录）。
    """
    conn = connect()
    try:
        now = _now()
        cid = payload["candidate_id"]
        rnd = int(payload.get("round", 1))
        exists = conn.execute(
            "SELECT id FROM interviews WHERE candidate_id = ? AND round = ?", (cid, rnd)
        ).fetchone()

        data = {
            "interviewer": payload.get("interviewer"),
            "scores": payload.get("scores"),
            "total_score": payload.get("total_score"),
            "comment": payload.get("comment"),
            "ai_summary": payload.get("ai_summary"),
            "ai_evaluation": payload.get("ai_evaluation"),
            "ai_provider": payload.get("ai_provider"),
            "status": payload.get("status", "completed"),
            "updated_at": now,
        }
        if exists:
            iid = exists["id"]
            sets = ", ".join(f"{k} = :{k}" for k in data)
            extra = ""
            if data["status"] == "completed":
                extra = ", submitted_at = COALESCE(submitted_at, :now)"
            conn.execute(
                f"UPDATE interviews SET {sets}{extra} WHERE id = :iid",
                {**data, "iid": iid, "now": now},
            )
        else:
            data.update(
                {
                    "candidate_id": cid,
                    "round": rnd,
                    "started_at": payload.get("started_at") or now,
                    "submitted_at": now if data["status"] == "completed" else None,
                }
            )
            cols = ", ".join(data)
            ph = ", ".join(f":{k}" for k in data)
            cur = conn.execute(f"INSERT INTO interviews ({cols}) VALUES ({ph})", data)
            iid = cur.lastrowid
        conn.commit()
        return iid
    finally:
        conn.close()


def list_interviews(candidate_id: int) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM interviews WHERE candidate_id = ? ORDER BY round",
            (candidate_id,),
        ).fetchall()
        return rows_to_dicts(rows)
    finally:
        conn.close()


def list_interviewer_names() -> list[dict]:
    """
    所有出现过的面试官名单（去重），附带其打过的轮次数。
    供「面试官」下拉选择与权重设定使用；空/空白名不统计。
    只读查询，不改任何数据。
    """
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT TRIM(interviewer) AS interviewer, COUNT(*) AS rounds
                 FROM interviews
                WHERE interviewer IS NOT NULL AND TRIM(interviewer) <> ''
                GROUP BY TRIM(interviewer)
                ORDER BY rounds DESC, interviewer"""
        ).fetchall()
        return rows_to_dicts(rows)
    finally:
        conn.close()


def current_round_for(candidate_id: int) -> int:
    """
    该候选人**当前正在进行/应当进行的轮次**。

    语义（关键：面试官连点保存也只会有同一条记录）：
      1. 若存在 status='in_progress' 的轮次 → 就是这一轮（保存时 UPDATE 它）；
      2. 否则若已有完成的轮次 → 下一轮 = max(round) + 1；
      3. 否则（还没有任何记录）→ 第 1 轮。

    第 1 条是核心：进入面试页时 ensure_open_round() 已经把当前轮建成
    in_progress，所以之后不论保存多少次都会命中规则 1，轮次保持稳定。
    """
    conn = connect()
    try:
        open_row = conn.execute(
            "SELECT round FROM interviews WHERE candidate_id = ? "
            "AND status = 'in_progress' ORDER BY round DESC LIMIT 1",
            (candidate_id,),
        ).fetchone()
        if open_row is not None:
            return int(open_row["round"])

        max_row = conn.execute(
            "SELECT MAX(round) AS m FROM interviews WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if max_row is None or max_row["m"] is None:
            return 1
        return int(max_row["m"]) + 1
    finally:
        conn.close()


def next_round_for(candidate_id: int) -> int:
    """兼容旧调用：等价于 current_round_for。"""
    return current_round_for(candidate_id)


def ensure_open_round(candidate_id: int, round_no: int) -> int:
    """
    确保存在一个"开放中"的轮次记录（status='in_progress'），返回该轮的 round 号。

    作用：面试官进入面试页开始评分时，就把该轮建出来；
    之后每次点"保存"都是 UPDATE 同一条 → 彻底避免重复提交产生多行。
    若该轮已是 completed，则不覆盖，直接返回（由调用方决定是否开新一轮）。
    """
    conn = connect()
    try:
        existing = conn.execute(
            "SELECT id, status FROM interviews WHERE candidate_id = ? AND round = ?",
            (candidate_id, round_no),
        ).fetchone()
        if existing:
            return round_no

        now = _now()
        conn.execute(
            """INSERT INTO interviews
                 (candidate_id, round, status, started_at, updated_at)
               VALUES (?, ?, 'in_progress', ?, ?)""",
            (candidate_id, round_no, now, now),
        )
        conn.commit()
        return round_no
    finally:
        conn.close()


def advance_round(candidate_id: int) -> int:
    """
    显式开启新一轮：把当前轮标记 completed（若还开着），并创建下一轮。
    返回新的轮次号。
    """
    conn = connect()
    try:
        row = conn.execute(
            "SELECT round, status FROM interviews WHERE candidate_id = ? "
            "ORDER BY round DESC LIMIT 1",
            (candidate_id,),
        ).fetchone()
        now = _now()
        if row is None:
            new_round = 1
        elif row["status"] == "completed":
            new_round = int(row["round"]) + 1
        else:
            # 当前轮还开着 → 先收尾，再开新轮
            conn.execute(
                "UPDATE interviews SET status='completed', "
                "submitted_at = COALESCE(submitted_at, ?), updated_at = ? "
                "WHERE candidate_id = ? AND round = ?",
                (now, now, candidate_id, row["round"]),
            )
            new_round = int(row["round"]) + 1

        conn.execute(
            """INSERT INTO interviews
                 (candidate_id, round, status, started_at, updated_at)
               VALUES (?, ?, 'in_progress', ?, ?)
               ON CONFLICT(candidate_id, round) DO NOTHING""",
            (candidate_id, new_round, now, now),
        )
        conn.commit()
        return new_round
    finally:
        conn.close()


def update_candidate_order(cid: int, order_index: int) -> None:
    conn = connect()
    try:
        conn.execute(
            "UPDATE candidates SET order_index = ?, updated_at = ? WHERE id = ?",
            (order_index, _now(), cid),
        )
        conn.commit()
    finally:
        conn.close()


def update_candidate_parsed(cid: int, parsed_json: str, resume_text: str | None = None) -> None:
    conn = connect()
    try:
        if resume_text is None:
            conn.execute(
                "UPDATE candidates SET resume_parsed = ?, updated_at = ? WHERE id = ?",
                (parsed_json, _now(), cid),
            )
        else:
            conn.execute(
                "UPDATE candidates SET resume_parsed = ?, resume_text = ?, updated_at = ? WHERE id = ?",
                (parsed_json, resume_text, _now(), cid),
            )
        conn.commit()
    finally:
        conn.close()


def meta_get(key: str, default: str | None = None) -> str | None:
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def meta_set(key: str, value: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO app_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()
