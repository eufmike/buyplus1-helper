## Goal

This is a simple project to create a Chrome extension that assists users in customer service, integrating the backend with [buyplus1.com.tw](https://buyplus1.com.tw/) to facilitate their daily work, identify pitfalls, provide solutions and provide AI assisted chat responses to customers.

- **Language interaction:** Traditional Chinese
- **Customer Area:** Taiwan
- **Product source:** US, Taiwan, Japan, Korea, Australia, Europe, etc.

---

## Features

### 1. Daily Task Checklist
Tracks recurring daily work items based on `service_log.csv`:

| Task | Description | Schedule |
|------|-------------|----------|
| 新品上架 | New product listing | Daily |
| 新品入單 | New product order entry | Daily |
| 追漏單 | Chase missing/unprocessed orders | Daily |
| 匯款通知 | Payment received notification to customers | Daily |
| 催款通知 | Payment reminder to customers | Tue / Thu |
| 斷貨通知 | Out-of-stock notification | As needed |
| 直播 | Live stream session | As scheduled |
| 直播入單 | Live stream order entry | As scheduled |
| 發廠商文 | Send vendor documents | As needed |

### 2. AI-Assisted Customer Responses
- Generates draft replies in Traditional Chinese using the Claude API
- Context-aware: incorporates current task status and order/customer page context
- One-click copy to clipboard

### 3. Pitfall Detection
- Scans task notes for unresolved follow-up items (e.g. unanswered questions, pending confirmations, incomplete notifications)
- Groups flagged items by recency for easy triage

### 4. Site Integration
- Content script injected on buyplus1.com.tw pages
- Extracts order numbers, customer names, and page context to enrich AI responses

---

## Project Structure

```
buyplus1-helper/
├── manifest.json
├── service_log.csv          # Daily work log (imported by extension)
├── icons/
├── background/
│   └── service_worker.js    # Handles Claude API calls and storage
├── content/
│   └── content.js           # Injected into buyplus1.com.tw pages
├── lib/
│   ├── csv_parser.js        # Parses service_log.csv with date-inheritance
│   ├── task_engine.js       # Task matching, pitfall detection, daily checklist
│   ├── ai_client.js         # Claude API wrapper
│   └── utils.js             # Date helpers, string normalization
├── popup/
│   ├── popup.html           # Three-tab UI: Checklist | AI Chat | Pitfalls
│   ├── popup.js
│   └── popup.css
└── options/
    ├── options.html         # API key configuration
    └── options.js
```

---

## Setup

1. Clone this repo
2. Open Chrome and go to `chrome://extensions`
3. Enable **Developer mode**
4. Click **Load unpacked** and select this folder
5. Go to the extension **Options** page and enter your Claude API key
6. Import `service_log.csv` from the extension popup to load task history

---

## CSV Format

The `service_log.csv` follows this structure:

```
日期,工作項目,完成請打Ｖ,備註（待追事項）
3/19,新品上架,TRUE,some notes
    ,新品入單,TRUE,
    ,追漏單,FALSE,待確認回覆
```

- Rows with an empty date inherit the date from the previous row
- `完成` column accepts `TRUE`, `FALSE`, or `Ｖ`
- Notes column is scanned for unresolved action items

---

## Tech Stack

- Vanilla JS (no build tools)
- Chrome Extension Manifest V3
- Claude API (`claude-opus-4-6` or `claude-haiku-4-5`)
