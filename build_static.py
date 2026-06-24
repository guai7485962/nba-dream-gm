"""
build_static.py — 產生靜態部署版本（可裝到手機的 PWA）
執行：python build_static.py → 輸出 dist/（index.html, manifest.json, sw.js, icons）
"""
import os
import json
import re
import struct
import zlib
from datetime import datetime, timezone, timedelta

TW = timezone(timedelta(hours=8))  # 台灣時間（CI 環境多為 UTC，固定換算成 +8）
BASE = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE, "players.json")
HTML_IN = os.path.join(BASE, "static", "index.html")
DIST = os.path.join(BASE, "dist")


def read_players():
    # 讀 players.json（不依賴 sqlite，Cloudflare 等精簡 Python 環境也能建置）
    with open(JSON_PATH, encoding="utf-8") as f:
        rows = json.load(f)
    rows.sort(key=lambda r: -(r.get("ovr") or 0))
    return rows


def format_db_js(players):
    lines = []
    for p in players:
        row = [p["name"], p["pos"], p["pts"], p["reb"], p["ast"],
               p["stl"], p["blk"], p["fg"], p["salary"], p.get("team", ""),
               p.get("ovr", 0), p.get("def_rtg", 60)]
        lines.append(json.dumps(row, ensure_ascii=False))
    return "let DB=[\n" + ",\n".join(lines) + "\n];"


def patch_html(html, players, build_date=""):
    new_db = format_db_js(players)
    html = re.sub(r'let DB=\[[\s\S]*?\];', new_db, html, count=1)
    html = html.replace(
        'async function save(){try{await window.storage.set("nba_gm_idle",JSON.stringify(S));}catch(e){}}',
        'async function save(){try{localStorage.setItem("nba_gm_idle",JSON.stringify(S));}catch(e){}}')
    html = html.replace(
        'async function load(){try{const r=await window.storage.get("nba_gm_idle");if(r&&r.value)S=JSON.parse(r.value);}catch(e){S=null;}',
        'async function load(){try{const r=localStorage.getItem("nba_gm_idle");if(r)S=JSON.parse(r);}catch(e){S=null;}')
    html = html.replace(
        'try{await window.storage.delete("nba_gm_idle");}catch(e){}',
        'try{localStorage.removeItem("nba_gm_idle");}catch(e){}')
    html = re.sub(r'async function loadPlayersFromAPI\(\)\{[\s\S]*?\n\}',
                  'async function loadPlayersFromAPI(){return{ok:true,count:DB.length};}', html, count=1)
    html = html.replace(
        "if(api.ok)src.innerHTML='🟢 真實數據（'+api.count+' 名球員，來自本機伺服器）';",
        "if(api.ok)src.innerHTML='🟢 真實數據（'+api.count+' 名球員・更新於 " + build_date + "）';")
    html = html.replace(
        "else src.innerHTML='🟡 離線後備數據（未連到本機伺服器，使用內建 '+DB.length+' 名球員）';",
        "else src.innerHTML='🟢 真實數據（'+DB.length+' 名球員・更新於 " + build_date + "）';")
    pwa_tags = ('<link rel="manifest" href="manifest.json">\n'
                '<meta name="theme-color" content="#101218">\n'
                '<meta name="apple-mobile-web-app-capable" content="yes">\n'
                '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n'
                '<meta name="apple-mobile-web-app-title" content="夢之隊GM">\n'
                '<link rel="apple-touch-icon" href="icon-192.png">\n')
    html = html.replace('<meta charset="UTF-8">', '<meta charset="UTF-8">\n' + pwa_tags, 1)
    sw_reg = ('\n// PWA：註冊 Service Worker\n'
              'if("serviceWorker" in navigator){navigator.serviceWorker.register("sw.js").catch(()=>{});}\n')
    html = html.replace('</script>\n</body>', sw_reg + '</script>\n</body>', 1)
    return html


def _make_png_bytes(size):
    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    cx = cy = size // 2
    radius = int(size * 0.38)
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            dx, dy = x - cx, y - cy
            rows += bytes([0xD9, 0x8E, 0x3F]) if dx*dx+dy*dy <= radius*radius else bytes([0x10, 0x12, 0x18])
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(rows)))
    png += chunk(b'IEND', b'')
    return png


def make_icons():
    for sz in (192, 512):
        out = os.path.join(DIST, f"icon-{sz}.png")
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (sz, sz), (0x10, 0x12, 0x18))
            d = ImageDraw.Draw(img)
            m = sz // 8
            d.ellipse([m, m, sz-m, sz-m], fill=(0xD9, 0x8E, 0x3F))
            lw = max(2, sz // 40)
            d.line([(sz//2, m), (sz//2, sz-m)], fill=(0xA3, 0x5F, 0x1F), width=lw)
            d.line([(m, sz//2), (sz-m, sz//2)], fill=(0xA3, 0x5F, 0x1F), width=lw)
            img.save(out)
        except ImportError:
            with open(out, "wb") as f:
                f.write(_make_png_bytes(sz))
        print(f"  icon-{sz}.png")


def make_sw_js(version):
    return ('const CACHE = "nba-gm-%s";\n'
            'const ASSETS = ["./", "./index.html", "./manifest.json"];\n'
            'self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS))); self.skipWaiting(); });\n'
            'self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))); self.clients.claim(); });\n'
            'self.addEventListener("fetch", e => { e.respondWith(caches.match(e.request).then(cached => cached || fetch(e.request))); });\n') % version


MANIFEST = {
    "name": "夢之隊 GM", "short_name": "夢之隊GM", "description": "NBA 球隊經營放置遊戲",
    "start_url": "./", "scope": "./", "display": "standalone",
    "background_color": "#101218", "theme_color": "#101218", "orientation": "portrait-primary",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
}


def main():
    now = datetime.now(TW)
    version = now.strftime("%Y%m%d%H%M")
    build_date = now.strftime("%Y-%m-%d %H:%M")
    print(f"NBA 夢之隊 GM — 建置版本 {version}")
    if not os.path.exists(JSON_PATH):
        print("找不到 players.json！請先執行 python fetch_players.py")
        return
    os.makedirs(DIST, exist_ok=True)
    players = read_players()
    print(f"讀取 {len(players)} 名球員")
    with open(HTML_IN, "r", encoding="utf-8") as f:
        html = f.read()
    html = patch_html(html, players, build_date)
    with open(os.path.join(DIST, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(DIST, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(MANIFEST, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DIST, "sw.js"), "w", encoding="utf-8") as f:
        f.write(make_sw_js(version))
    make_icons()
    print(f"完成！更新於 {build_date}（快取版本 {version}）")


if __name__ == "__main__":
    main()
