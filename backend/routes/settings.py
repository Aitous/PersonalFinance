import json
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel
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
    credentials_store.save_bank_credential(cred.bank, "username", cred.username)
    credentials_store.save_bank_credential(cred.bank, "password", cred.password)
    return {"status": "saved", "bank": cred.bank}

@router.get("/settings/banks")
def get_configured_banks():
    banks = ["chase", "discover", "amex"]
    return {
        bank: credentials_store.get_bank_credential(bank, "username") is not None
        for bank in banks
    }

@router.post("/settings/llm")
def save_llm_config(config: LLMConfig):
    credentials_store.save_llm_key(config.provider, config.api_key)
    cfg = json.loads(CONFIG_PATH.read_text())
    cfg["llm_provider"] = config.provider
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    return {"status": "saved", "provider": config.provider}

@router.get("/settings/llm")
def get_llm_config():
    cfg = json.loads(CONFIG_PATH.read_text())
    return {"provider": cfg.get("llm_provider", "claude")}
