# run_bot.py

import time
from engine import BotConfig, TowerBot, load_regions

if __name__ == "__main__":
    cfg = BotConfig()
    load_regions(cfg)
    bot = TowerBot(cfg)
    bot.start()
    try:
        # keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot.stop()
