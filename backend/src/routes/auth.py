from fastapi import APIRouter, HTTPException
from ..schemas.auth import LoginRequest
from ..services.auth_service import find_user
from ..security import create_token, hash_password

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login(payload: LoginRequest):
    user = find_user(payload.email)
    if not user or user["password_hash"] != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="邮箱或密码不正确")
    return {"access_token": create_token(user), "token_type": "bearer", "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]}}
