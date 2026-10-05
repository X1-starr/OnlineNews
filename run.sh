#!/data/data/com.termux/files/usr/bin/sh
cd "$(dirname "$0")" || exit 1
mkdir -p logs
termux-wake-lock 2>/dev/null
pkill -f "python main.py" 2>/dev/null
nohup python main.py >> logs/nohup.log 2>&1 &
echo "Started. Watch logs: tail -f logs/bot.log"
