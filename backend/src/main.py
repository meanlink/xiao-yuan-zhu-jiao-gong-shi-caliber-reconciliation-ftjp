from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import init_db
from .middlewares.rate_limit import rate_limit_middleware
from .middlewares.errors import error_middleware
from .routes import auth, classes, work_records, reports, dashboard, audit
from .services.auth_service import ensure_users

app = FastAPI(title="Campus TA Hours", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.middleware("http")(error_middleware)
app.middleware("http")(rate_limit_middleware)

@app.on_event("startup")
def startup():
    init_db()
    ensure_users()

@app.get("/health")
def health():
    return {"status": "ok", "service": "campus-ta-hours-backend"}

app.include_router(auth.router)
app.include_router(classes.router)
app.include_router(work_records.router)
app.include_router(reports.router)
app.include_router(dashboard.router)
app.include_router(audit.router)
