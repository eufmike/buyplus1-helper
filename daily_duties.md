# Daily Duties

This document describes the recurring and occasional work duties tracked in `service_log.csv`.

---

## Recurring Daily Tasks

These tasks appear in every work day's log.

### 新品上架 (New Product Listing)

- List newly arrived products on the platform
- process:
  1. Import from Facebook posts to the buyplus1 website:
     - the product will be first posted on facebook.  
     - the import to the buyplus1 database will be done via their Chrome extension, where an sign will pop up on the newly posted facebook post.
  2. Post selection:
     - after the product is imported, it will be listed on the buyplus1 website.
     - then go to the page of 匯入商品->匯入FB社團貼文 (kind like inbox), pick up the actual product user want to list
     - Because the buyplus1 extension performs batch import by newest post (for example, newest 10 posts), it has no knowledge to distinguish between product post, promotion post, and event post (streaming selling event). Also, duplication could happen since the import mechanism is only basic.
     - In the current workflow, users spend significant time on clean the "inbox", filter the actual product posts, check the title and listing price.
     - Once the products are filtered and selected, users need to click import (匯入貼文/商品), then selected product will be imported to product management page (商品管理->全部商品)
  3. Sub-listing:
     - Users move to the product management page, find the newly imported product
     - Each product may include multiple variants (e.g. different colors or sizes, different prices by payment). The listing process requires users to select which variants to list, and set the price for each variant.
     - Steps: 
       1. status（狀態）: 已下架 -> 上架中
       2. check if the price and amount are correct.
          1. price (價格): the price announced in the post
          2. amount (數量): often time this won't be announced in the post, but sometimes it is specified during the streaming
       3. then decide the spec （規格）, which can be selected from the dropdown menu or input manually in the first option（手動輸入）
       4. Each spec needs to fill in the following fields: 
          - 規格值(款式): the actual spec value, for example, "藍色S", "紅色M", "黑色L"
          - 備註: any notes related to this spec, for example, "內衣玫瑰色只剩Ｓ，問要不要換貨"
          - 數量: the quantity of this spec to be listed
          - 減去數量: the quantity that has already been ordered (if any), which should be subtracted from the total quantity to get the available quantity for listing
          - 單價: the price for this spec, which is relative to the import price (the price of the product when it was imported from Facebook)
       5. discount(折扣)：
          1. 會員類型：批發會員 一般會員 親友價
          2. 需購買數量
          3. 單價
          4. 開始日期
          5. 結束日期
          6. 順序
- Also appears abbreviated as **上架**
- Common follow-ups: notify customers of arrival, confirm items not yet listed, handle partially-listed batches

### 新品入單 (New Product Order Entry)

- Enter new orders into the system after products are listed
- Also appears abbreviated as **入單**
- Common follow-ups: confirm sizing/color selections with customers before entry, reconcile any unclear orders

### 追漏單 (Chase Missing Orders)

- Review and follow up on orders that may have been missed, unprocessed, or unconfirmed
- Common follow-ups: contact customers awaiting responses, confirm pending item selections, resolve ambiguous order details

### 匯款通知 (Payment Received Notification)

- Notify customers that their payment has been received
- Common follow-ups: incomplete batch sends (noted as "還沒發完"), notify in name-sorted order across multiple sessions (p1, p2, p3...)

### 催款通知 (Payment Reminder)

- Send payment reminders to customers with outstanding balances
- **Schedule: Tuesdays and Thursdays only (三/五進行)**
- Common follow-ups: continue the previous day's batch, track customers who have not responded

### 斷貨通知 (Out-of-Stock Notification)

- Notify affected customers when a product goes out of stock
- Marked as **非常態** (non-routine) — only executed when a stockout occurs
- Common follow-ups: confirm whether to refund or substitute; batch sends may span multiple days

### 直播 (Live Stream)

- Conduct or participate in a live stream sales session
- Marked FALSE on most days; only TRUE when a session is scheduled

### 直播入單 (Live Stream Order Entry)

- Enter orders placed during a live stream session into the system
- Only applicable on live stream days

---

## Occasional Tasks

These tasks appear on specific days based on business needs.

### 發廠商文 (Send Vendor Documents)

- Send procurement or coordination documents to vendors
- Triggered when new vendor orders or shipments need to be arranged

### 廠商貨發單 (Vendor Shipment Order)

- Issue a shipment order to the vendor for goods to be sent
- Triggered after confirming customer order details with the vendor

### 義大利包相關作業 (Italy Bag Operations)

- **義大利包未加入會員的提醒他們加入** — remind customers who purchased Italy bags but haven't joined the membership program
- **義大利包再入單** — re-enter Italy bag orders (e.g. after confirmation or correction)

### 內衣相關確認 (Underwear Order Confirmation)

- **內衣再確認** — follow up on underwear orders that need size/color reconfirmation before processing
- **內衣玫瑰色只剩Ｓ，問要不要換貨** — example of a stock-limitation follow-up: contact customer about substitution when only one size remains

---

## Notes Column Conventions

The **備註（待追事項）** column is used to record follow-up items. Common patterns:

| Pattern | Meaning |
|---------|---------|
| `等...回覆` / `等...確認` | Waiting for a response or confirmation |
| `還沒...` | Task not yet completed |
| `要跟...問` | Need to check with a specific person |
| `？` | Unresolved question |
| `先發到p2` / `先發到p3` | Batch notification in progress; resume from this page |
| Customer name only | Direct follow-up needed with that customer |

---

## Weekly Schedule Summary

| Task | Mon | Tue | Wed | Thu | Fri |
|------|-----|-----|-----|-----|-----|
| 新品上架 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 新品入單 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 追漏單 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 匯款通知 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 催款通知 | — | ✓ | — | ✓ | — |
| 斷貨通知 | as needed | as needed | as needed | as needed | as needed |
| 直播 | as scheduled | as scheduled | as scheduled | as scheduled | as scheduled |
| 直播入單 | as scheduled | as scheduled | as scheduled | as scheduled | as scheduled |
| 發廠商文 / 廠商貨發單 | occasional | occasional | occasional | occasional | occasional |
