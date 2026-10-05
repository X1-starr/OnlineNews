import threading
import time

S = {
    "started": time.time(), "last_cycle": None, "last_cycle_secs": None,
    "next_cycle": None, "cycle_running": False, "source_health": {},
    "last_error": "", "wipe_request": False,
}
RUN_NOW = threading.Event()
