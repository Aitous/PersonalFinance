from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db.database import init_db
from backend.routes.transactions import router as tx_router
from backend.routes.analysis import router as analysis_router
from backend.routes.sync import router as sync_router
from backend.routes.settings import router as settings_router
from backend.routes.import_csv import router as import_router
from backend.routes.search import router as search_router, _embed_all

app = FastAPI(title="PersonalFinance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tx_router)
app.include_router(analysis_router)
app.include_router(sync_router)
app.include_router(settings_router)
app.include_router(import_router)
app.include_router(search_router)

@app.on_event("startup")
def startup():
    init_db()
    import threading
    threading.Thread(target=_embed_all, daemon=True).start()
    # Only persisted jobs created by an explicit request or successful import
    # are resumed. Startup never creates a new LLM job.
    from backend.jobs.enrichment import resume_interrupted_jobs, run_job
    for job_id in resume_interrupted_jobs():
        threading.Thread(target=run_job, args=(job_id,), daemon=True).start()

@app.get("/health")
def health():
    return {"status": "ok"}
