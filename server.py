"""
server.py — 本機 API 伺服器
功能：
  1. 提供 /api/players —— 遊戲開局時讀這個拿球員名單
  2. 提供 /api/status —— 查資料庫狀態（球員數、最後更新時間）
  3. 托管 static/index.html —— 直接用瀏覽器開遊戲

啟動方式（在專案資料夾下）：
    python server.py

啟動後：
  本機（這台 PC）開：     http://localhost:8000
  同網路的手機開：        http://<你的PC區網IP>:8000   （IP 用 ipconfig 查）

--host 0.0.0.0 代表「接受區網內任何裝置連線」，手機才連得到。
若只想自己這台電腦能連，把 host 改成 127.0.0.1。
"""
import os
import json
import sqlite3

from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

import database as db
from build_static import player_row

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE, "static")
JSON_PATH = os.path.join(BASE, "players.json")

app = FastAPI(title="NBA 夢之隊 GM 本機伺服器")


@app.get("/api/players")
def api_players():
    """回傳所有球員，格式對齊前端 DB 的 17 欄（含 ovr/t3r/ftr/ft/p3）。
    優先讀 players.json（欄位最完整，與靜態建置一致）；缺檔才退回 sqlite。"""
    # 首選：players.json（含真實 ft/p3、t3r、ovr 等完整欄位）
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, encoding="utf-8") as f:
                rows = json.load(f)
            rows.sort(key=lambda r: -(r.get("ovr") or 0))
            full = [player_row(p) for p in rows]
            return {"count": len(full), "players": full}
        except Exception:
            pass  # 讀取或解析失敗 → 退回 sqlite

    # 後備：sqlite（缺 t3r/ft/p3，player_row 會依位置後備，遊戲仍可玩）
    try:
        players = db.get_all_players()
    except sqlite3.OperationalError:
        return JSONResponse(
            {"error": "資料庫尚未建立，請先執行 python fetch_players.py"},
            status_code=503,
        )
    if not players:
        return JSONResponse(
            {"error": "資料庫是空的，請先執行 python fetch_players.py 抓取球員"},
            status_code=503,
        )
    full = [player_row(p) for p in players]
    return {"count": len(full), "players": full}


@app.get("/api/status")
def api_status():
    try:
        return {"players": db.count_players(), "last_update": db.last_update()}
    except sqlite3.OperationalError:
        return {"players": 0, "last_update": None}


@app.get("/")
def index():
    path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(path):
        return JSONResponse({"error": "找不到 static/index.html"}, status_code=404)
    return FileResponse(path)


# 托管 static 目錄下的其他靜態檔
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    print("=" * 48)
    print("  NBA 夢之隊 GM — 本機伺服器啟動中")
    print("=" * 48)
    try:
        n = db.count_players()
        print(f"  資料庫球員數：{n}")
        if n == 0:
            print("  ⚠ 資料庫是空的！請先在另一個視窗執行：")
            print("      python fetch_players.py")
    except Exception:
        print("  ⚠ 尚未建立資料庫，請先執行： python fetch_players.py")
    print()
    print("  這台電腦開：  http://localhost:8000")
    print("  手機開：      http://<你的PC區網IP>:8000   (用 ipconfig 查 IP)")
    print("  按 Ctrl+C 停止伺服器")
    print("=" * 48)
    uvicorn.run(app, host="0.0.0.0", port=8000)
