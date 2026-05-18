from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db.database import init_db
from backend.routes.transactions import router as tx_router
from backend.routes.analysis import router as analysis_router
from backend.routes.sync import router as sync_router
from backend.routes.settings import router as settings_router

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

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok"}
