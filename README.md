# 夢之隊 GM（NBA Dream Team GM）

一款接上**真實 NBA 數據**的球隊經營遊戲，做成可安裝到手機的網頁 App（PWA），部署在 Cloudflare Pages 上。你扮演總管（GM），簽人、交易、排先發、選戰術，帶著「夢之隊」在真實 30 隊聯盟裡打完例行賽、季後賽、拚總冠軍。

球員數據每天由 GitHub Actions 自動抓取更新，OVR、能力、身價都會隨真實數據變動。

---

## 玩法概觀

- **聯盟**：30 支真實 NBA 隊 ＋ 你的夢之隊，共 31 隊，分東西區。例行賽 58 場依勝率排名，前 6 直接晉級、7–10 名打 Play-in，之後系列賽打到分區冠軍再爭總冠軍。
- **球員**：約 420 名真實球員（達出賽門檻者），每人有得分、籃板、助攻、抄截、火鍋、命中率、防守值，以及**個人三分傾向（t3r）**與**造犯規傾向（ftr）**。
- **經營**：市場簽人、對真實隊交易、選秀/球星市場、身價每日行情（低買高賣賺陣容價值）、薪資帽。
- **排陣**：設定先發、一鍵最佳先發、賽前防守對位（可點兩列互換防守者）。
- **進攻戰術**（賽前選）：主打三分、主打內線、球給指定主將、團隊籃球、買犯製造罰球、跑轟加速。AI 對手也會依自己陣容選戰術，形成博弈與剋制。

## 逐球模擬引擎

你的每場比賽都是**真正逐回合擲骰**算出來的，而非隨機比分：

跳球 → 控球過半（可能被抄）→ 依使用率選出手者 → 傳導（可能被抄、記助攻）→ 出手型態（依個人三分傾向決定 2 分/3 分）→ 火鍋檢定（依對位防守者蓋帽能力）→ 犯規檢定（依個人造犯規傾向）→ 命中檢定（能力＋命中率−對位防守−三分難度−手感回歸）→ 籃板／二次進攻補籃 → 罰球，並全程追蹤上場時間、體力、犯規（含犯滿換人）。

由此衍生的功能：

- **觀戰重播**：比賽結果可逐球播報，附即時記分板與即時累計的雙方 box score。
- **賽後快報**：依當場數據自動生成多變化的新聞（逆轉、對飆、防守大戰、大三元、外線開火、火鍋鎮守、傷兵…）。
- **匯出文字**：每場比賽可輸出成純文字（含比分、戰術、防守對位、完整數據）並一鍵複製。

（整套引擎已用大量模擬對齊真實 NBA 的各項平均：得分、命中率、三分、罰球、籃板、助攻、抄截、火鍋、失誤、犯規。）

---

## 專案結構

```
nba-dream-gm/
├─ static/index.html          遊戲本體（單一檔案 HTML+JS，含逐球引擎與所有 UI）
├─ fetch_players.py           用 nba_api 抓真實球員數據 → 產出 players.json（與 players.db）
├─ build_static.py            讀 players.json → 建置 dist/（嵌入資料庫、manifest、sw、icons）
├─ ovr.py                     OVR（PIE＋排名曲線）、防守值、薪資估算公式
├─ database.py                sqlite 存取（players.db，備用）
├─ players.json               建置用的球員資料（由 fetch 產生、由每日 Action 更新）
├─ requirements.txt           Python 套件
├─ wrangler.toml              Cloudflare Pages 設定（[assets] directory = ./dist）
├─ .github/workflows/daily-update.yml   每日自動抓資料並提交（觸發自動部署）
└─ dist/                      建置輸出（.gitignore，Cloudflare 在雲端自行建置）
```

**資料來源**：球員場均數據、進階數據（PIE、防守效率）、位置皆來自 NBA 官方 stats 端點（透過 `nba_api`）。薪資用官方薪資對照或 OVR 反推（讓薪資帽機制運作）。三分傾向 `t3r = 三分出手/總出手`、造犯規傾向 `ftr = 罰球出手/總出手` 由抓取時計算。

---

## 部署架構（Cloudflare Pages）

前端是純靜態網站：`build_static.py` 把 `players.json` 嵌進 `static/index.html`，輸出到 `dist/`，Cloudflare Pages 以 `dist/` 為網站內容部署。

- **來源監看**：Cloudflare 監看 GitHub repo，任何 push 都會自動重新 build（跑 `build_static.py`）+ 部署。
- **每日自動更新**：`.github/workflows/daily-update.yml` 每天（UTC 15:00／台灣 23:00）跑 `fetch_players.py`，若資料有變就把 `players.json`／`players.db` commit 回 repo → 觸發 Cloudflare 重建 → 遊戲數據更新。資料沒變（例如休賽期）就自動跳過，不白部署。
- **手機遊玩**：直接用 Cloudflare Pages 的網址開，可用瀏覽器「加入主畫面」做成 App 圖示。存檔存在手機瀏覽器的 localStorage，重新部署不會清除進度。

> 注意：新選進來的 NBA 新秀要等他們**打過足夠場次**（≥15 場、場均 ≥10 分鐘）且**新賽季開打**後，才會被抓取納入名單（資料來源是實際出賽數據）。

---

## 本機開發流程

需要 Python 3.10+（`pip install -r requirements.txt`）。

**改遊戲**：直接編輯 `static/index.html`（遊戲全在這一個檔）。本機預覽：

```bash
python build_static.py       # 讀 players.json → 產生 dist/
# 用瀏覽器打開 dist/index.html，或起個本機伺服器：
python -m http.server -d dist 8000   # 然後開 http://localhost:8000
```

**更新真實數據**（需網路，會呼叫 nba_api）：

```bash
python fetch_players.py --real-salary     # 產出 players.json（約 450 名）
python fetch_players.py --top 300         # 只抓前 300 名
```

`fetch_players.py` 會用 `current_season()` 自動判斷賽季（10 月後才算新賽季）。

> ⚠️ 抓取禮儀：腳本每次請求間有延遲，勿改短或高頻重複執行，以免 IP 被 NBA 端點暫時封鎖。失敗多為暫時性，過幾分鐘再試。

**部署**：把改動 push 到 GitHub，Cloudflare 會自動重建部署。

```bash
python build_static.py
git add -A
git commit -m "..."
git pull --rebase
git push
```

---

## 調整平衡 / 數值

- **逐球引擎與戰術**：在 `static/index.html` 的 `trip()`、`simGameDetailed()`、`usageW()`、`TACTICS`、`aiTactic()`。命中率、犯規率、造犯規、三分傾向、換人、體力、戰術修正等常數都在這裡。
- **OVR／防守值／薪資**：在 `ovr.py`（`composite_score`、`ovr_from_rank`、`defense_rating`）與 `fetch_players.py`。
- **抓取門檻**：`fetch_players.py` 的 `MIN_GAMES`、`MIN_MPG`、`DEFAULT_TOP`。

調數值後，建議用獨立 Node 腳本跑大量模擬驗證平衡，再 build 部署。

---

## 常見問題

**手機看不到最新版？** PWA 有快取，把 App 完全關掉再開（必要時兩次）讓 Service Worker 更新。標題列的「更新於 時間」可確認是否為最新建置。

**Cloudflare 沒看到每天部署？** 更新只在「資料有變」時才提交、才觸發部署；休賽期數據不動屬正常。要確認排程有跑，看 GitHub → Actions 的執行紀錄，或按「Run workflow」手動觸發。

**新賽季換季？** 交給 `current_season()` 自動處理（10 月起切到新賽季）；無需手動改。

**存檔會不會因更新消失？** 不會。進度存在手機瀏覽器 localStorage，部署新版只更新程式與數據，不動存檔。
