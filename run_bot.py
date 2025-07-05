# run_bot.py

import time
try:
    import keyboard  # type: ignore
    _HAS_KEYBOARD = True
except Exception:
    keyboard = None
    _HAS_KEYBOARD = False

from engine import BotConfig, TowerBot, load_regions

if __name__ == "__main__":
    cfg = BotConfig()
    load_regions(cfg)
    bot = TowerBot(cfg)
    bot.start()

    if _HAS_KEYBOARD:
        print("Press Ctrl+Alt+S to stop")
        keyboard.add_hotkey("ctrl+alt+s", bot.stop)
        keyboard.wait("ctrl+alt+s")
    else:
        print("Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            bot.stop()
