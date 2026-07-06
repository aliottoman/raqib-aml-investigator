"""
==============================================================================
 Raqib (رقيب) · AI-Assisted AML Operations on OCI Enterprise AI
 Author: Ali Ottoman | Oracle GenAI
==============================================================================

What this app does
------------------
* Provides a role-aware workbench for screening, case investigation, governed
  evidence review, and maker-checker SAR decisions.
* Uses OCI Responses API orchestration, Conversations, code_interpreter,
  optional xAI web_search, and Guardrails while keeping analysts in control of
  database access and final disposition.
* Persists case-scoped investigation events, approvals, notes, rule versions,
  and structured SAR drafts; exports English or Arabic PDFs.
* One process: `python app.py` serves the API and the built React UI.
"""

import uvicorn

import config
from src import bankdb
from src.api import app  # noqa: F401  (uvicorn target)

if __name__ == "__main__":
    bankdb.ensure_db()
    print(f"Raqib → http://localhost:{config.PORT}   "
          f"(live={'yes' if config.live_configured() else 'no — demo tape'})")
    uvicorn.run("src.api:app", host="0.0.0.0", port=config.PORT, reload=False)
