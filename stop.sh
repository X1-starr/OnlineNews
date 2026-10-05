#!/data/data/com.termux/files/usr/bin/sh
pkill -f "python main.py" && echo "Stopped."
termux-wake-unlock 2>/dev/null
