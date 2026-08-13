# Gemini Telegram Bot

Telegram bot တစ်ခုကို Gemini API နဲ့ ချိတ်ထားတဲ့ minimal starter project ပါ။

## Features

- `/start`
- `/reset`
- ပုံမှန် text message တွေကို Gemini ဆီပို့ပြီး reply ပြန်ပေး
- Group ထဲမှာ `@botusername` mention လုပ်ရုံနဲ့ reply ပြန်ပေး
- Bot ကို group admin ပေးထားပြီး သုံးနိုင်
- URL ပို့ရင် page ထဲက main article text ကိုဖတ်ပြီး source-based answer ပေး
- `PROVIDER=auto` နဲ့ Gemini -> OpenRouter free -> DeepSeek -> Ollama local fallback သုံးနိုင်
- Thailand time နံနက် `06:30` တိတိ / ည `21:00` တိတိ group တွေထဲ morning / good night message ပို့
- Railway နဲ့ deploy လုပ်လို့ရ
- `/help` command
- URL fetch SSRF protection — internal/private address တွေကို block
- Per-user rate limit + daily cap — free quota မကုန်အောင်
- Per-chat lock — message နှစ်ခု တစ်ပြိုင်နက် ရောက်လာရင် ရောနှောမဖြေဘူး
- `ALLOWED_GROUP_IDS` — ရွေးထားတဲ့ group တွေပဲ သုံးလို့ရအောင် ကန့်သတ်လို့ရ

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
- `PROVIDER` - default `auto`
- `PROVIDER_ORDER` - default `gemini,openrouter_free,deepseek,ollama`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL` - default `openrouter/free`
- `OPENROUTER_REFERER`
- `OPENROUTER_TITLE`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL` - default `deepseek-chat`
- `DEEPSEEK_BASE_URL` - default `https://api.deepseek.com`
- `OLLAMA_BASE_URL` - default `http://localhost:11434`
- `OLLAMA_MODEL` - default `llama3.1:8b`
- `NOTES_DB_PATH` - default `notes_data.json`
- `GROUPS_DB_PATH` - default `groups_data.json`
- `THAILAND_TIMEZONE` - default `Asia/Bangkok`
- `ALLOWED_GROUP_IDS` - comma-separated group IDs (negative numbers) — ထည့်ထားရင် ဒီ group တွေပဲ bot သုံးလို့ရမယ် (empty = အကုန်ခွင့်)
- `RATE_LIMIT_SECONDS` - user တစ်ယောက် ထပ်မေးဖို့ စောင့်ရမယ့် စက္ကန့်အရေအတွက် (default `5`)
- `DAILY_MESSAGE_CAP` - user တစ်ယောက် တစ်နေ့ မေးလို့ရတဲ့ အကြိမ်အရေအတွက် (default `40`)
- `MAX_PROMPT_CHARS` - question အရှည်ဆုံး စာလုံးအရေအတွက် (default `4000`)

## Railway notes

ဒီ project က webhook မသုံးဘဲ long polling နဲ့ run လုပ်ထားပါတယ်။
Railway မှာ Dockerfile ကို auto-detect လုပ်ပြီး container အနေနဲ့ run လုပ်နိုင်ပါတယ်။

`Ollama` ကို local machine ပေါ်ကနေ fallback အဖြစ်သုံးချင်ရင် bot run နေတဲ့ host ကနေ reach လုပ်လို့ရတဲ့ `OLLAMA_BASE_URL` တစ်ခုလိုတယ်။
Railway ပေါ်က bot က သင့် laptop ရဲ့ localhost ကို တိုက်ရိုက် မမြင်နိုင်ပါဘူး။
အဲဒါကြောင့် local Ollama fallback ကို သုံးချင်ရင်:

- bot ကိုလည်း local run လုပ်
- သို့မဟုတ် Ollama ရှိတဲ့ VPS/LAN endpoint တစ်ခုအသုံးပြု
- သို့မဟုတ် Ollama ကို public reachable tunnel နဲ့ expose လုပ်

DeepSeek ကို သုံးချင်ရင် `DEEPSEEK_API_KEY` နဲ့ `DEEPSEEK_MODEL` ကို variables ထဲထည့်ပါ။
OpenRouter ထက်ပြီးတဲ့ cloud fallback တစ်ခုအဖြစ်လည်း သုံးလို့ရပါတယ်။

နေ့စဉ် `06:30` နဲ့ `21:00` messages တွေက bot register လုပ်ထားတဲ့ group တွေကိုပဲ သွားမယ်။
Group list ကို `groups_data.json` (နဲ့ `notes_data.json`) ထဲမှာထားပြီး persistent storage မရှိရင် redeploy/restart နောက်ပိုင်း ဆုံးနိုင်တယ်။

## Railway Volume (persistent data)

group list နဲ့ notes တွေ redeploy ခံနိုင်ရည်ရှိအောင် Railway volume သုံးနိုင်တယ်။

1. Railway dashboard → Service ထဲက Volumes tab ကိုသွားပါ
2. Volume အသစ်ဆောက်ပါ (ဥပမာ `gemini-bot-data`)
3. Mount path က `/data` လို့ထားပါ
4. Volume ကိုသုံးပြီးရင် `RAILWAY_VOLUME_PATH=/data` env var က auto ပါလာမယ်
5. Bot က auto detect လုပ်ပြီး JSON data files တွေကို volume ထဲမှာသိမ်းမယ်

Data structure:
```
/data/
├── notes_data.json     # /addnote နဲ့ထည့်ထားတဲ့ notes
└── groups_data.json    # Registered group list
```

Note: `GROUPS_DB_PATH` / `NOTES_DB_PATH` env var တွေနဲ့ သီးသန့်လမ်းကြောင်းသတ်မှတ်လည်းရပါတယ်။

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

`/addnote` နဲ့ curated sources သို့မဟုတ် plain question/answer notes ထည့်လို့ရပါတယ်။

Example:

```text
/addnote Book Reviews | https://example.com/post1 https://example.com/post2 | fantasy, review, summary
```

အဲဒီလိုထည့်ပြီးရင် user မေးခွန်းထဲမှာ note title သို့မဟုတ် tag နဲ့ဆိုင်တဲ့အကြောင်းအရာတွေပါလာရင် bot က အရင်သိမ်းထားတဲ့ source တွေကိုဖတ်ပြီး answer ထုတ်မယ်။

Plain question/answer note တွေလည်း ထည့်လို့ရပါတယ်:

```text
/addnote Space Question | space question, spacing issue | ဒီဟာက သက်ဆိုင်ရာ အဖြေပါ | faq, help
```

အဲဒီ format မှာ:

- 1st part = note title
- 2nd part = question words / trigger phrases
- 3rd part = answer text
- 4th part = optional tags

ဒီ mode က `space question` လို phrase ပါတဲ့ မေးခွန်းတွေကို token overlap နဲ့ဆီလျော်သလို match လုပ်ပြီး answer ပြန်ပေးနိုင်တယ်။

Admin-only commands:

- `/addnote`
- `/notes`

## How it works

- Telegram message လက်ခံ
- Provider chain ထဲက model ကိုခေါ်
- ရလာတဲ့ response ကို Telegram message အဖြစ်ပြန်ပို့

## Customize

`SYSTEM_PROMPT` ကိုပြောင်းပြီး bot personality ကိုညှိနိုင်ပါတယ်။
`GEMINI_MODEL` ကိုပြောင်းပြီး model ကိုလည်း လိုသလိုရွေးနိုင်ပါတယ်။
