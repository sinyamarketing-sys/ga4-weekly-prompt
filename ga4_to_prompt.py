"""
GA4 → Claude.ai Prompt Pack 自動生成器

每週一 08:00 (台北時間) 由 GitHub Actions 觸發：
1. 從 GA4 Data API 拉取上週 + 上上週數據
2. 整理成結構化 JSON
3. 包成可直接貼到 Claude.ai 的 prompt（含分析指令）
4. 上傳到 Google Drive 指定資料夾，同時生成 Markdown 和 Google Docs 兩種格式

環境變數（透過 GitHub Secrets 注入）：
  GA4_PROPERTY_ID       - GA4 屬性 ID
  DRIVE_FOLDER_ID       - Google Drive 目標資料夾 ID
  GOOGLE_APPLICATION_CREDENTIALS - Service Account JSON 路徑
"""

import os
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest, OrderBy,
)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# ===== 設定 =====
PROPERTY_ID = os.environ["GA4_PROPERTY_ID"]
DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]
REPORT_DAYS = 7  # 報表涵蓋天數
TOP_N = 15       # 各維度取前 N 筆

TAIPEI_TZ = timezone(timedelta(hours=8))


# ===== GA4 資料抓取 =====
def get_date_ranges(days: int = REPORT_DAYS):
    """回傳本期與上期的日期區間（以台北時區為準，end 為昨天）"""
    today_taipei = datetime.now(TAIPEI_TZ).date()
    cur_end = today_taipei - timedelta(days=1)
    cur_start = cur_end - timedelta(days=days - 1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return (
        (cur_start.isoformat(), cur_end.isoformat()),
        (prev_start.isoformat(), prev_end.isoformat()),
    )


def run_report(client, dimensions, metrics, start, end, limit=TOP_N, order_by_metric=None):
    """通用 GA4 報表查詢"""
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start, end_date=end)],
        limit=limit,
    )
    if order_by_metric:
        request.order_bys = [
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name=order_by_metric), desc=True)
        ]
    response = client.run_report(request)
    rows = []
    for row in response.rows:
        record = {}
        for i, d in enumerate(dimensions):
            record[d] = row.dimension_values[i].value
        for i, m in enumerate(metrics):
            v = row.metric_values[i].value
            try:
                record[m] = float(v) if "." in v else int(v)
            except ValueError:
                record[m] = v
        rows.append(record)
    return rows


def fetch_ga4_data():
    """抓取本週與上週數據（電商導向指標）"""
    client = BetaAnalyticsDataClient()
    (cur_start, cur_end), (prev_start, prev_end) = get_date_ranges()

    data = {
        "current_period": {"start": cur_start, "end": cur_end},
        "previous_period": {"start": prev_start, "end": prev_end},
    }

 # 總覽指標（GA4 限制單次最多 10 個 metric，拆成兩組查詢）
    overview_metrics_basic = [
        "activeUsers", "newUsers", "sessions", "screenPageViews",
        "averageSessionDuration", "bounceRate", "engagementRate",
        "conversions", "totalRevenue", "transactions",
    ]
    overview_metrics_ecom = [
        "purchaseRevenue", "addToCarts", "checkouts",
        "ecommercePurchases", "itemViewEvents",
    ]

    def _fetch_overview(start, end):
        basic = run_report(client, [], overview_metrics_basic, start, end, limit=1)
        ecom = run_report(client, [], overview_metrics_ecom, start, end, limit=1)
        merged = {}
        if basic:
            merged.update(basic[0])
        if ecom:
            merged.update(ecom[0])
        return [merged] if merged else []

    data["overview_current"] = _fetch_overview(cur_start, cur_end)
    data["overview_previous"] = _fetch_overview(prev_start, prev_end)
  

    # 來源/媒介
    data["top_sources"] = run_report(
        client,
        ["sessionSource", "sessionMedium"],
        ["sessions", "activeUsers", "conversions", "totalRevenue"],
        cur_start, cur_end,
        order_by_metric="sessions",
    )

    # Channel grouping
    data["channels"] = run_report(
        client,
        ["sessionDefaultChannelGroup"],
        ["sessions", "activeUsers", "conversions", "totalRevenue"],
        cur_start, cur_end,
        order_by_metric="sessions",
    )

    # 熱門頁面
    data["top_pages"] = run_report(
        client,
        ["pagePath"],
        ["screenPageViews", "activeUsers", "averageSessionDuration", "bounceRate"],
        cur_start, cur_end,
        order_by_metric="screenPageViews",
    )

    # 著陸頁
    data["landing_pages"] = run_report(
        client,
        ["landingPage"],
        ["sessions", "activeUsers", "bounceRate", "conversions"],
        cur_start, cur_end,
        order_by_metric="sessions",
    )

    # 國家
    data["top_countries"] = run_report(
        client, ["country"],
        ["activeUsers", "sessions", "conversions"],
        cur_start, cur_end,
        order_by_metric="activeUsers",
    )

    # 裝置類別
    data["devices"] = run_report(
        client, ["deviceCategory"],
        ["activeUsers", "sessions", "bounceRate", "conversions", "totalRevenue"],
        cur_start, cur_end,
        order_by_metric="activeUsers",
    )

    # 熱門商品（電商）
    data["top_items"] = run_report(
        client,
        ["itemName"],
        ["itemsViewed", "itemsAddedToCart", "itemsPurchased", "itemRevenue"],
        cur_start, cur_end,
        order_by_metric="itemRevenue",
    )

    # 每日趨勢
    data["daily_trend"] = run_report(
        client, ["date"],
        ["activeUsers", "sessions", "conversions", "totalRevenue", "transactions"],
        cur_start, cur_end,
        limit=REPORT_DAYS,
    )

    return data


# ===== 組成 Prompt =====
def build_prompt(ga4_data: dict) -> str:
    """組合成完整的 Claude.ai prompt（含電商導向分析指令）"""
    cur = ga4_data["current_period"]
    prev = ga4_data["previous_period"]

    instructions = f"""你是一位資深電商數據分析顧問，正在為信亞網購 (sinya.com.tw) 撰寫週報。

我會在下面提供 GA4 過去兩週的完整數據。請用**繁體中文**產出一份結構化分析報告，包含以下章節：

## 1. 本週摘要（3-5 句話）
- 一段 high-level 重點，包含 Users、Sessions、轉換、營收的變化
- 點出本週最值得注意的一件好事和一件壞事

## 2. 關鍵指標對比表
請用 Markdown 表格列出本週 vs 上週：
- Active Users / New Users / Sessions / 頁面瀏覽
- Avg Session Duration / Bounce Rate / Engagement Rate
- 轉換次數 / 交易筆數 / 總營收 / 平均訂單價值 (AOV)
- 加入購物車事件 / 結帳事件 / 購買事件
- 每個指標都要顯示「本週值、上週值、變化 %（標示 ↑↓）」
- 變化超過 ±15% 用 ⚠️ 標記

## 3. 流量來源與轉換漏斗觀察
- 哪些 channel / source 帶來最多流量？哪些帶來最多營收？
- 流量大但轉換低的來源（檢視中找出問題）
- 流量小但轉換率高的來源（可以加碼投資）
- 評估各管道的 ROAS 概念（哪些值得擴大、哪些應該收掉）

## 4. 熱門頁面與商品分析
- 哪些頁面 PV 高、停留時間長？
- 哪些頁面跳出率異常（>70% 且流量大）？
- Top 商品的「瀏覽 → 加購 → 購買」漏斗轉換率分別是多少？
- 找出「曝光高但加購率低」或「加購高但購買率低」的商品

## 5. 裝置與地區洞察
- 各裝置（desktop/mobile/tablet）的轉換率與營收貢獻
- 地區 Top 5 + 是否有意外的成長地區

## 6. 異常與警訊 🚨
任何符合以下條件都要點出：
- 任何核心指標 >20% 的波動
- 跳出率 >70% 且流量在 Top 10 的頁面
- 轉換率驟降的來源
- 加購到購買的轉換率 <20%
- 每日趨勢中有單日異常高/低點（例如某天流量突增/驟降）

## 7. 下週行動建議
列出 3-5 個**具體可執行**的 action items：
- 要明確指出對象（例如「某個頁面」、「某個來源」、「某個商品」）
- 要附上預估影響（例如「預估可提升轉換率 X%」）
- 排優先順序（高 / 中 / 低）

---

報告風格要求：
- 直接、數據導向、不廢話
- 所有百分比計算到小數點後一位
- 用 Markdown 格式，方便我貼到報告系統
- 不要重複 raw data，重點是「洞察」而非「數字搬運」

---

## GA4 原始數據

**本週**：{cur['start']} ~ {cur['end']}
**上週**：{prev['start']} ~ {prev['end']}

```json
{json.dumps(ga4_data, ensure_ascii=False, indent=2, default=str)}
```

請開始分析。
"""
    return instructions


# ===== 上傳到 Google Drive =====
def upload_to_drive(local_md_path: str, ts: str):
    """同時上傳 Markdown 檔案 + 建立 Google Docs"""
    creds = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    service = build("drive", "v3", credentials=creds)

    base_name = f"GA4_週報_Prompt_{ts}"

    # 1. 上傳 Markdown 原檔（方便複製貼上 Claude.ai）
    md_metadata = {
        "name": f"{base_name}.md",
        "parents": [DRIVE_FOLDER_ID],
        "mimeType": "text/markdown",
    }
    md_media = MediaFileUpload(local_md_path, mimetype="text/markdown")
    md_file = service.files().create(
        body=md_metadata, media_body=md_media, fields="id, webViewLink"
    ).execute()

    # 2. 同時建立 Google Docs（用 mimeType 轉換）
    doc_metadata = {
        "name": base_name,
        "parents": [DRIVE_FOLDER_ID],
        "mimeType": "application/vnd.google-apps.document",
    }
    doc_media = MediaFileUpload(local_md_path, mimetype="text/markdown")
    doc_file = service.files().create(
        body=doc_metadata, media_body=doc_media, fields="id, webViewLink"
    ).execute()

    return {
        "markdown_link": md_file.get("webViewLink"),
        "doc_link": doc_file.get("webViewLink"),
    }


# ===== 主程式 =====
def main():
    print("📊 正在從 GA4 拉取數據...")
    ga4_data = fetch_ga4_data()

    print("📝 正在組合 Claude.ai prompt...")
    prompt = build_prompt(ga4_data)

    # 存檔（在 Cloud Shell / GitHub Actions runner 本地）
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    cur = ga4_data["current_period"]
    ts = f"{cur['start']}_to_{cur['end']}"
    md_path = out_dir / f"prompt_{ts}.md"
    md_path.write_text(prompt, encoding="utf-8")

    # 同時存一份原始 JSON 備查
    json_path = out_dir / f"raw_{ts}.json"
    json_path.write_text(
        json.dumps(ga4_data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print("☁️  正在上傳到 Google Drive...")
    links = upload_to_drive(str(md_path), ts)

    print("\n✅ 完成！")
    print(f"   📄 Markdown 檔: {links['markdown_link']}")
    print(f"   📝 Google Docs: {links['doc_link']}")
    print("\n下一步：開啟其中一個連結 → 全選複製 → 貼到 claude.ai → 送出")


if __name__ == "__main__":
    main()
