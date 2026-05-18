import keyring
from typing import Optional

SERVICE_PREFIX = "PersonalFinanceApp"

class CredentialsStore:
    def save_bank_credential(self, bank: str, field: str, value: str) -> None:
        keyring.set_password(SERVICE_PREFIX, f"{bank}:{field}", value)

    def get_bank_credential(self, bank: str, field: str) -> Optional[str]:
        return keyring.get_password(SERVICE_PREFIX, f"{bank}:{field}")

    def save_llm_key(self, provider: str, api_key: str) -> None:
        keyring.set_password(SERVICE_PREFIX, f"llm:{provider}", api_key)

    def get_llm_key(self, provider: str) -> Optional[str]:
        return keyring.get_password(SERVICE_PREFIX, f"llm:{provider}")

credentials_store = CredentialsStore()
