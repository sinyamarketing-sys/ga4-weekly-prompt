# GA4 → Claude.ai Weekly Report

每週一自動從 Google Analytics 4 抓取數據，生成可貼到 [Claude.ai](https://claude.ai) 的完整分析 prompt，並上傳到 Google Drive。

## 流程

```
GitHub Actions (週一 08:00 台北時間)
    ↓
從 GA4 抓上週 + 上上週數據
    ↓
組合成含分析指令的 Markdown prompt
    ↓
上傳到 Google Drive (Markdown + Google Docs)
    ↓
你開 Drive → 全選複製 → 貼到 Claude.ai → 拿到完整週報
```

## 設定方式

詳見 [SETUP.md](./SETUP.md)。

## 技術棧

- Python 3.11
- Google Analytics Data API v1
- Google Drive API v3
- GitHub Actions

## 授權

MIT
