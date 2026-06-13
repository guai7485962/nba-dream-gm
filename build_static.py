"""
build_static.py — 產生靜態部署版本（可裝到手機的 PWA）

執行一次：
    python build_static.py

輸出 dist/ 資料夾，包含：
  index.html  — 嵌入 150 名真實球員數據，存檔改用 localStorage
  manifest.json — PWA 設定（App 名稱、主題色、icon 路徑）
  sw.js         — Service Worker（讓手機顯示「安裝到主畫面」）
  icon-192.png / icon-512.png — App 圖示

部署到 Netlify（最快，免費，不需 GitHub）：
  1. 跑完這個腳本
  2. 瀏覽器打開 https://app.netlify.com/drop
  3. 把 dist/ 資料夾拖進去
  4. 複製 Netlify 給你的網址

部署到 GitHub Pages：
  1. 建立 GitHub 帳號 + 新 Repository（Public）
  2. git init dist/ && git add . && git commit -m "deploy"
  3. git remote add origin https://github.com/你的帳號/nba-gm.git
  4. git push origin main
  5. 在 Repo → Settings → Pages → Source 選 main branch
"""
import sqlite3
import os
import json
import re
import struct
import zlib
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "players.db")
HTML_IN = os.path.join(BASE, "static", "index.html")
DIST    = os.path.join(BASE, "dist")


# ─── 讀取球員 ───────────────────────────────────────────────────────

def read_players():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM players ORDER BY ovr DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def format_db_js(players):
    """產生新的 let DB=[...]; 字串，格式與原本一致"""
    lines = []
    for p in players:
        row = [
            p["name"], p["pos"],
            p["pts"], p["reb"], p["ast"],
            p["stl"], p["blk"], p["fg"],
            p["salary"], p.get("team", ""),
        ]
        lines.append(json.dumps(row, ensure_ascii=False))
    return "let DB=[\n" + ",\n".join(lines) + "\n];"


# ─── 修改 HTML ──────────────────────────────────────────────────────

def patch_html(html, players):
    # 1. 嵌入真實球員數據
    new_db = format_db_js(players)
    html = re.sub(r'let DB=\[[\s\S]*?\];', new_db, html, count=1)

    # 2. 把 window.storage → localStorage
    html = html.replace(
        'async function save(){try{await window.storage.set("nba_gm_idle",JSON.stringify(S));}catch(e){}}',
        'async function save(){try{localStorage.setItem("nba_gm_idle",JSON.stringify(S));}catch(e){}}'
    )
    html = html.replace(
        'async function load(){try{const r=await window.storage.get("nba_gm_idle");if(r&&r.value)S=JSON.parse(r.value);}catch(e){S=null;}',
        'async function load(){try{const r=localStorage.getItem("nba_gm_idle");if(r)S=JSON.parse(r);}catch(e){S=null;}'
    )
    html = html.replace(
        'try{await window.storage.delete("nba_gm_idle");}catch(e){}',
        'try{localStorage.removeItem("nba_gm_idle");}catch(e){}'
    )

    # 3. loadPlayersFromAPI → 直接回傳成功（數據已內嵌）
    html = re.sub(
        r'async function loadPlayersFromAPI\(\)\{[\s\S]*?\n\}',
        'async function loadPlayersFromAPI(){return{ok:true,count:DB.length};}',
        html, count=1
    )

    # 4. 更新資料來源顯示文字
    html = html.replace(
        "if(api.ok)src.innerHTML='🟢 真實數據（'+api.count+' 名球員，來自本機伺服器）';",
        "if(api.ok)src.innerHTML='🟢 真實數據（'+api.count+' 名球員，已內嵌至此版本）';"
    )
    # 同步按鈕在靜態版不需要（沒有伺服器），改為提示
    html = html.replace(
        'else src.innerHTML=\'🟡 離線後備數據（未連到本機伺服器，使用內建 \'+DB.length+\' 名球員）\';',
        "else src.innerHTML='🟢 真實數據（'+DB.length+' 名球員，已內嵌至此版本）';"
    )

    # 5. 在 <head> 加入 PWA 所需 meta + manifest
    pwa_tags = (
        '<link rel="manifest" href="manifest.json">\n'
        '<meta name="theme-color" content="#101218">\n'
        '<meta name="apple-mobile-web-app-capable" content="yes">\n'
        '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n'
        '<meta name="apple-mobile-web-app-title" content="夢之隊GM">\n'
        '<link rel="apple-touch-icon" href="icon-192.png">\n'
    )
    html = html.replace('<meta charset="UTF-8">', '<meta charset="UTF-8">\n' + pwa_tags, 1)

    # 6. 在 </script> 前加入 Service Worker 註冊
    sw_js = (
        '\n// PWA：註冊 Service Worker（讓手機可安裝到主畫面）\n'
        'if("serviceWorker" in navigator){'
        'navigator.serviceWorker.register("sw.js").catch(()=>{});}\n'
    )
    html = html.replace('</script>\n</body>', sw_js + '</script>\n</body>', 1)

    return html


# ─── 產生圖示（用純 Python 內建模組，不依賴 Pillow）──────────────

def _make_png_bytes(size, r, g, b):
    """產生純色背景 + 簡單橘色籃球圓 的 PNG（不需要任何第三方套件）"""
    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    # 畫素資料：深色背景 + 中央橘色圓
    cx = cy = size // 2
    radius = int(size * 0.38)
    rows_data = bytearray()
    for y in range(size):
        rows_data.append(0)  # filter byte
        for x in range(size):
            dx, dy = x - cx, y - cy
            if dx * dx + dy * dy <= radius * radius:
                rows_data += bytes([0xD9, 0x8E, 0x3F])  # 橘色 #D98E3F
            else:
                rows_data += bytes([0x10, 0x12, 0x18])  # 深色背景 #101218

    compressed = zlib.compress(bytes(rows_data))

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', compressed)
    png += chunk(b'IEND', b'')
    return png


def make_icons():
    """嘗試用 Pillow 做精緻圖示；失敗則用內建方法做簡單圓形"""
    for sz in (192, 512):
        out = os.path.join(DIST, f"icon-{sz}.png")
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (sz, sz), (0x10, 0x12, 0x18))
            draw = ImageDraw.Draw(img)
            m = sz // 8
            draw.ellipse([m, m, sz - m, sz - m], fill=(0xD9, 0x8E, 0x3F))
            lw = max(2, sz // 40)
            draw.line([(sz // 2, m), (sz // 2, sz - m)], fill=(0xA3, 0x5F, 0x1F), width=lw)
            draw.line([(m, sz // 2), (sz - m, sz // 2)], fill=(0xA3, 0x5F, 0x1F), width=lw)
            for a in ((-30, 30), (150, 210)):
                draw.arc([m + sz//8, m, sz - m - sz//8, sz - m], a[0], a[1],
                         fill=(0xA3, 0x5F, 0x1F), width=lw)
            img.save(out)
        except ImportError:
            with open(out, "wb") as f:
                f.write(_make_png_bytes(sz, 0xD9, 0x8E, 0x3F))
        print(f"  ✓ icon-{sz}.png")


# ─── Service Worker ─────────────────────────────────────────────────

def make_sw_js(version):
    return f"""\
const CACHE = "nba-gm-{version}";
const ASSETS = ["./", "./index.html", "./manifest.json"];

self.addEventListener("install", e => {{
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
}});
self.addEventListener("activate", e => {{
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
}});
self.addEventListener("fetch", e => {{
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
}});
"""

MANIFEST = {
    "name": "夢之隊 GM",
    "short_name": "夢之隊GM",
    "description": "NBA 球隊經營放置遊戲",
    "start_url": "./",
    "scope": "./",
    "display": "standalone",
    "background_color": "#101218",
    "theme_color": "#101218",
    "orientation": "portrait-primary",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
}


# ─── 主程式 ─────────────────────────────────────────────────────────

def main():
    version = datetime.now().strftime("%Y%m%d%H%M")
    print("=" * 50)
    print(f"  NBA 夢之隊 GM — 靜態 PWA 建置（版本 {version}）")
    print("=" * 50)

    if not os.path.exists(DB_PATH):
        print("✗ 找不到 players.db！請先執行 python fetch_players.py")
        return

    os.makedirs(DIST, exist_ok=True)

    # 球員數據
    players = read_players()
    print(f"讀取 {len(players)} 名球員")

    # HTML
    with open(HTML_IN, "r", encoding="utf-8") as f:
        html = f.read()
    html = patch_html(html, players)
    out_html = os.path.join(DIST, "index.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    print("✓ dist/index.html（含真實球員數據）")

    # manifest
    with open(os.path.join(DIST, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(MANIFEST, f, ensure_ascii=False, indent=2)
    print("✓ dist/manifest.json")

    # service worker（版本號確保手機每次重開都拿到最新快取）
    with open(os.path.join(DIST, "sw.js"), "w", encoding="utf-8") as f:
        f.write(make_sw_js(version))
    print(f"✓ dist/sw.js（快取版本 {version}）")

    # icons
    print("正在產生圖示…")
    make_icons()

    print()
    print("✓ 完成！dist/ 資料夾已就緒")
    print()
    print("【最快部署方式：Netlify Drop（免費，不需 GitHub）】")
    print("  1. 用瀏覽器開啟：https://app.netlify.com/drop")
    print("  2. 把整個 dist/ 資料夾拖進去")
    print("  3. 複製 Netlify 給你的網址，手機開那個網址就能安裝！")
    print()
    print("【每次更新球員數據後，重新跑一次這個腳本再重新部署即可】")


if __name__ == "__main__":
    main()
