"""
fetch_players.py — 用 nba_api 抓取真實 NBA 球員場均數據，寫入資料庫

資料來源：
  - 球員數據：NBA 官方 stats 端點（nba_api，免費、免金鑰）
  - 球員位置：NBA PlayerIndex 端點（真實位置，比數據推斷準確）
  - 球員薪資：Basketball Reference 合約頁面（爬蟲，失敗自動 fallback）

執行方式（在專案資料夾下）：
    python fetch_players.py                  # 真實位置 + OVR 反推薪資
    python fetch_players.py --real-salary    # 真實位置 + 真實薪資（需網路）
    python fetch_players.py --top 80         # 只抓前 80 名

⚠️ 抓取禮儀：本腳本在每次請求之間加了延遲，請勿高頻重複執行。
"""
import argparse
import time
import sys
import unicodedata
from datetime import datetime

import database as db
from ovr import calc_ovr, estimate_salary, composite_score, ovr_from_rank, defense_rating

REQUEST_DELAY = 0.6
MIN_GAMES = 15     # 至少 15 場，濾掉小樣本（避免深板凳因效率虛高而被高估）
MIN_MPG = 10       # 每場至少 10 分鐘，排除只打 garbage time 的球員
DEFAULT_TOP = 450  # 30 隊 × 約 15 人，讓每隊有真實深度


def current_season():
    """自動回傳目前 NBA 球季字串（NBA 球季 10 月開打、跨年）。例：2025-26"""
    now = datetime.now()
    start = now.year if now.month >= 10 else now.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


SEASON = current_season()


# ─── 1. 球員場均數據 ────────────────────────────────────────────────

def fetch_league_averages(season):
    """抓全聯盟球員的本季場均數據。回傳 list of dict。"""
    try:
        from nba_api.stats.endpoints import leaguedashplayerstats
    except ImportError:
        print("✗ 找不到 nba_api 套件。請先執行： pip install -r requirements.txt")
        sys.exit(1)

    def _fetch(s):
        print(f"正在抓取 {s} 球季的聯盟球員數據……（首次可能要幾秒）")
        resp = leaguedashplayerstats.LeagueDashPlayerStats(
            season=s,
            season_type_all_star="Regular Season",
            per_mode_detailed="PerGame",
            timeout=30,
        )
        return resp.get_normalized_dict()["LeagueDashPlayerStats"]

    try:
        rows = _fetch(season)
        # 新球季剛開打、達標人數太少 → 自動退回上一季（資料較完整）
        enough = sum(1 for r in rows if r.get("GP", 0) >= MIN_GAMES)
        if enough < 100:
            start = int(season[:4])
            prev = f"{start - 1}-{str(start)[-2:]}"
            print(f"  {season} 球季樣本不足（僅 {enough} 人達 {MIN_GAMES} 場），改抓 {prev}")
            time.sleep(REQUEST_DELAY)
            rows = _fetch(prev)
    except Exception as e:
        print(f"✗ 抓取失敗：{e}")
        print("  可能原因：沒有網路、NBA 伺服器暫時拒絕、或球季字串不對。稍後再試。")
        sys.exit(1)

    time.sleep(REQUEST_DELAY)
    return rows


def fetch_advanced(season):
    """抓進階數據裡的 PIE（影響力）與 DEF_RATING（防守效率），
    回傳 {player_id: {"pie": pie, "dr": def_rating}}。失敗回空 dict。"""
    try:
        from nba_api.stats.endpoints import leaguedashplayerstats
        print("  正在取得進階數據（PIE 影響力 + DEF_RATING 防守）……")
        resp = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            season_type_all_star="Regular Season",
            per_mode_detailed="PerGame",
            measure_type_detailed_defense="Advanced",
            timeout=30,
        )
        rows = resp.get_normalized_dict()["LeagueDashPlayerStats"]
        time.sleep(REQUEST_DELAY)
        adv = {r["PLAYER_ID"]: {"pie": r.get("PIE", 0), "dr": r.get("DEF_RATING", 0)} for r in rows}
        print(f"  取得 {len(adv)} 名球員的進階數據 ✓")
        return adv
    except Exception as e:
        print(f"  ⚠ 進階數據抓取失敗：{e}（改用純場均排名、防守用抄阻估算）")
        return {}


# ─── 2. 球員位置（PlayerIndex 真實位置）────────────────────────────

def fetch_positions_playerindex(season):
    """用 PlayerIndex 端點取得真實位置（單次 API 呼叫）。
    回傳 {player_id: pos_code}，pos_code 為 PG/SG/SF/PF/C。
    失敗時回傳空字典，main() 會 fallback 到數據推斷。"""
    try:
        from nba_api.stats.endpoints import playerindex
        print("  正在取得球員位置資料（PlayerIndex）……")
        # PlayerIndex 在 nba_api 1.11+ 不接受 season/active 參數，直接呼叫
        resp = playerindex.PlayerIndex(timeout=30)
        data = resp.get_normalized_dict()
        # 找到有資料的第一個 key
        rows = None
        for key in ("PlayerIndex", "PlayerIndexNew", "players"):
            if key in data and data[key]:
                rows = data[key]
                break
        if not rows and data:
            rows = next((v for v in data.values() if v), None)
        if not rows:
            raise ValueError("回傳資料是空的")

        # 印出第一筆的欄位名稱，方便除錯
        if rows:
            sample_keys = list(rows[0].keys())
            pid_key = next((k for k in sample_keys if "ID" in k), None)
            pos_key = next((k for k in sample_keys if "POS" in k or k == "POSITION"), None)
            if not pid_key or not pos_key:
                print(f"  ⚠ 找不到 ID/位置欄位。可用欄位：{sample_keys}")
                return {}

        pos_map = {}
        for r in rows:
            pid = r.get(pid_key)
            pos_raw = (r.get(pos_key) or "").strip()
            if pid:
                pos_map[int(pid)] = _normalize_pos(pos_raw)

        time.sleep(REQUEST_DELAY)
        print(f"  取得 {len(pos_map)} 名球員的位置資料 ✓")
        return pos_map
    except Exception as e:
        print(f"  ⚠ PlayerIndex 取位置失敗：{e}")
        print("    改用數據推斷（仍可運作，但位置準確度較低）")
        return {}


def _normalize_pos(pos_raw):
    """將 NBA 位置字串標準化為 PG/SG/SF/PF/C，或回傳 None（讓數據推斷接手）。

    NBA 常見格式：G, F, C, G-F, F-G, F-C, C-F,
                  Guard, Forward, Center,
                  Point Guard, Shooting Guard, Small Forward, Power Forward
    """
    mapping = {
        "POINT GUARD": "PG",   "SHOOTING GUARD": "SG",
        "SMALL FORWARD": "SF", "POWER FORWARD": "PF",
        "CENTER": "C",
        "PG": "PG", "SG": "SG", "SF": "SF", "PF": "PF", "C": "C",
        "G": "G",    # 待數據微調：可能是 PG 或 SG
        "F": "F",    # 待數據微調：可能是 SF 或 PF
        "G-F": "SG", "F-G": "SF",
        # F-C 刻意不映射，讓 _stats_guess 用數據判斷
        # （避免把 Wembanyama 等蓋帽中鋒錯判為 PF）
        "C-F": "C",
    }
    return mapping.get(pos_raw.upper(), None)


# 手動位置修正：NBA 官方常把「組織前鋒」等球員列成 F/G-F，數據也難推回真正位置。
# 這份清單對知名球員強制指定位置（依姓名，含去變音符號比對）。可自行增補。
POSITION_OVERRIDE = {
    "Stephen Curry": "PG",
    "Luka Doncic": "PG",
    "LeBron James": "SF",
    "Ben Simmons": "PG",
    "Josh Giddey": "PG",
    "Nikola Jokic": "C",
    "Giannis Antetokounmpo": "PF",
    "Zion Williamson": "PF",
}


def resolve_position(pid, pos_map, row):
    """合併 手動修正 + PlayerIndex 位置 + 場上數據，得出最終 5 位置之一。"""
    name_plain = _strip_accents((row.get("PLAYER_NAME") or "").lower())
    for k, v in POSITION_OVERRIDE.items():
        if _strip_accents(k.lower()) == name_plain:
            return v
    base = pos_map.get(pid)

    if base is None:
        # PlayerIndex 沒拿到 → 純數據推斷
        return _stats_guess(row)

    if base == "G":
        # 控衛 vs 得分後衛：助攻是關鍵
        return "PG" if row.get("AST", 0) >= 5.5 else "SG"

    if base == "F":
        # 先判斷是否夠格打中鋒，再分大小前鋒
        reb, blk = row.get("REB", 0), row.get("BLK", 0)
        if blk >= 2.5 or (blk >= 1.5 and reb >= 9.5):
            return "C"   # Wembanyama 類型：蓋帽極多的前鋒中鋒
        return "PF" if (reb >= 7.0 or blk >= 1.0) else "SF"  # 降低門檻修正 Zion

    return base  # PG/SG/SF/PF/C 已明確，直接用


# ─── 真實三分/罰球命中率（給引擎的射手模型；一律存 0-1 小數）──────

# 位置罰球後備（對齊 static/index.html 引擎 EST_FT）
_POS_FT = {"PG": 0.80, "SG": 0.79, "SF": 0.76, "PF": 0.71, "C": 0.65}


def resolve_ft(row, pos):
    """回傳真實罰球命中率（0-1）。造罰球極少、樣本不足時退回位置估計。"""
    ftp = row.get("FT_PCT")
    fta = row.get("FTA", 0) or 0
    if ftp is not None and fta >= 1.0:      # 每場至少 1 次罰球才採用真實值
        return round(float(ftp), 3)
    return _POS_FT.get(pos, 0.75)


def resolve_p3(row, fg_pct100):
    """回傳真實三分命中率（0-1）。三分出手極少時退回依 FG%/出手傾向的合理低值，
    避免把不投三分者的 0% 直接送進引擎導致射手不投。"""
    p3 = row.get("FG3_PCT")
    fg3a = row.get("FG3A", 0) or 0
    if p3 is not None and fg3a >= 0.8:       # 每場至少 0.8 次三分出手才採用真實值
        return round(float(p3), 3)
    # 幾乎不投三分（多為中鋒）→ 時代合理低值
    if fg3a < 0.2:
        return 0.20
    # 出手偏少 → 以 FG% 與聯盟平均估
    v = 0.30 + max(0.0, (fg_pct100 - 45)) * 0.002
    return round(min(0.360, max(0.28, v)), 3)


def _stats_guess(row):
    """純數據推斷位置（PlayerIndex 失敗時的 fallback）。"""
    reb, ast, blk = row.get("REB", 0), row.get("AST", 0), row.get("BLK", 0)
    if blk >= 1.2 and reb >= 8:
        return "C"
    if reb >= 7:
        return "PF"
    if ast >= 6:
        return "PG"
    if ast >= 4:
        return "SG"
    return "SF"


# ─── 3. 真實薪資（Basketball Reference 爬蟲）──────────────────────

def fetch_real_salaries():
    """從 Basketball Reference 爬取真實薪資。
    回傳 {name_lower: salary_millions}。失敗時回傳空字典。"""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        print("  ⚠ 缺少 beautifulsoup4，請執行 pip install -r requirements.txt")
        return {}

    url = "https://www.basketball-reference.com/contracts/players.html"
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept-Language": "en-US,en;q=0.9",
    }
    print("  正在從 Basketball Reference 抓取真實薪資……")
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠ Basketball Reference 無法連線：{e}")
        print("    改用 OVR 反推薪資")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"id": "player-contracts"})
    if not table:
        print("  ⚠ 找不到薪資表格（頁面結構可能已更新）")
        return {}

    sal_map = {}
    for tr in table.find("tbody").find_all("tr"):
        if "thead" in (tr.get("class") or []):
            continue
        name_td = tr.find("td", {"data-stat": "player"})
        sal_td  = tr.find("td", {"data-stat": "y1"})   # 當季薪資
        if not name_td or not sal_td:
            continue
        name    = name_td.get_text(strip=True)
        sal_str = sal_td.get_text(strip=True).replace("$", "").replace(",", "")
        if not sal_str:
            continue
        try:
            sal_map[name.lower()] = round(int(sal_str) / 1_000_000, 1)
        except ValueError:
            continue

    print(f"  取得 {len(sal_map)} 名球員的真實薪資 ✓")
    return sal_map


def _strip_accents(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def lookup_salary(player_name, sal_map):
    """在薪資字典裡找對應球員（支援 Unicode 變音符號模糊比對）。"""
    if not sal_map:
        return None
    name_lo = player_name.lower()
    if name_lo in sal_map:
        return sal_map[name_lo]
    # 去掉變音符號再比對（Dončić → Doncic）
    plain = _strip_accents(name_lo)
    for k, v in sal_map.items():
        if _strip_accents(k) == plain:
            return v
    return None


# ─── 4. 主程式 ─────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="抓取 NBA 球員數據並寫入資料庫")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP,
                    help=f"抓取 OVR 前幾名球員（預設 {DEFAULT_TOP}）")
    ap.add_argument("--season", default=SEASON,
                    help="球季，例如 2024-25")
    ap.add_argument("--real-salary", action="store_true",
                    help="從 Basketball Reference 抓真實薪資（需要網路）")
    args = ap.parse_args()

    db.init_db()

    # ── 抓數據 ──
    rows    = fetch_league_averages(args.season)
    print(f"取得 {len(rows)} 名球員原始資料")

    pos_map = fetch_positions_playerindex(args.season)
    adv_map = fetch_advanced(args.season)

    sal_map = {}
    if args.real_salary:
        sal_map = fetch_real_salaries()
        if not sal_map:
            print("  薪資抓取失敗，改用 OVR 反推")

    # ── 第一輪：算出每位球員的綜合影響力分數（場均 + PIE）──
    print("開始計算影響力分數、OVR 與薪資……")
    entries = []
    for r in rows:
        if r.get("GP", 0) < MIN_GAMES or r.get("MIN", 0) < MIN_MPG:
            continue
        pts = round(r.get("PTS", 0), 1)
        reb = round(r.get("REB", 0), 1)
        ast = round(r.get("AST", 0), 1)
        stl = round(r.get("STL", 0), 1)
        blk = round(r.get("BLK", 0), 1)
        fg  = round(r.get("FG_PCT", 0) * 100, 1)
        fga  = r.get("FGA", 0) or 0
        fg3a = r.get("FG3A", 0) or 0
        fta  = r.get("FTA", 0) or 0
        t3r = round(fg3a / fga, 3) if fga > 0 else 0      # 三分出手佔比（投不投三分的傾向）
        ftr = round(fta / fga, 3) if fga > 0 else 0       # 罰球出手 / 投籃出手（造犯規上罰球線的傾向）
        pid  = r["PLAYER_ID"]
        pos  = resolve_position(pid, pos_map, r)
        ft   = resolve_ft(r, pos)                          # 真實罰球命中率（0-1）
        p3   = resolve_p3(r, fg)                           # 真實三分命中率（0-1）
        adv  = adv_map.get(pid) or {}
        pie  = adv.get("pie")
        dr   = adv.get("dr") or 0
        entries.append({
            "player_id": pid,
            "name":   r["PLAYER_NAME"],
            "team":   r.get("TEAM_ABBREVIATION", ""),
            "pos":    pos,
            "pts": pts, "reb": reb, "ast": ast,
            "stl": stl, "blk": blk, "fg":  fg,
            "t3r": t3r, "ftr": ftr, "ft": ft, "p3": p3,
            "pie": round((pie * 100 if (pie is not None and pie < 1.5) else (pie or 0)), 1),
            "def_rating": round(dr, 1),
            "def_rtg": defense_rating(dr, blk, stl),
            "_score": composite_score(pts, reb, ast, stl, blk, fg, pie),
        })

    # ── 第二輪：依分數排名換算 OVR（曲線），取前 N 名 ──
    entries.sort(key=lambda e: e["_score"], reverse=True)
    entries = entries[:args.top]
    n = len(entries)
    real_sal_count = 0
    for i, e in enumerate(entries):
        e["ovr"] = ovr_from_rank(i, n)
        real_sal = lookup_salary(e["name"], sal_map)
        if real_sal is not None:
            e["salary"] = real_sal
            real_sal_count += 1
        else:
            e["salary"] = estimate_salary(e["ovr"])
        del e["_score"]

    processed = entries

    db.clear_players()  # 先清空舊資料，只留本次的 450 名，避免過時球員殘留
    for p in processed:
        db.upsert_player(p)

    # 另外輸出 players.json：給 build_static 用（不依賴 sqlite，Cloudflare 才建得起來）
    import os as _os, json as _json
    _jpath = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "players.json")
    with open(_jpath, "w", encoding="utf-8") as _f:
        _json.dump(processed, _f, ensure_ascii=False)
    print(f"  已輸出 players.json（{len(processed)} 名，給靜態建置用）")

    # ── 摘要 ──
    print(f"\n✓ 完成！已寫入 {len(processed)} 名球員到資料庫。")
    if args.real_salary:
        real_in_top = sum(1 for p in processed if lookup_salary(p["name"], sal_map) is not None)
        print(f"  真實薪資配對：{real_in_top} 名 / OVR反推：{len(processed)-real_in_top} 名")
    print(f"  最強前 5 名：")
    for p in processed[:5]:
        print(f"    {p['name']:24s} {p['team']:4s} {p['pos']:2s}  "
              f"OVR {p['ovr']}  防守{p['def_rtg']}  ${p['salary']}M")
    print(f"  防守力前 5 名：")
    for p in sorted(processed, key=lambda x: -x["def_rtg"])[:5]:
        print(f"    {p['name']:24s} {p['team']:4s} {p['pos']:2s}  "
              f"防守{p['def_rtg']}  (DEF_RATING {p['def_rating']}, 阻{p['blk']} 抄{p['stl']})")
    print(f"  資料庫位置：{db.DB_PATH}")
    print(f"  現在可以啟動伺服器： python server.py")


if __name__ == "__main__":
    main()
