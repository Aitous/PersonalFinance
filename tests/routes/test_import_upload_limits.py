from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from backend.routes import import_csv


@pytest.mark.asyncio
async def test_upload_size_limit(monkeypatch):
    monkeypatch.setattr(import_csv, "MAX_INBOX_FILE_BYTES", 4)
    assert await import_csv._read_uploaded_csv(UploadFile(file=BytesIO(b"1234"))) == b"1234"
    with pytest.raises(HTTPException) as error:
        await import_csv._read_uploaded_csv(UploadFile(file=BytesIO(b"12345")))
    assert error.value.status_code == 413
