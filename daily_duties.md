# Daily Duties

This document describes the recurring and occasional work duties tracked in `service_log.csv`.

---

## Recurring Daily Tasks

These tasks appear in every work day's log.

### 新品上架 (New Product Listing)

List newly arrived products on the platform. Also abbreviated as **上架**.

**Process:**

1. **Import from Facebook posts**
   - Products are first posted on Facebook.
   - The buyplus1 Chrome extension detects new posts and shows a sign-in prompt, triggering a batch import into the buyplus1 database.

2. **Post selection** (匯入商品 → 匯入FB社團貼文)
   - This inbox receives all batch-imported posts. Because the extension imports by newest post (e.g. newest 10 posts), it cannot distinguish product posts from promotions or live-stream events, and duplicates may occur.
   - Users must manually filter the inbox, identify actual product posts, and verify the title and listing price.
   - Once filtered, click 匯入貼文/商品 to send selected products to 商品管理 → 全部商品.

3. **Sub-listing** (商品管理 → 全部商品)
   - Find the newly imported product. Each product may have multiple variants (colors, sizes, payment tiers).
   - For each variant to be listed:
     1. Set **狀態**: 已下架 → 上架中
     2. Verify **price (價格)** — from the Facebook post — and **amount (數量)** — often unspecified unless stated during a live stream.
     3. Select or manually input the **spec (規格)** via the dropdown or 手動輸入.
     4. Fill in spec fields:
        | Field | Description |
        |-------|-------------|
        | 規格值(款式) | Spec value, e.g. 藍色S, 紅色M, 黑色L |
        | 備註 | Notes for this spec, e.g. "內衣玫瑰色只剩Ｓ，問要不要換貨" |
        | 數量 | Total quantity to list |
        | 減去數量 | Already-ordered quantity to subtract from total |
        | 單價 | Price for this spec (relative to import price) |
     5. Configure **discounts (折扣)** if applicable:
        | Field | Options / Notes |
        |-------|-----------------|
        | 會員類型 | 批發會員 / 一般會員 / 親友價 |
        | 需購買數量 | Minimum purchase quantity |
        | 單價 | Discounted unit price |
        | 開始日期 | Discount start date |
        | 結束日期 | Discount end date |
        | 順序 | Priority order |

**Common follow-ups:** notify customers of arrival, confirm items not yet listed, handle partially-listed batches.

### 新品入單 (New Product Order Entry)

Enter new orders into the system after products are listed. Also abbreviated as **入單**.

Occurs after the product listing stage. Customers place orders by commenting on the Facebook post. A second round of import is required to capture those orders after a period of time — typically done twice a day.

**Process:**

1. **Import from the extension (匯入):** Define the time period for the extension to parse the comment section of each post and detect new orders.
2. **Confirm and import:** Once new orders are identified, import them into the system so the database records the purchase.

**Common follow-ups:** confirm sizing/color selections with customers before entry, reconcile any unclear orders.

### 追漏單 (Chase Missing Orders)

Review and follow up on orders that may not yet have been imported, due to a limited parse window or failed parsing.

### 匯款通知 (Payment Received Notification)

Notify customers that their payment has been received and their order is confirmed.

### 催款通知 (Payment Reminder)

Send payment reminders to customers with outstanding balances, after a grace period following the initial payment notification.

- **Schedule: Wednesday and Friday only (三/五進行)**
- **Common follow-ups:** continue the previous day's batch, track customers who have not responded.

### 斷貨通知 (Out-of-Stock Notification)

Notify affected customers when a product goes out of stock. Marked as **非常態** (non-routine) — only triggered when a stockout occurs.

- **Common follow-ups:** confirm whether to refund or substitute; batch sends may span multiple days.

### 直播 (Live Stream)

Conduct or participate in a live stream sales session. Marked FALSE on most days; only TRUE when a session is scheduled.

### 直播入單 (Live Stream Order Entry)

Enter orders placed during a live stream session into the system. Only applicable on live stream days.
