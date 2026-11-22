import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://campus:campus123@localhost:17754/campus_hours")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JWT_SECRET = os.getenv("JWT_SECRET", "campus-ta-hours-secret")
SHARED_DIR = os.getenv("SHARED_DIR", "/tmp/campus-ta-hours")
