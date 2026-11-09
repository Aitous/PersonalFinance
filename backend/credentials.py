import keyring
from typing import Optional

SERVICE_PREFIX = "PersonalFinanceApp"

class CredentialsStore:
    def save_bank_credential(self, bank: str, field: str, value: str) -> None:
        keyring.set_password(SERVICE_PREFIX, f"{bank}:{field}", value)

    def get_bank_credential(self, bank: str, field: str) -> Optional[str]:
        return keyring.get_password(SERVICE_PREFIX, f"{bank}:{field}")

    def delete_bank_credential(self, bank: str, field: str) -> None:
        try:
            keyring.delete_password(SERVICE_PREFIX, f"{bank}:{field}")
        except keyring.errors.PasswordDeleteError:
            pass

    def save_llm_key(self, provider: str, api_key: str) -> None:
        keyring.set_password(SERVICE_PREFIX, f"llm:{provider}", api_key)

    def get_llm_key(self, provider: str) -> Optional[str]:
        return keyring.get_password(SERVICE_PREFIX, f"llm:{provider}")

credentials_store = CredentialsStore()
