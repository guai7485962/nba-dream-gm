"""
database.py — SQLite 資料庫的建立與存取
資料庫是單一檔案 players.db，零設定、跟著專案走。
存兩種資料：
  players          目前最新的球員數據（遊戲開局讀這個）
  player_history   每次抓取的歷史快照（之後可做「球員成長曲線」等功能）
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "players.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 讓查詢結果能用欄位名存取
    return conn


def init_db():
    """建立資料表（若不存在）。可重複呼叫，安全。"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            player_id   INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            team        TEXT,
            pos         TEXT,
            pts         REAL, reb REAL, ast REAL,
            stl         REAL, blk REAL, fg  REAL,
            pie         REAL,
            def_rating  REAL,
            def_rtg     REAL,
            ovr         INTEGER,
            salary      REAL,
            updated_at  TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS player_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id   INTEGER,
            name        TEXT,
            pts REAL, reb REAL, ast REAL, stl REAL, blk REAL, fg REAL,
            ovr INTEGER, salary REAL,
            snapshot_at TEXT
        )
    """)
    # 相容舊資料庫：缺欄位就補上（不必刪檔重建）
    cols = [r[1] for r in c.execute("PRAGMA table_info(players)").fetchall()]
    if "pie" not in cols:
        c.execute("ALTER TABLE players ADD COLUMN pie REAL")
    if "def_rating" not in cols:
        c.execute("ALTER TABLE players ADD COLUMN def_rating REAL")
    if "def_rtg" not in cols:
        c.execute("ALTER TABLE players ADD COLUMN def_rtg REAL")
    conn.commit()
    conn.close()


def upsert_player(p):
    """寫入或更新一名球員。p 是一個 dict。同時寫一筆歷史快照。"""
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    c.execute("""
        INSERT INTO players (player_id,name,team,pos,pts,reb,ast,stl,blk,fg,pie,def_rating,def_rtg,ovr,salary,updated_at)
        VALUES (:player_id,:name,:team,:pos,:pts,:reb,:ast,:stl,:blk,:fg,:pie,:def_rating,:def_rtg,:ovr,:salary,:now)
        ON CONFLICT(player_id) DO UPDATE SET
            name=:name, team=:team, pos=:pos,
            pts=:pts, reb=:reb, ast=:ast, stl=:stl, blk=:blk, fg=:fg,
            pie=:pie, def_rating=:def_rating, def_rtg=:def_rtg, ovr=:ovr, salary=:salary, updated_at=:now
    """, {**p, "now": now})
    c.execute("""
        INSERT INTO player_history (player_id,name,pts,reb,ast,stl,blk,fg,ovr,salary,snapshot_at)
        VALUES (:player_id,:name,:pts,:reb,:ast,:stl,:blk,:fg,:ovr,:salary,:now)
    """, {**p, "now": now})
    conn.commit()
    conn.close()


def clear_players():
    """清空 players 資料表（保留 player_history 快照），避免舊球員累積殘留。"""
    conn = get_conn()
    conn.execute("DELETE FROM players")
    conn.commit()
    conn.close()


def get_all_players():
    """回傳所有球員（依 OVR 由高到低），給 API 用。"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM players ORDER BY ovr DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_players():
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
    conn.close()
    return n


def last_update():
    conn = get_conn()
    row = conn.execute("SELECT MAX(updated_at) AS t FROM players").fetchone()
    conn.close()
    return row["t"] if row else None


if __name__ == "__main__":
    init_db()
    print(f"資料庫已就緒：{DB_PATH}")
    print(f"目前球員數：{count_players()}　最後更新：{last_update()}")
