# OnlineNews Bot

ربات خبری تلگرام برای Android (Termux). هر ۳۰ دقیقه منابع خبری فارسی، انگلیسی، عربی و روسی را بررسی می‌کند، با هوش مصنوعی فیلتر، ترجمه و خلاصه می‌کند و در کانال تلگرام منتشر می‌کند. پنل مدیریت در چت خصوصی ربات دارد.

## امکانات

- بررسی خودکار منابع خبری چندزبانه
- فیلتر اهمیت خبر با هوش مصنوعی
- ترجمه و خلاصه‌سازی فارسی
- انتشار خودکار در کانال تلگرام
- پنل مدیریت در چت خصوصی ربات
- ذخیره در دیتابیس برای جلوگیری از خبر تکراری

## نصب در Termux

    pkg update -y && pkg upgrade -y
    pkg install -y python git gh nano sqlite
    gh auth login
    git clone https://github.com/X1-starr/OnlineNews.git
    cd OnlineNews
    pip install -r requirements.txt
    cp .env.example .env
    nano .env

مقدارهای `.env` را پر کنید (توکن ربات، آیدی کانال، کلید AI، آیدی عددی ادمین). این فایل هرگز نباید آپلود شود.

## تست و اجرا

    python main.py --check-sources
    python main.py --test-ai
    python main.py --test-telegram
    python main.py --once
    ./run.sh

برای توقف: `./stop.sh`

## پنل مدیریت

در چت خصوصی ربات `/start` بزنید. فقط شناسه `ADMIN_CHAT_ID` اجازه استفاده دارد.

## افزودن منبع

یک خط `Source(...)` به `sources.py` اضافه کنید و `python main.py --check-sources` بزنید.

## امنیت

کلیدها فقط در `.env` هستند. `.env`، دیتابیس و لاگ‌ها در `.gitignore` هستند.
