# Local CSV Import Inbox Implementation Plan

> **For agentic workers:** Implement the two tasks below in order. Keep this flow local to the existing app; do not add a bank connection or cloud file access.

**Goal:** Let the user review CSVs placed in `transactions/inbox/` and explicitly confirm each import.

**Architecture:** Add safe, non-recursive inbox listing and preview/confirm endpoints to the existing CSV import router. The UI polls the inbox while Settings is open, previews one selected file, and confirms import only if its checksum still matches.

**Tech Stack:** FastAPI, SQLAlchemy, React, TypeScript.

**Spec:** Approved in-chat scope: a local inbox for downloaded CSVs, with preview, duplicate counts, and explicit confirmation before import.

## Global Constraints

- Read only direct `.csv` files inside the fixed `transactions/inbox/` directory.
- Reject symlinks, path traversal, unsupported extensions, and files over 25 MiB.
- Do not move a file or modify transactions during scan or preview.
- Confirmed imports use the existing parser, deduplication, import history, and enrichment pipeline.
- Keep the existing direct-upload path intact.

## Review Focus

- A file replaced after preview must be rejected by checksum validation.
- Unknown bank filenames must be reviewable after explicit bank selection.
- Invalid rows and duplicate-only files must not be silently imported.
- Archive name collisions must not overwrite an earlier statement.
- Empty or missing inbox directories must produce a useful empty state.

---

### Task 1: Safe local inbox API

**Files:**
- Modify: `backend/routes/import_csv.py`
- Modify: `frontend/src/api/client.ts`

- [x] Add inbox listing, preview, and confirm endpoints with strict basename, symlink, size, and checksum validation.
- [x] Route confirmed files through the existing import pipeline and archive without overwriting.
- [x] Add typed API client methods and response shapes.
- [x] Verify with Python compilation and `git diff --check`.

### Task 2: Inbox review UI

**Files:**
- Modify: `frontend/src/components/ImportWorkspace.tsx`
- Modify: `frontend/src/index.css`

- [x] Add a periodically refreshed inbox list and a manual refresh control.
- [x] Allow bank/account selection and preview of counts, sample transactions, warnings, and rejected rows.
- [x] Require a separate confirm action; show progress/errors; refresh import history and coverage after success.
- [x] Verify with the production frontend build and `git diff --check`.
