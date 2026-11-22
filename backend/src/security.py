import hashlib
from datetime import datetime, timedelta, timezone
from jose import jwt
from .config import JWT_SECRET

ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def create_token(user: dict) -> str:
    payload = {"sub": str(user["id"]), "email": user["email"], "role": user["role"], "name": user["name"], "exp": datetime.now(timezone.utc) + timedelta(hours=8)}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
