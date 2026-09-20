# 🤖 تلگرام یوزربات هوشمند و سیستم ایجنت (Telegram AI Agent Userbot)

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Telethon](https://img.shields.io/badge/Telethon-MTProto-blueviolet.svg)](https://github.com/LonamiWebs/Telethon)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](Dockerfile)
[![Tests: 86 Passed](https://img.shields.io/badge/Tests-86%20Passed-brightgreen.svg)](tests/)

[English](README_EN.md) | [فارسی](README.md)

یک یوزربات شخصی تلگرام (MTProto Userbot) کاملاً ماژولار، استاندارد، ایمن و مقاوم در برابر محدودیت‌های نرخ تلگرام (**Rate-Limit Resilience**)، پیاده‌سازی‌شده با **Telethon** و متصل به موتور مدل‌های زبانی هوش مصنوعی (**Google Gemini**، **OpenAI** و **Ollama / Local LLMs**).

این سیستم هم‌زمان دو کارکرد حیاتی را پوشش می‌دهد:
1. **خلاصه‌سازی و مانیتورینگ هوشمند کانال‌ها و چت‌ها (Summarization & Digest):** در دو حالت دستوری (با ارسال فرمان در Saved Messages) و زمان‌بندی خودکار دوره‌ای با ایزوله‌سازی کانتکست در برابر تزریق دستور (Prompt Injection Defense).
2. **پاسخ‌گویی هوشمند به پیام‌های خصوصی (Human-like DM Auto-reply):** با شبیه‌سازی کامل رفتارهای انسانی (وضعیت `Typing...` متناسب با طول پاسخ و تاخیر تصادفی Jitter)، مکانیزم تجمیع پیام‌ها (**ChatDebouncer**) با قفل سریال‌سازی چت، کول‌داون حضور انسان، درک پیام‌های ریپلای‌شده، ماسک‌سازی خودکار داده‌های حساس (PII Redaction)، و تنظیمات امنیتی پیش‌فرض (`AUTO_REPLY_ENABLED=false`).

---

## 🌟 قابلیت‌های کلیدی و معماری امنیت

- **🔒 تنظیمات امن پیش‌فرض (Safe Defaults):** به طور پیش‌فرض پاسخ‌دهی خودکار غیرفعال است (`AUTO_REPLY_ENABLED=false`) تا از پاسخ‌های ناخواسته جلوگیری شود. با فعال‌سازی `ALLOWLIST_USERS`، بات تنها به کاربران مشخص پاسخ می‌دهد.
- **🛡️ مقاومت در برابر محدودیت نرخ تلگرام (Rate-Limit Resilience):** دکوراتور هوشمند `@with_floodwait` خطاهای FloodWait تلگرام را مدیریت کرده و با الگوریتم Exponential Backoff و Jitter تصادفی از ارسال درخواست‌های تکراری و مسدودی اکانت جلوگیری می‌کند.
- **⚡ تجمیع هوشمند پیام‌ها (ChatDebouncer):** پیام‌های متوالی و سریع یک مخاطب را با قفل اختصاصی چت (`ChatLock`) و سمافور سراسری هم‌زمانی تجمیع کرده و به صورت یک پیام منسجم به مدل ارسال می‌کند.
- **🕵️ فیلتر ساختاری محتوای حساس و مالی:**
  - اعتبارسنجی کارت‌های بانکی ۱۶ رقمی با الگوریتم **Luhn**.
  - شناسایی ساختاری کدهای ورود و رمزهای یک‌بار مصرف (**OTP**).
  - شناسایی کلیدهای خصوصی رمزنگاری و توکن‌های ابری.
  - فشرده‌سازی و محدودسازی نرخ هشدارهای امنیتی (Anti-Flood Throttling) در پیام‌های ذخیره‌شده.
- **🛡️ دفاع در برابر تزریق پرامپت (Prompt Injection Defense):** کلیه ورودی‌های کاربران خارجی و پیام‌های کانال‌ها در تگ‌های ساختاری `<untrusted_user_input>` و `<untrusted_channel_history>` محصور شده و مدل زبانی با دستورالعمل‌های امنیتی اکید در برابر تغییر هویت محافظت می‌شود.
- **💾 پایداری اتمیک داده‌ها (Atomic StateRepository):** ذخیره‌سازی وضعیت توقف، لیست سیاه و مدل فعال در فایل پایدار `/data/state.json` با مکانیسم رایت اتمیک (`os.replace`) مقاوم در برابر قطع ناگهانی برق یا ری‌استارت کانتینر.

---

## 🏛️ ساختار معماری پروژه (Architecture)

```
telegram_agent_userbot/
├── config/
│   ├── __init__.py
│   └── settings.py             # اعتبارسنجی تنظیمات با Pydantic Settings و پارسر CSV
├── client/
│   ├── __init__.py
│   ├── telethon_client.py      # مدیریت نشست کلاینت MTProto و چرخه حیات Telethon
│   ├── anti_ban.py             # دکوراتور بافر بازتلاش FloodWait و تاخیرهای رفتاری
│   └── message_sender.py       # ارسال‌کننده پیام با خردسازی استاندارد (<=4096) و ماسک PII
├── llm/
│   ├── __init__.py
│   ├── base.py                 # رابط انتزاعی BaseLLMProvider، Data Models و Exception Hierarchy
│   ├── gemini_provider.py      # درایور ناهمگام Google Gemini با تایم‌اوت و بازتلاش نمایی
│   ├── openai_provider.py      # درایور OpenAI و مدل‌های سازگار (Ollama/vLLM) با بازتلاش ۴۲۹/۵xx
│   ├── mock_provider.py        # درایور شبیه‌ساز آفلاین دترمینیستیک جهت تست و دیباگ
│   └── factory.py              # فکتوری و رجیستری ایجاد و تست سلامت مدل زبانی
├── filters/
│   ├── __init__.py
│   ├── base.py                 # ساختارهای FilterContext و FilterResult
│   ├── system_filter.py        # مسدودسازی قطعی اکانت‌های رسمی تلگرام (777000) و پیام‌های خود
│   ├── bot_filter.py           # فیلتر و نادیده گرفتن اکانت‌های ربات (is_bot=True)
│   ├── blacklist_filter.py     # مسدودسازی افراد و چت‌های لیست سیاه با نرمال‌سازی شناسه
│   ├── sensitive_filter.py     # شناساگر ساختاری Luhn کارت‌ها، کدهای OTP و نرمال‌سازی فارسی
│   └── pipeline.py             # پایپ‌لاین اتصال و اجرای زنجیره‌ای فیلترها (Short-circuit)
├── services/
│   ├── __init__.py
│   ├── alert_service.py        # ارسال هشدارهای فوری امنیتی به Saved Messages با Anti-Flood
│   ├── chat_debouncer.py       # تجمیع پیام‌ها با قفل سریال‌سازی چت و سمافور هم‌زمانی
│   ├── humanizer.py            # شبیه‌ساز زمان خواندن پیام و زمان تایپ متناسب
│   ├── digest_service.py       # استخراج تاریخچه، خردسازی و خلاصه تحلیلی با تگ‌های امنیتی
│   ├── auto_reply_service.py   # هماهنگ‌کننده پاسخ‌دهی (کول‌داون انسان، لیست سفید، ماسک PII)
│   └── state_repository.py     # مخزن وضعیت پایدار با ذخیره‌سازی اتمیک در /data/state.json
├── handlers/
│   ├── __init__.py
│   ├── dm_handler.py           # شنود پیام‌های خصوصی با سیاست مدیا، فیلتر سن پیام و دابل‌چک
│   └── saved_messages_handler.py # فرامین کنترلی (/summary, /digest, /pause, /resume, /mode, /blacklist, /status)
├── scheduler/
│   ├── __init__.py
│   └── digest_scheduler.py     # کارگر زمان‌بند پس‌زمینه (Background Worker) برای بولتن دوره‌ای
├── scripts/
│   └── generate_session_string.py # اسکریپت ساخت TELEGRAM_SESSION_STRING برای دیپلوی ابری
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # زیرساخت تست آفلاین، MockTelethonClient و FastSleep
│   ├── test_p0_fixes.py        # تست‌های تنظیمات CSV، کول‌داون بات/انسان و پیش‌فرض‌ها (۷ تست)
│   ├── test_p1_reliability.py  # تست‌های قفل دیبانسر، تایم‌اوت LLM و پایداری اتمیک (۸ تست)
│   ├── test_p3_security.py     # تست‌های Luhn، تراتل هشدارها، تگ‌های پرامپت و سن پیام (۱۲ تست)
│   ├── test_tier1_features.py  # تست‌های پایه تک‌تک قابلیت‌ها (۲۹ تست)
│   ├── test_tier2_boundaries.py# تست‌های مقادیر مرزی و یونیکد فارسی (۷ تست)
│   ├── test_tier3_combinations.py# تست‌های تعاملات متقابل فیلترها و مقاومت سیستم (۵ تست)
│   ├── test_tier4_scenarios.py # سناریوهای واقعی کاربر و حملات فیشینگ (۴ تست)
│   ├── test_tier5_adversarial.py# تست‌های هم‌زمانی و ورودی‌های خرابکارانه (۵ تست)
│   └── test_tier6_enhancements.py# تست‌های قابلیت‌های تکمیلی و فرامین (۹ تست)
├── Dockerfile                  # فایل ساخت کانتینر چندمرحله‌ای داکر با کاربر غیرریشه
├── docker-compose.yml          # استقرار سریع با داکر کامپوز و اتصال ولوم ./data
├── pyproject.toml              # مشخصات پروژه پایتون و ابزارهای Ruff و Pytest
├── .env.example                # قالب آماده متغیرهای محیطی
├── requirements.txt            # فهرست نیازمندی‌ها و وابستگی‌های پایتون
├── persona_prompt.txt          # فایل تنظیم آزادانه پرسونا و لحن ایجنت
├── main.py                     # نقطه ورود با مدیریت سیگنال‌های SIGINT/SIGTERM
└── README.md                   # راهنمای کامل فارسی
```

---

## 🚀 راهنمای راه‌اندازی گام‌به‌گام

### گام ۱: دریافت اعتبارسنجی API تلگرام
1. به سایت رسمی تلگرام به آدرس [my.telegram.org](https://my.telegram.org) مراجعه کنید.
2. با شماره تلفن همراه اکانت خود وارد شده و کد ارسال‌شده در تلگرام را ثبت کنید.
3. به بخش **API development tools** بروید و اپلیکیشن جدید بسازید تا `TELEGRAM_API_ID` و `TELEGRAM_API_HASH` را دریافت کنید.

### گام ۲: تنظیم متغیرهای محیطی (`.env`)
فایل `.env.example` را کپی کرده و نام آن را به `.env` تغییر دهید:
```bash
cp .env.example .env
```
سپس مقادیر کلیدی را تنظیم نمایید:
```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_telegram_api_hash_here

# انتخاب مدل زبانی: gemini یا openai یا mock
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_google_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# کنترل‌های ایمنی و پاسخ‌دهی
AUTO_REPLY_ENABLED=false
ALLOWLIST_USERS=12345678,trusted_friend
DRY_RUN=false
SEND_HISTORY_TO_PROVIDER=true
REDACT_PII_BEFORE_LLM=true

# کانال‌های مورد نظر برای خلاصه‌سازی خودکار (جداشده با کاما)
DIGEST_CHANNELS=durov,tech_news_channel
DIGEST_INTERVAL_MINUTES=360
```

### گام ۳: شخصی‌سازی لحن و پرسونا (`persona_prompt.txt`)
فایل `persona_prompt.txt` به شما امکان می‌دهد بدون دست زدن به کدهای برنامه، نحوه معرفی، لحن گفتگو (رسمی یا صمیمی)، و اطلاعات لازم را به هوش مصنوعی آموزش دهید.

### گام ۴: اجرای برنامه

#### روش مستقیم با پایتون:
```bash
python main.py
```

#### روش اجرا با Docker Compose (پیشنهادی برای سرور):
```bash
docker-compose up -d
```
داده‌های سشن و وضعیت برنامه در شاخه `./data` به صورت پایدار ذخیره می‌شوند.

---

## 🎮 فرامین کنترلی در پیام‌های ذخیره‌شده (Saved Messages)

می‌توانید مستقیماً در چت **Saved Messages** خودتان دستورات زیر را ارسال کنید:

| دستور | توضیح | مثال |
|---|---|---|
| `/summary <channel> [limit] [topic]` | اسکن و خلاصه‌سازی تحلیلی فوری پیام‌های اخیر یک کانال | `/summary @durov 30 اخبار هوش مصنوعی` |
| `/digest [limit]` | استخراج و تولید بولتن خبری از تمام کانال‌های منتخب | `/digest 20` |
| `/pause [minutes]` | توقف موقت پاسخ‌دهی خودکار (با تعیین زمان یا نامحدود) | `/pause 30` |
| `/resume` | فعال‌سازی مجدد پاسخ‌دهی خودکار | `/resume` |
| `/mode <gemini\|openai\|mock>` | تغییر آنلاین و آنی موتور هوش مصنوعی فعال با بررسی سلامت قبلی | `/mode openai` |
| `/blacklist <add\|remove> <user>` | افزودن یا حذف کاربر/شناسه از لیست سیاه با ذخیره پایدار | `/blacklist add @spammer` |
| `/status` | مشاهده وضعیت اتصال، مدل هوش مصنوعی، لیست سفید، وضعیت آزمایشی و مانیتورینگ | `/status` |
| `/help` | نمایش راهنمای کامل فرامین | `/help` |

---

## 🧪 اجرای آزمون‌های خودکار (Offline Verification)

تمام اجزای یوزربات مجهز به یک زیرساخت تست ۱۰۰٪ آفلاین هستند که بدون نیاز به اتصال به تلگرام یا مصرف سهمیه API اجرا می‌شوند:

```bash
python -m pytest tests/ -v
```

پوشش آزمون‌ها شامل **۸۶ تست جامع** با نرخ قبولی ۱۰۰٪ است:
- **Phase 0 Tests (7 تست):** پارس متغیرهای محیطی با کاما، تفکیک پیام‌های ربات از انسان، لیست سفید و حالت Dry Run.
- **Phase 1 Tests (8 تست):** قفل سریال‌سازی دیبانسر، تایم‌اوت و بازتلاش LLM، تغییر اتمیک مدل و پایداری StateRepository.
- **Phase 3 Tests (12 تست):** الگوریتم Luhn، شناسایی OTP، محدودسازی نرخ هشدارها، سیاست مدیا و فیلتر سن پیام.
- **Tier 1-6 Tests (59 تست):** تست‌های ماژول‌های پایه، مقادیر مرزی، سناریوهای واقعی و ورودی‌های خرابکارانه.

---

## ⚖️ سلب مسئولیت و ملاحظات امنیتی (Disclaimer & Safety)

⚠️ **هشدار امنیتی و قوانین تلگرام:**
این نرم‌افزار به عنوان یک **یوزربات تلگرام (Userbot)** بر بستر پروتکل MTProto کار می‌کند. با وجود اعمال بالاترین استانداردهای مقاوم‌سازی در برابر ریت‌لیمیت (`@with_floodwait`)، تاخیرهای تصادفی شبه‌انسانی (`Humanizer`) و توقف خودکار هنگام حضور صاحب اکانت، اتوماسیون حساب‌های شخصی ممکن است با قوانین شرایط استفاده تلگرام ([Telegram Terms of Service](https://telegram.org/tos)) در تضاد باشد.

توصیه‌های مهم:
1. در شروع کار از حالت آزمایشی (`DRY_RUN=true`) استفاده نمایید.
2. پاسخ‌دهی خودکار را به لیست مجاز (`ALLOWLIST_USERS`) محدود کنید.
3. هرگز از این بات برای ارسال پیام‌های انبوه، تبلیغاتی یا مزاحمت استفاده نکنید.
4. توسعه‌دهندگان هیچ‌گونه مسئولیتی در قبال محدودیت، مسدودسازی موقت یا دائم حساب تلگرام بر عهده نخواهند داشت.

---

## 📄 مجوز (License)

این پروژه تحت مجوز [MIT License](LICENSE) منتشر شده است.
