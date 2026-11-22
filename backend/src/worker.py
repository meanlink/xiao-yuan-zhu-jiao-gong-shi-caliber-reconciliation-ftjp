import os
import time
from pathlib import Path
import redis
from .config import REDIS_URL, SHARED_DIR

os.makedirs(SHARED_DIR, exist_ok=True)
client = redis.from_url(REDIS_URL)
path = Path(SHARED_DIR) / "worker-heartbeat"
while True:
    path.write_text(str(time.time()))
    try:
        client.set("campus-ta-hours:worker", "alive", ex=30)
    except Exception:
        pass
    time.sleep(5)
