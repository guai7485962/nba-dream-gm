# NBA Dream Team GM 專案狀態

最後更新：2026-07-17（Asia/Taipei）

## 目前狀態

- 分支：`main`
- 遊戲主程式：`static/index.html`
- 共用 Mobile UI Lab 預覽：`http://127.0.0.1:8000/`

## 最近工作

- 校正 9 位傳奇球星的 NBA player ID，讓官方頭像能顯示正確球員；舊存檔會在 `load()` 時依姓名自動回填。
- 球星市場卡片把「開價年薪」與「市場身價」改為相鄰雙欄比較，並保留省下、溢價或價格合理提示。

## 驗證

- `verify.ps1`：建置成功，JavaScript 語法檢查通過。
- `npm.cmd run ui:shot -- nba`：390×844、412×915、430×932 共 12 張截圖；`report.json` 為 0 errors、0 warnings，已逐張檢查價格比較區塊無截斷或溢位。
- 9 個校正後的 NBA 官方頭像網址皆回應 HTTP 200。
- Codex in-app Browser 當次沒有可用瀏覽器實例；互動檢查未執行，以 Mobile UI Lab 實際渲染結果作為視覺證據。
