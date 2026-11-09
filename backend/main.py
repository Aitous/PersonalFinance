import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.db.database import init_db
from backend.auth import authenticate_request, reset_current_owner, set_current_owner, hosted_auth_enabled
import backend.db.tenancy  # Register ORM tenant-scope hooks before serving requests.
from backend.routes.transactions import router as tx_router
from backend.routes.analysis import router as analysis_router
from backend.routes.sync import router as sync_router
from backend.routes.settings import router as settings_router
from backend.routes.import_csv import router as import_router
from backend.routes.search import router as search_router, _embed_all
from backend.routes.plaid import router as plaid_router
from backend.routes.account import router as account_router

app = FastAPI(title="PersonalFinance API", docs_url=None if hosted_auth_enabled() else "/docs",
              redoc_url=None if hosted_auth_enabled() else "/redoc",
              openapi_url=None if hosted_auth_enabled() else "/openapi.json")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

@app.middleware("http")
async def require_verified_identity(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    try:
        owner_id = await authenticate_request(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
    identity_token = set_current_owner(owner_id or None)
    try:
        return await call_next(request)
    finally:
        reset_current_owner(identity_token)

# Added after auth so CORS remains the outer middleware and also decorates
# unauthenticated 401 responses with the configured frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin] if hosted_auth_enabled() else [frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tx_router)
app.include_router(analysis_router)
app.include_router(sync_router)
app.include_router(settings_router)
app.include_router(import_router)
app.include_router(search_router)
app.include_router(plaid_router)
app.include_router(account_router)

@app.on_event("startup")
def startup():
    if hosted_auth_enabled():
        required = ("SUPABASE_URL", "DATABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "APP_ENCRYPTION_KEY", "LLM_PROVIDER", "FRONTEND_ORIGIN")
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise RuntimeError("Missing required hosted configuration: " + ", ".join(missing))
        if not os.environ["SUPABASE_URL"].startswith("https://") or not os.environ["FRONTEND_ORIGIN"].startswith("https://"):
            raise RuntimeError("SUPABASE_URL and FRONTEND_ORIGIN must use HTTPS in hosted mode")
        if len(os.environ["APP_ENCRYPTION_KEY"]) < 32:
            raise RuntimeError("APP_ENCRYPTION_KEY must contain at least 32 characters")
        provider_key = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}.get(os.environ["LLM_PROVIDER"].lower())
        if provider_key is None or not os.getenv(provider_key):
            raise RuntimeError("LLM_PROVIDER must be openai, gemini, or claude and its server API key must be configured")
    init_db()
    import threading
    # The existing local embedding sweep has no tenant parameter. Hosted
    # background work is started only by an owner-scoped API action.
    if not hosted_auth_enabled():
        threading.Thread(target=_embed_all, daemon=True).start()
    # Only persisted jobs created by an explicit request or successful import
    # are resumed. Startup never creates a new LLM job.
    if not hosted_auth_enabled():
        from backend.jobs.enrichment import resume_interrupted_jobs, run_job
        for job_id in resume_interrupted_jobs():
            threading.Thread(target=run_job, args=(job_id,), daemon=True).start()

@app.get("/health")
def health():
    return {"status": "ok"}
