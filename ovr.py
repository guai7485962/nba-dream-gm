"""
ovr.py — 球員評分（OVR）與薪資反推
這裡的公式刻意和遊戲前端 (index.html 的 calcOvr) 保持一致，
這樣後端算出來的 OVR 和前端顯示的會是同一套標準。
薪資因為官方沒有 API，採「用 OVR 反推」的遊戲化做法。
"""


def calc_ovr(pts, reb, ast, stl, blk, fg):
    """舊版：把場均換算成 68–99。保留作為前端後備與相容用途。"""
    v = (38
         + pts * 1.05
         + reb * 0.82
         + ast * 0.95
         + stl * 1.7
         + blk * 1.7
         + (fg - 44) * 0.28)
    return max(68, min(99, round(v)))


def composite_score(pts, reb, ast, stl, blk, fg, pie=None):
    """綜合影響力分數：場均加權 + PIE（球員影響力估計）。
    這個分數只用來『排名』，OVR 由 ovr_from_rank 依排名換算，所以絕對數值不重要。
    PIE 能反映防守/組織/整體影響，修正純場均低估明星的問題。"""
    box = (pts * 1.0
           + reb * 0.7
           + ast * 1.0
           + stl * 2.0
           + blk * 1.8
           + (fg - 44) * 0.2)
    if pie is not None:
        # PIE 可能是 0.20（比例）或 20.0（百分比），統一成百分比尺度
        pie_pct = pie * 100 if pie < 1.5 else pie
        return box + pie_pct * 1.6
    return box


def ovr_from_rank(rank, n):
    """依『綜合分數排名』把球員映射到 58–99 的 OVR 曲線（rank 0 = 最強）。
    指數 < 1 讓頂端拉開：超巨 96–99、全明星 90–95、先發 80–88、輪替 72–80、板凳 58–71。"""
    if n <= 1:
        return 99
    pct = rank / (n - 1)          # 0（最強）→ 1（最弱）
    ovr = 99 - 41 * (pct ** 0.65)
    return max(58, min(99, round(ovr)))


def estimate_salary(ovr):
    """用 OVR 反推一個「看起來合理」的年薪（單位：百萬美元）。
    這不是真實薪資，而是讓薪資帽機制能運作的遊戲化數值。
    曲線設計（近似真實 NBA）：
      70→約 5M、76→約 12M、82→約 24M、88→約 38M、94→約 50M、99→約 58M
    """
    if ovr < 68:
        return 2.0
    # 線性基底 + 溫和的二次項，中段平滑、頂端拉開
    sal = (ovr - 67) * 1.15 + ((ovr - 67) ** 2) * 0.045
    sal = max(2.0, min(59.0, sal))
    return round(sal, 1)


def role_player_salary(ovr):
    """角色球員（OVR 68–76）的底薪區間，略低於反推值，模擬底薪合約。"""
    base = estimate_salary(ovr)
    return round(base * 0.75, 1)


if __name__ == "__main__":
    # 自我檢查：印出幾個代表性數值，確認曲線合理
    samples = [
        ("頂級 MVP 級", 29.6, 12.7, 10.2, 1.8, 0.6, 57.6),
        ("全明星級", 26.8, 8.7, 6.0, 1.1, 0.5, 45.2),
        ("先發級", 18.0, 5.0, 4.0, 1.0, 0.5, 47.0),
        ("角色球員", 8.0, 3.0, 1.5, 0.5, 0.3, 45.0),
    ]
    for name, *stats in samples:
        ovr = calc_ovr(*stats)
        print(f"{name:10s} OVR={ovr:2d}  反推年薪=${estimate_salary(ovr)}M")
