# NBA Dream Team GM 專案狀態

最後更新：2026-07-17（Asia/Taipei）

## 目前狀態

- 分支：`main`
- 遊戲主程式：`static/index.html`
- 共用 Mobile UI Lab 預覽：`http://127.0.0.1:8000/`

## 最近工作

- Jason Kidd 的 NBA `latest` 頭像其實是灰色占位圖；改以 ESPN 彩色球員照覆寫，NBA 圖保留為載入失敗備援。
- 校正 9 位傳奇球星的 NBA player ID，讓官方頭像能顯示正確球員；舊存檔會在 `load()` 時依姓名自動回填。
- 球星市場卡片把「開價年薪」與「市場身價」改為相鄰雙欄比較，並保留省下、溢價或價格合理提示。

## 驗證

- `verify.ps1`：建置成功，JavaScript 語法檢查通過。
- `npm.cmd run ui:shot -- nba`：2026-07-17 08:48 重跑 390×844、412×915、430×932 共 12 張截圖；`report.json` 為 0 errors、0 warnings，已逐張檢查無排版回歸。
- Jason Kidd ESPN 彩色頭像網址回應 HTTP 200，已與 NBA 灰色占位圖並排目視確認。
- 9 個校正後的 NBA 官方頭像網址皆回應 HTTP 200。
- Codex in-app Browser 當次沒有可用瀏覽器實例；互動檢查未執行，以 Mobile UI Lab 實際渲染結果作為視覺證據。

## 最近部署

- 最新功能 commit：`9074ac8`（改用 Jason Kidd 彩色頭像）
- Cloudflare Workers Builds：`completed / success`
- 正式網址：`https://nba-dream-gm.guai7485962.workers.dev/`
- 線上確認：正式 HTML 已包含 ESPN Jason Kidd `429.png` 彩色頭像覆寫，頁面更新於 2026-07-17 09:56。

## 2026-07-24 季後賽市場與釋出防誤觸

- 季後賽期間可照常簽下球星市場與自由市場球員；名單上限與薪資帽規則仍照常檢查。
- 球員釋出改為兩層確認：第一層說明影響，第二層才提供最終釋出按鈕；任一步都能取消。
- 最終釋出前會再次檢查球員仍存在，避免無效 id 誤刪名單最後一人。
- 驗證：`verify.ps1` 通過；Mobile UI Lab 產生 12 張三種手機尺寸截圖，`report.json` 為 0 errors / 0 warnings。
- 實際互動驗證：取消第二層時球員保留；走完兩層後才移至自由市場。快速模擬進入季後賽後，球星市場簽約按鈕維持啟用並進入一般名單／薪資檢查，不再出現季後賽鎖定。
