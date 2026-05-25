# GA4 → Claude.ai 週報自動化

每週一早上 08:00（台北時間），GitHub Actions 自動：
1. 從 GA4 抓上週 + 上上週數據
2. 組合成「給 Claude.ai 的完整 prompt」
3. 上傳到 Google Drive 指定資料夾（Markdown + Google Docs 兩種格式）

你週一一早只需要：**開 Drive → 點開 Doc → 全選複製 → 貼到 [claude.ai](https://claude.ai) → 送出 → 得到完整週報分析**

---

## 一、Google Drive 資料夾設定

### 1. 建立 Drive 資料夾並授權給 service account
1. 開 [Google Drive](https://drive.google.com/) → 新增資料夾，例如「GA4 週報」
2. 對資料夾**右鍵 → 共用**
3. 把 `ga4-claude-reporter@nifty-charter-497400-b4.iam.gserviceaccount.com` 加為**編輯者**
4. **取消勾選**「通知對方」
5. 點分享
6. 進入該資料夾，**複製網址最後那串 ID**：
   - 網址：`https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrSt`
   - Folder ID：`1AbCdEfGhIjKlMnOpQrSt`
   - **記下這個 ID**，等等要用

### 2. 啟用 Google Drive API
進入 [Cloud Console → Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com?project=nifty-charter-497400-b4)，點 **啟用**。

---

## 二、GitHub Repo 設定

### 1. 建立 Repo（Public）
1. 進入 [github.com](https://github.com)，登入或註冊
2. 右上角 **+ → New repository**
3. 名稱例如 `ga4-weekly-prompt`
4. 選 **Public**
5. 勾選 **Add a README file**
6. **Create repository**

### 2. 上傳本專案檔案
最簡單的方式：用網頁介面拖曳。
1. 在新 repo 點 **Add file → Upload files**
2. 把這個專案的所有檔案（含 `.github` 資料夾）拖進去
3. Commit

或用 git command line（若熟）：
```bash
git clone https://github.com/你的帳號/ga4-weekly-prompt.git
cd ga4-weekly-prompt
# 把專案檔複製進來
git add .
git commit -m "Initial setup"
git push
```

### 3. 設定 GitHub Secrets（**最關鍵的步驟**）

到 repo 頁面 → **Settings → Secrets and variables → Actions → New repository secret**

依序建立以下三個 secret：

| Secret Name | Value |
|---|---|
| `GA4_PROPERTY_ID` | `321311625` |
| `DRIVE_FOLDER_ID` | 上面取得的 Drive 資料夾 ID |
| `GCP_SERVICE_ACCOUNT_JSON` | 完整的 service account JSON 內容（見下方） |

**GCP_SERVICE_ACCOUNT_JSON 的填法**：
1. 開啟你電腦上的 `nifty-charter-497400-b4-2e062cabad9a.json`
2. **整個檔案內容複製貼上**到 secret 的 Value 欄位
3. 從 `{` 開頭到 `}` 結尾，包含所有換行
4. 點 **Add secret**

⚠️ Secret 一旦設好後就無法再讀取，只能覆寫。所以記得備份你的 JSON 檔。

---

## 三、測試與啟用

### 1. 手動測試一次
- repo 頁面 → **Actions** 分頁
- 左側點 **GA4 Weekly Report**
- 右側 **Run workflow → Run workflow** 按下去
- 等 1-2 分鐘看執行狀態
- 綠色勾勾 = 成功，紅色 X = 失敗（點進去看錯誤訊息）

### 2. 確認 Drive 有檔案
成功後到你的「GA4 週報」資料夾，會看到：
- `GA4_週報_Prompt_2026-XX-XX_to_2026-XX-XX.md` （Markdown 原檔）
- `GA4_週報_Prompt_2026-XX-XX_to_2026-XX-XX` （Google Docs）

### 3. 使用方式
1. 點開 Google Docs（或 .md）
2. **Ctrl+A 全選 → Ctrl+C 複製**
3. 開啟 [claude.ai](https://claude.ai)
4. **Ctrl+V 貼上 → 送出**
5. Claude 會根據 prompt 自動產出 6 個章節的完整分析報告

### 4. 自動排程已啟動
設定完之後，**每週一台北時間早上 08:00** GitHub 會自動跑這個流程，你週一進公司就有新報告等著。

---

## 四、客製化

### 改成日報 / 月報
編輯 `ga4_to_prompt.py` 開頭：
```python
REPORT_DAYS = 7   # 改成 1 = 日報、30 = 月報
```

再改 `.github/workflows/weekly.yml`：
```yaml
- cron: '0 0 * * *'   # 每天 (日報)
- cron: '0 0 1 * *'   # 每月 1 號 (月報)
```

[cron 表達式產生器](https://crontab.guru/) 可以幫你產生正確語法。

### 改分析重點
編輯 `ga4_to_prompt.py` 的 `build_prompt()` 函式，調整裡面的「報告風格要求」和章節結構。

### 改抓取的指標
編輯 `fetch_ga4_data()`，metrics 與 dimensions 對照表：
- [GA4 Dimensions & Metrics Explorer](https://ga-dev-tools.google/ga4/dimensions-metrics-explorer/)

---

## 五、安全性說明

- **Repo 設成 Public 是安全的**：所有敏感資訊（API key、service account JSON、property ID）都存在 GitHub Secrets，GitHub 會自動遮蔽，不會出現在程式碼或執行 log 裡
- Service account 只有 GA4 「檢視者」+ Drive 指定資料夾「編輯者」權限，影響範圍受限
- 若懷疑金鑰外洩：到 Cloud Console 把舊金鑰停用 → 建新金鑰 → 更新 GitHub Secret

---

## 六、常見問題

**Q: GitHub Actions 跑失敗怎麼辦？**
A: 點進失敗的 run → 看 log。常見錯誤：
- `KeyError: 'GA4_PROPERTY_ID'` → Secret 沒設定或名稱拼錯
- `403 Forbidden` (Drive) → service account 沒被加為資料夾編輯者
- `403 PERMISSION_DENIED` (GA4) → service account 沒加進 GA4

**Q: 想暫停自動排程？**
A: repo Actions 分頁 → 右上角 **Disable workflow**

**Q: GitHub Actions 是不是真的免費？**
A: Public repo 的 Actions **完全免費、無使用上限**。Private repo 每月有 2000 分鐘免費額度（一次跑約 1-2 分鐘，遠遠用不完）。
