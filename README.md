# 夢之隊 GM（NBA Dream Team GM）— 開發者 / Agent 指南

這份 README 寫給要接手改程式的人或 AI agent。目標是讓你在幾分鐘內掌握遊戲怎麼運作、程式關鍵在哪、改東西要動哪個函式，然後馬上開工。

> 一句話：接真實 NBA 數據的球隊經營放置遊戲，做成可裝手機的 PWA，部署在 Cloudflare Pages。玩家當 GM，簽人／交易／排先發／選戰術，比賽由**真正的逐回合模擬引擎**算出來。整個前端就是**一個 `static/index.html`**（HTML+CSS+JS 全塞在裡面）。

---

## 1. 最重要的心智模型（先讀這段）

1. **遊戲本體 = `static/index.html` 這一個檔**。所有 UI、狀態、逐球引擎、季後賽、市場都在裡面。要改玩法／數值／畫面，99% 是改這個檔。
2. **`build_static.py` 是建置器**：讀 `players.json`，把球員資料嵌進 `index.html` 的 `let DB=[...]`，輸出到 `dist/`。Cloudflare 部署 `dist/`。
3. **`players.json` 由 `fetch_players.py` 用 `nba_api` 產生**（真實球員場均＋進階數據）。`ovr.py` 負責 OVR／防守值／薪資公式。
4. **狀態 `S` 存在瀏覽器 localStorage**（key = `nba_gm_idle`）。改資料結構要同時改 `load()` 裡的遷移邏輯，否則舊存檔會壞。
5. **驗證方式**：改完 `python build_static.py` 成功即代表能建置；JS 語法可用 `node --check`（見第 9 節）。本機預覽用 `python -m http.server -d dist`。

---

## 2. 檔案結構與資料流

```
nba-dream-gm/
├─ static/index.html      ← 遊戲本體（單檔 HTML+CSS+JS，~2000 行）。改這裡。
├─ fetch_players.py       ← nba_api 抓數據 → players.json（+ players.db）
├─ ovr.py                 ← OVR / 防守值 / 薪資估算公式
├─ build_static.py        ← players.json + index.html → dist/
├─ database.py            ← sqlite 存取（備用）
├─ players.json           ← 建置用球員資料（每日 Action 更新）
├─ wrangler.toml          ← Cloudflare Pages 設定（[assets] directory = ./dist）
├─ .github/workflows/daily-update.yml  ← 每日抓資料並 commit（觸發部署）
└─ dist/                  ← 建置輸出（.gitignore，Cloudflare 雲端自建）
```

資料流：

```
fetch_players.py (nba_api) ──> players.json ──> build_static.py ──> dist/index.html ──> Cloudflare Pages
                                   │                                        │
                              ovr.py 公式                        嵌入 let DB=[...]（15 欄）
```

---

## 3. 建置器的三個關鍵改寫（改 index.html 前必懂）

`build_static.py` 的 `patch_html()` 會對 `static/index.html` 做正則改寫，產生 `dist/index.html`：

1. **嵌入資料庫**：`re.sub(r'let DB=\[[\s\S]*?\];', new_db, ...)`。
   ⚠️ 不要改 `let DB=[` 這個宣告樣式，否則建置抓不到。`const LEGENDS=[...]`（傳奇球員）是**另一個常數、不會被覆蓋**，所以傳奇資料直接寫死在 `index.html`。
2. **存檔 API 切換**：source 用 `window.storage.get/set/delete`（本機 dev server 用），build 後換成 `localStorage`。
   ⚠️ 改 `save()` / `load()` 時，這三行的字串必須跟 `patch_html()` 裡的 `.replace(...)` 目標字串**完全一致**，否則切換失敗。
3. **`loadPlayersFromAPI()`** 在 build 後被替換成直接回傳內建 DB（部署版沒有本機 API）。

其他：注入 PWA manifest／SW／icon；SW 快取版本 = 建置時間戳，所以每次 build 會讓手機 PWA 更新。

---

## 4. index.html 內部架構

檔案由上到下大致分區（用函式名 grep 最可靠，行號會漂移）：

### 4.1 資料與常數
- `let DB=[...]`：球員資料庫，每列 **15 欄**：
  `[name, pos, pts, reb, ast, stl, blk, fg, salary, team, ovr, def_rtg, player_id, t3r, ftr]`
  - `def_rtg`＝**防守能力分數，數字越高＝防守越強**（例：Wembanyama 92、Gobert 74、Trae Young 32）。⚠️ 這跟真實 NBA 的「防守效率（越低越好）」相反，改防守數值時務必記住。
  - `t3r`＝三分出手佔比（FG3A/FGA）、`ftr`＝造犯規傾向（FTA/FGA）。
- `const LEGENDS=[...]`：近 15 年＋2000 年代傳奇球員，格式同 DB 15 欄。傳奇模式時混入選秀市場。
- 核心常數（grep 得到）：`CAP=230`（薪資帽 M）、`MIN_R=8`/`MAX_R=15`（名單人數）、`REG_GAMES=58`、`PLAYOFF_TEAMS=16`、`DRAFT_OFFERS=10`、`DRAFT_SLOTS=[0,4,8,12,16,20]`、`SLOT_HOURS=[0,4,8,12,16,20]`（每天 6 場的開賽時間）、`NBA_TEAMS`（30 隊縮寫/分區）、`POSITIONS`、`POS_NUM`。
- 引擎用常數：`THREE_P`（各位置三分傾向預設）、`FOUL_P=0.06`、`HANDLE`/`SIZE`（各位置控球/體型）、`TACTICS`（戰術清單）。

### 4.2 球員物件（player object）
由 `mkPlayer()`（真實隊）、`clonePlayer()`（市場/選秀複製）、`genRoles()`（虛構角色，只給 AI 補深度）、`giftRoles()`（起手隨機真實普通球員）產生。欄位：
```
{id, name, pos, pts, reb, ast, stl, blk, fg, sal, team,
 ovr, drtg, pid, t3r, ftr,           // 能力
 sta(體力0-100), inj(傷停場數), yrs(合約年),
 pot(潛力), form(狀態-8~8), mv(身價), mvH(身價歷史)}
```
`id` 前綴：`p*`＝真實隊球員、`c*`＝複製（市場/選秀）、`g*`＝虛構角色。

### 4.3 遊戲狀態 `S`（存 localStorage）
在 `newGame()` 建立，重要欄位：
```
S = {
  team, abbr, conf('E'|'W'), season, phase, round, w, l,
  roster[], fa[](自由球員), ai[](30 隊，各有 roster/w/l/conf),
  starters[](先發 5 個 id), rest[](輪休球員 id — 完全不上場),
  tactic{t,target}, defByOpp{}(手動防守對位), schedule[][],
  draftBoard{slot,manualUsed,offers[]}, draft(選秀進行中),
  po(季後賽樹), resign(續約), gameHist[](近場逐球紀錄),
  log[], champs[], teamMvH[], legendMode(bool),
  nextAt(下一場時間戳), mday, lastSync, giftId, unseen
}
```
`phase`：`prep`（組隊）→ `regular`（例行賽）→ `playoffs`（季後賽）→ `offseason`（休賽期）。

### 4.4 存檔與遷移 —— `save()` / `load()`
- `save()`：`JSON.stringify(S)` 寫 localStorage。
- `load()`：讀回後跑**版本遷移**。⚠️ 新增 `S` 欄位時要在這裡補預設，例：`if(!Array.isArray(S.rest))S.rest=[];`。
- `load()` 內的 `_fix()` 會**依姓名用最新 `DB` 回填真實球員**能力（每日更新即時反映，薪資保留）；`_fixLeg()` 用最新 `LEGENDS` 回填傳奇。改了 DB/LEGENDS 數值後，舊存檔靠這兩個函式自動校正（涵蓋 roster/fa/ai/選秀池/選秀市場 offers）。

### 4.5 放置時鐘（遊戲怎麼「自己進行」）
- 底部 `setInterval(...,1000)` 每秒檢查：`marketCatchup()`（每日身價行情）、`draftCatchup()`（每 4 小時換一批選秀）、`tick()`（到 `nextAt` 就打球）。
- `tick()` → 迴圈補算所有到期時段：`recoverAll()` 回體力 → `playRegularRound()` 或 `playPlayoffSlot()` → `nextAt = nextSlot(nextAt)`。
- `nextSlot()` 依 `SLOT_HOURS` 算下一個開賽點（放置一整晚回來會一次補算多場）。

### 4.6 UI：render 與事件分派
- `render()`：依 `tab` 呼叫 `vTeam/vMarket/vTrade/vSched/vLeague`（或 `vStart`/`vOffseason`），把 HTML 字串塞進 `#main`。純字串模板，無框架。
- **所有互動走事件委派**：`document.addEventListener("click", ...)` 讀 `e.target.closest("[data-act]")`，用 `switch(a)` 分派（見檔尾）。要加新按鈕＝在 HTML 加 `data-act="xxx" data-id/arg=...`，再到 switch 加 `case "xxx"`。
- 球員列由 `pRow(p, btnHtml, showSta)` 產生（`.p-card` 直向卡片：資訊列 `.p-top` / 數據列 `.p-row2` / 動作列 `.p-actions`）。選秀市場另有 `offerRow()`（用 `.p-row` 橫向樣式，跟 `pRow` 各自獨立，別混用 class）。

---

## 5. 逐球模擬引擎（遊戲核心，最常調的地方）

玩家的每場比賽都是真的一回合一回合擲骰算的。入口 `simGameDetailed(ta, tb, meIdx)`。

### 5.1 引擎資料結構（與球員物件分離，很重要）
`engTeam(team,isMe,name)` 把球隊包成「比賽用隊伍」`T`：
```
T = {name, isMe, players[], live[](場上5人), qf(單節犯規), tac(戰術)}
```
每個上場球員是 **wrapper `w`**（不是球員物件）：
```
w = {p(球員物件), start, sta(本場體力副本), pf(犯規), fld(犯滿), secs, tmin,
     pts,reb,ast,stl,blk,fgm,fga,t3m,t3a,ftm,fta,tov, qp}
```
⚠️ **不變式**：比賽期間統計累加在 `w.*`（wrapper），**不要寫回球員物件 `w.p.*`**。體力也用 `w.sta` 副本。之前踩過的雷：把單場數據寫回球員物件會讓數值滾雪球。賽後只有 `applyFatigueInjury()` 用 `p.sta -= ...` 扣真正的體力。

### 5.2 一個回合 `trip(O, D)`（O 進攻、D 防守）
回傳 `{pts, evs:[...]}`（evs 是逐球播報事件）。流程：
1. `liveDefMap(O,D)` 先算對位（O 每個出手者 → 對應 D 防守者，套用玩家手動 `S.defByOpp`）。
2. **團隊犯規/非投籃犯規** 檢定 → 罰球（bonus 罰球分給使用率加權隨機球員，不是固定給控球者）。
3. **抄截** 檢定（依控球者 HANDLE 與防守者 stl）。
4. `usageW(w,tac)` 選出手者（戰術會改權重，見第 6 節）。
5. **傳導**（可能被抄、記助攻）。
6. **出手型態**：依 `t3r` 決定 2 分/3 分。
7. **火鍋** 檢定（依對位防守者 blk）。
8. **投籃犯規** 檢定（依 `ftr`）。
9. **命中** 檢定 `makeP`（見下）→ 命中得分 / 未中進籃板 → 二次進攻。
10. 罰球。全程累加 `w.secs`、`w.pf`、統計。

**命中率 `makeP`**（在 `trip()` 內，最常調的一行）大致：
```
基準 0.54 + (進攻能力-80)*0.0022 + (fg-47)*0.003
        - (對位防守者 drtg-62)*0.0022        ← drtg 越高扣越多（防守越強）
        - (三分?0.155:0) - 手感回歸 + 戰術修正
夾在 [0.28, 0.575]
```

### 5.3 換人 / 節奏
- `simGameDetailed` 內每節切成多個 possession，`QP` 控節奏（跑轟 +12%）。
- `subBench(T,q,margin)`：依上場時間比例輪換替補、犯滿（pf≥6）換下、末節追分回先發。
- `w.tmin` 由固定分配權重 `[37,35,34,32,30,16,14,12,10]` 決定各人目標上場時間。

### 5.4 賽後
- `applyFatigueInjury(team,isMe,win)`：先發 `-14` 體力、替補 `-8`；更新 `form`；約 1.8% 機率受傷。
- `recoverAll()`：每個時段所有球員 `+12` 體力；**輪休（`S.rest`）球員額外 `+10`**。
- `genRecap(L)`：依當場數據生成多變化賽後快報。`gameToText(L)`：匯出純文字（含比分/戰術/防守對位/box）。`watchGame(idx)`：逐球重播（只播關鍵動作）。

---

## 6. 進攻戰術系統

- `TACTICS` 陣列定義 7 種：`none/three/inside/feed/share/foul/run`（無/主打三分/主打內線/球給主將/團隊籃球/買犯/跑轟）。
- `usageW(w,tac)` 是戰術核心：`feed` 把指定球員使用率 ×2.1；`share` 壓平（次方 0.62）；`inside` 依位置加權（C×1.55…）；`three` 依 `t3r` 加權。
- `makeP` 內也有各戰術的命中修正；`trip()` 內 `inside` 提高火鍋/進攻籃板、`run` 提高失誤與節奏。
- `aiTactic(team)`：AI 依自己陣容自動選戰術，形成博弈。玩家的選擇存 `S.tactic = {t, target}`（feed 才有 target）。

---

## 7. 賽季 / 季後賽 / 市場

- **賽程**：`buildSchedule()` 圓桌雙循環（31 隊＝你＋30 真實隊），確保開季第一輪就有你的比賽。
- **例行賽**：`playRegularRound()` 只有你的比賽跑逐球引擎（`simGameDetailed`），其餘 29 隊用 `quickWin()` 快速判勝負（效能）。
- **季後賽**：`startPlayoffs()` 建東西區樹；`mkConfPO()`（Play-in 單場 target 1）、`buildBracket()`（七戰四勝 target 4）、`playSeriesGame()`/`advanceConf()`/`playPlayoffSlot()` 推進。結構在 `S.po`（`S.po.E/.W/.finals`）。對手偵測：`curOpponent()` → 例行賽 `nextOpponent()` / 季後賽 `playoffOpponent()`。
- **市場/選秀**：`rollDraftOffers()` 每批 10 人，OVR 越高越稀有（`STAR_BIAS`），有機率「跳樓價」；`S.legendMode` 時每名額約 12% 抽傳奇。`refreshDraft()`（免費手動刷新）、`draftCatchup()`（每 4 小時自動換）。
- **簽約/釋出/交易**：`sign()`（用 `ask` 當薪資）、`release()`、`evalTrade()`/`proposeTrade()`（只有玩家受薪資帽 `CAP` 限制）。`legalMe()` 決定能不能出賽（人數≥8、不超帽、健康≥5）。
- **身價/交易價值**：`mvBase(p)`（依 OVR/form）＝身價；`val(p)`＝交易價值（含 mv、非線性 OVR、扣薪資）。`marketTick()`/`marketCatchup()` 每日跳動身價。
- **輪休**：`togRest(id)` 切換 `S.rest`；`lineupOf(team,isMe)` 對「我方」排除輪休者；`isResting(id)` 判斷。輪休球員不上場 → 體力多回。

---

## 8. 「我想改 X → 動這裡」速查表

| 想做的事 | 改哪裡 |
|---|---|
| 調整命中率/比分高低 | `trip()` 內 `makeP`（基準 0.54、係數、上下限） |
| 調犯規/罰球太多太少 | `trip()` 的團隊犯規 `0.085`、投籃犯規 `0.06*ftr`、`FOUL_P`、`ftPct()` |
| 調三分頻率/命中 | `THREE_P`、出手型態判定、`makeP` 的 `-0.155` 三分難度 |
| 調體力消耗/回復 | `applyFatigueInjury`（-14/-8）、`recoverAll`（+12，輪休 +10）、`eff()` 體力曲線 |
| 調受傷率 | `applyFatigueInjury` 的 `Math.random()<0.018` |
| 調節奏/回合數 | `simGameDetailed` 的 `QP`、換人 `subBench` |
| 改/加戰術 | `TACTICS` 陣列 + `usageW()` + `makeP` 修正 + `aiTactic()` |
| 改戰力公式 | `power()`、`gameVal()`、`eff()` |
| 改 OVR/防守值/薪資公式 | `ovr.py`（`composite_score`/`ovr_from_rank`/`defense_rating`）＋ `fetch_players.py` |
| 改薪資帽/名單人數/賽季長度 | 常數 `CAP`/`MIN_R`/`MAX_R`/`REG_GAMES` |
| 改選秀出現機率/跳樓價 | `rollDraftOffers()`（`STAR_BIAS`、`bChance`、傳奇 12%） |
| 加/改傳奇球員 | `const LEGENDS=[...]`（15 欄，`def_rtg` 越高越強）；舊存檔靠 `load()` 的 `_fixLeg()` 自動校正 |
| 改起手陣容 | `newGame()`、`giftRoles()`（隨機真實普通球員）、`makeGiftStar()`（核心明星、已打折起薪） |
| 改交易 AI 接受條件 | `evalTrade()` 的 `gain`/`need` |
| 加新按鈕/互動 | HTML 加 `data-act="x"`，檔尾 `switch(a)` 加 `case "x"` |
| 改球員卡/市場列排版 | `pRow()`（球隊/自由球員，`.p-card`）、`offerRow()`（選秀市場，`.p-row`）＋ 上方 CSS |
| 改賽後快報/匯出/重播 | `genRecap()` / `gameToText()` / `watchGame()` |
| 加新 `S` 欄位 | `newGame()` 初始化 ＋ `load()` 遷移補預設 |

---

## 9. 本機開發 / 建置 / 部署

需要 Python 3.10+（`pip install -r requirements.txt`）。改遊戲只需編 `static/index.html`。

```bash
# 建置（讀 players.json → 產生 dist/）
python build_static.py

# 本機預覽
python -m http.server -d dist 8000   # 開 http://localhost:8000

# JS 語法驗證（可選）：抽出 <script> 內容跑 node --check
python - <<'PY'
h=open('static/index.html',encoding='utf-8').read()
i=h.index('<script>')+8; j=h.rindex('</script>')
open('/tmp/app.js','w',encoding='utf-8').write(h[i:j])
PY
node --check /tmp/app.js

# 更新真實數據（需網路，呼叫 nba_api）
python fetch_players.py --real-salary     # 產出 players.json（約 450 名）
python fetch_players.py --top 300         # 只抓前 300 名

# 部署（push 後 Cloudflare 自動重建 dist 並部署）
python build_static.py
git add -A
git commit -m "..."
git pull --rebase
git push
```

`fetch_players.py`：`current_season()` 自動判賽季（10 月後算新賽季）；門檻 `MIN_GAMES=15`、`MIN_MPG=10`、`DEFAULT_TOP=450`；計算 `t3r`/`ftr`；`--real-salary` 用官方薪資否則 OVR 反推。抓取有延遲禮儀，勿高頻重跑以免被 NBA 端點暫時封鎖。

**部署架構**：Cloudflare Pages 監看 repo，任何 push 自動跑 `build_static.py` + 部署 `dist/`。`.github/workflows/daily-update.yml` 每天（台灣 23:00）跑 `fetch_players.py`，資料有變才 commit → 觸發重建。存檔在手機 localStorage，重新部署不會清除。

---

## 10. 常踩的雷（invariants / gotchas）

1. **`def_rtg` 越高＝防守越好**（跟真實 NBA 防守效率相反）。改防守數值先確認方向。
2. **比賽統計只寫 wrapper `w.*`，不要寫回球員物件 `w.p.*`**，體力用 `w.sta` 副本；否則數值滾雪球。
3. **不要改 `let DB=[` 宣告樣式**，會讓 `build_static.py` 的正則抓不到。`LEGENDS` 是另一個常數、不受影響。
4. **改 `save()`/`load()` 的 storage 字串** 要同步 `build_static.py` 的 `.replace()` 目標，否則 dev↔build 的 localStorage 切換失敗。
5. **新增 `S` 欄位** 一定要在 `load()` 遷移補預設，並考慮舊存檔。
6. **改 DB/LEGENDS 數值後**，現有存檔靠 `load()` 的 `_fix()`/`_fixLeg()` 依姓名自動校正；新增傳奇欄位也走這裡。
7. **`pRow`（.p-card）與 `offerRow`（.p-row）用不同 class**，改排版別互相污染。
8. **手機看不到新版**＝ PWA 快取；完全關閉 App 再開（SW 快取版本＝建置時間戳）。標題列「更新於 時間」可確認建置版本。
