"""Environment-driven settings.

Every credential is read from the environment. Nothing is defaulted to a
working value — a missing key makes the corresponding capability report itself
as unconfigured rather than quietly returning invented data.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# backend/.env first, then the frontend .env one level up so the Ontada client
# id / FHIR base are declared in exactly one place.
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env", override=False)


def _clean(v: str) -> str:
    """Strip quotes and whitespace; treat obvious placeholders as unset."""
    v = (v or "").strip().strip('"').strip("'")
    if v.lower().startswith(("your-", "your_", "changeme", "<")):
        return ""
    return v


# ---------------------------------------------------------------- app
APP_ENV = os.getenv("APP_ENV", "local")
PORT = int(os.getenv("BACKEND_PORT", "8080"))
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3045").split(",") if o.strip()
]

# SQLite locally; point DATABASE_URL at Postgres and nothing else changes.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR / 'ehr.db'}")

# ---------------------------------------------------------------- Stedi
STEDI_API_KEY = _clean(os.getenv("STEDI_API_KEY", ""))
STEDI_BASE_URL = os.getenv("STEDI_BASE_URL", "https://healthcare.us.stedi.com/2024-04-01")

# The provider identity sent on every 270. Must be a real NPI the payer accepts.
PROVIDER_NPI = _clean(os.getenv("PROVIDER_NPI", ""))
PROVIDER_NAME = os.getenv("PROVIDER_NAME", "GeneSilico")

# ---------------------------------------------------------------- Ontada
ONTADA_CLIENT_ID = _clean(os.getenv("ONTADA_CLIENT_ID", "") or os.getenv("NEXT_PUBLIC_ONTADA_CLIENT_ID", ""))
ONTADA_CLIENT_SECRET = _clean(os.getenv("ONTADA_CLIENT_SECRET", ""))
ONTADA_FHIR_BASE = _clean(
    os.getenv("ONTADA_FHIR_BASE", "") or os.getenv("NEXT_PUBLIC_ONTADA_FHIR_BASE_URL", "")
)
ONTADA_REDIRECT_URI = os.getenv("ONTADA_REDIRECT_URI", "http://localhost:8080/api/ontada/callback")
# "symmetric" (client secret) | "asymmetric" (private_key_jwt) | "" = auto-detect
ONTADA_CLIENT_AUTH = os.getenv("ONTADA_CLIENT_AUTH", "")
# Exact scope string to request, overriding the derived set. A registration
# grants a fixed list and the authorization server rejects the whole request
# with [invalid_scope] if you ask for one element outside it — there is no
# partial grant. Set this to what the registration actually carries.
ONTADA_SCOPES = _clean(os.getenv("ONTADA_SCOPES", ""))

# Where the browser lands after the OAuth dance completes.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3045")


def stedi_mode() -> str:
    """'test' | 'production' | 'unconfigured' — inferred from the key prefix."""
    if not STEDI_API_KEY:
        return "unconfigured"
    return "test" if STEDI_API_KEY.startswith("test_") else "production"
