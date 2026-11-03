"""
Thin client for the real TypeSafe System One API (Jev), used by matching.py to
adjudicate menu-item pairs that cheap string similarity can't confidently call.

Deliberately stdlib-only (urllib), matching the rest of this repo's HTTP code —
the plan file for this project (and this portfolio's standing notes) record that
`requests` hangs against some hosts in this dev sandbox while `urllib.request`
and `curl` work fine; there is no reason to risk that here too.

API contract (read from the live docs, https://docs.typesafe.ai/api.md and
https://docs.typesafe.ai/primitives/noul.md, 2026-11-03):
  POST https://api.typesafe.ai/v1/systemone
  Authorization: Bearer <API_KEY>
  body: {"model": "jev-latest", "state": <context>, "questions": {id: {"type": "noul",
         "instructions": ..., "criteria": {"true": ..., "false": ...}}}}
  response: {"answers": {id: {"type": "noul", "noul": <0..1 probability-of-yes>}}}
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
TIMEOUT_SECONDS = 30
ENV_VAR = "TYPESAFE_API_KEY"
DOTENV_PATH = os.path.expanduser("~/products/.env")
DOTENV_KEY_NAME = "typesafe_api_key"


class JevError(RuntimeError):
    """Raised when the TypeSafe API can't be reached or answers unexpectedly."""


def _load_api_key() -> str:
    """Real API key, never hardcoded here. Primary: TYPESAFE_API_KEY env var.
    Fallback (documented portfolio convention): ~/products/.env's
    `typesafe_api_key=...` line, read fresh each time rather than cached."""
    env_value = os.environ.get(ENV_VAR)
    if env_value:
        return env_value

    if os.path.isfile(DOTENV_PATH):
        with open(DOTENV_PATH, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip() == DOTENV_KEY_NAME:
                    value = value.strip().strip('"').strip("'")
                    if value:
                        return value

    raise JevError(
        f"No TypeSafe API key found. Set {ENV_VAR} or add "
        f"`{DOTENV_KEY_NAME}=...` to {DOTENV_PATH}."
    )


def ask_noul_batch(state: str, questions: dict[str, dict]) -> dict[str, float]:
    """Send one real request with many Noul questions (cheap: they run in
    parallel server-side, per the docs) and return {question_id: noul_probability}.

    `questions` maps a caller-chosen id to {"instructions": ..., "criteria":
    {"true": ..., "false": ...} (optional)}.
    """
    if not questions:
        return {}

    api_key = _load_api_key()
    body = {
        "model": MODEL,
        "state": state,
        "questions": {
            qid: {"type": "noul", **q} for qid, q in questions.items()
        },
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status = resp.status
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise JevError(f"HTTP {exc.code} from TypeSafe API: {payload}") from exc

    if status != 200:
        raise JevError(f"HTTP {status} from TypeSafe API: {payload}")

    parsed = json.loads(payload)
    answers = parsed.get("answers", {})
    result: dict[str, float] = {}
    for qid in questions:
        answer = answers.get(qid)
        if not answer or "noul" not in answer:
            raise JevError(f"TypeSafe API response missing noul answer for {qid!r}: {parsed!r}")
        result[qid] = float(answer["noul"])
    return result
