# Gemini Telegram Bot

Telegram bot တစ်ခုကို Gemini API နဲ့ ချိတ်ထားတဲ့ minimal starter project ပါ။

## Features

- `/start`
- `/reset`
- ပုံမှန် text message တွေကို Gemini ဆီပို့ပြီး reply ပြန်ပေး
- Group ထဲမှာ `@botusername` mention လုပ်ရုံနဲ့ reply ပြန်ပေး
- Bot ကို group admin ပေးထားပြီး သုံးနိုင်
- URL ပို့ရင် page ထဲက main article text ကိုဖတ်ပြီး source-based answer ပေး
- Railway နဲ့ deploy လုပ်လို့ရ

## Local setup

```bash
cd /root/gemini-telegram-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
python main.py
```

## GitHub workflow

1. GitHub မှာ repo အသစ်တစ်ခုဖန်တီးပါ
2. ဒီ folder ထဲက code ကို push လုပ်ပါ
3. Railway မှာ `New Project`
4. `Deploy from GitHub Repo`
5. Repo ကိုရွေးပါ
6. Variables ထည့်ပါ

### Required variables

- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`
- `ADMIN_IDS` - comma-separated Telegram user IDs that can use `/addnote`

### Optional variables

- `GEMINI_MODEL` - default `gemini-3.6-flash`
- `SYSTEM_PROMPT` - bot ရဲ့ style ပြောင်းချင်ရင်
- `NOTES_DB_PATH` - default `notes_data.json`

## Railway notes

ဒီ project က webhook မသုံးဘဲ long polling နဲ့ run လုပ်ထားပါတယ်။
Railway မှာ Dockerfile ကို auto-detect လုပ်ပြီး container အနေနဲ့ run လုပ်နိုင်ပါတယ်။

## Group usage

1. Bot ကို Telegram group ထဲ invite လုပ်ပါ
2. Bot ကို admin ပေးပါ
3. Group ထဲမှာ `@your_bot_username` လို့ mention လုပ်ပြီး message ရေးပါ
4. Bot က mention ပါတဲ့ message ကိုပဲ Gemini ဆီပို့ပြီး reply ပြန်ပေးပါမယ်
5. Reply-to-bot message တွေလည်း အလုပ်လုပ်ပါမယ်

## URL reading

Bot ကို URL ပို့လိုက်ရင် page ကို fetch လုပ်မယ်, HTML ထဲက main article text ကို extract လုပ်မယ်, ပြီးရင် အဲဒီ source text ပေါ်မှာပဲ Gemini နဲ့ အဖြေထုတ်မယ်။

အလုပ်လုပ်ပုံ:

1. User က `https://...` URL ပို့
2. Bot က page ကို fetch လုပ်
3. Main article text ကို extract လုပ်
4. User က မေးထားတဲ့မေးခွန်းရှိရင် အဲဒါကို source-based answer ပြန်ပေး
5. Question မပါတဲ့ URL ဆိုရင် page summary ပြန်ပေး

သတိထားရန်:

- Public webpage တွေမှာအကောင်းဆုံးအလုပ်လုပ်တယ်
- Login လိုတဲ့ page, paywall, JavaScript-heavy site တွေမှာ extract မကောင်းနိုင်
- ဖတ်မရရင် error ပြန်ပြမယ်

## Admin notes

`/addnote` နဲ့ curated sources ထည့်လို့ရပါတယ်။

Example:

```text
/addnote Book Reviews | https://example.com/post1 https://example.com/post2 | fantasy, review, summary
```

အဲဒီလိုထည့်ပြီးရင် user မေးခွန်းထဲမှာ note title သို့မဟုတ် tag နဲ့ဆိုင်တဲ့အကြောင်းအရာတွေပါလာရင် bot က အရင်သိမ်းထားတဲ့ source တွေကိုဖတ်ပြီး answer ထုတ်မယ်။

Admin-only commands:

- `/addnote`
- `/notes`

## How it works

- Telegram message လက်ခံ
- Gemini `interactions.create(...)` ကိုခေါ်
- ရလာတဲ့ response ကို Telegram message အဖြစ်ပြန်ပို့

## Customize

`SYSTEM_PROMPT` ကိုပြောင်းပြီး bot personality ကိုညှိနိုင်ပါတယ်။
`GEMINI_MODEL` ကိုပြောင်းပြီး model ကိုလည်း လိုသလိုရွေးနိုင်ပါတယ်။
