import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
from backend.auth import hosted_auth_enabled
from backend.credentials import credentials_store

router = APIRouter()
CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"

class BankCredential(BaseModel):
    bank: str
    username: str
    password: str

class LLMConfig(BaseModel):
    provider: str
    api_key: str

@router.post("/settings/bank-credentials")
def save_bank_credentials(cred: BankCredential):
    if hosted_auth_enabled():
        raise HTTPException(status_code=404, detail="Bank credential sync is unavailable in hosted accounts; connect with Plaid")
    credentials_store.save_bank_credential(cred.bank, "username", cred.username)
    credentials_store.save_bank_credential(cred.bank, "password", cred.password)
    return {"status": "saved", "bank": cred.bank}

@router.get("/settings/banks")
def get_configured_banks():
    if hosted_auth_enabled():
        return {bank: False for bank in ["chase", "discover", "amex"]}
    banks = ["chase", "discover", "amex"]
    return {
        bank: credentials_store.get_bank_credential(bank, "username") is not None
        for bank in banks
    }

def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"llm_provider": "claude", "default_sync_days": 90}
    return json.loads(CONFIG_PATH.read_text())

@router.get("/settings/llm")
def get_llm_config():
    if hosted_auth_enabled():
        return {"provider": os.getenv("LLM_PROVIDER", "managed"), "managed": True}
    cfg = _read_config()
    return {"provider": cfg.get("llm_provider", "claude")}

@router.post("/settings/llm")
def save_llm_config(config: LLMConfig):
    if hosted_auth_enabled():
        raise HTTPException(status_code=404, detail="AI provider credentials are managed by the service")
    if config.provider not in {"claude", "gemini", "openai"}:
        raise HTTPException(status_code=400, detail="Unknown LLM provider")
    if not config.api_key.strip():
        raise HTTPException(status_code=400, detail="API key is required to change providers")
    credentials_store.save_llm_key(config.provider, config.api_key)
    cfg = _read_config()
    cfg["llm_provider"] = config.provider
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    return {"status": "saved", "provider": config.provider}
