"""GeneSilico EHR backend.

Design rule for this service: never invent a clinical or financial value. If an
upstream cannot answer, the response says so — with the upstream's own message
and a resolution — rather than substituting a plausible number.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, db
from .errors import ApiError, api_error_handler, unhandled_handler
from .routers import admin, casebooks, eligibility, health, ontada, payers, preauth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("genesilico-ehr")

DESCRIPTION = """
Backend for the pre-authorisation workflow: pull a patient's record from the
EHR, price their planned treatment against their real insurance benefits, and
say plainly what cannot be done.

### The one design rule

**Never invent a clinical or financial value.** When an upstream cannot answer,
the response says so — with the upstream's own message and a resolution —
rather than substituting a plausible number. `GET /api/capabilities` is the
authoritative statement of what this deployment can actually do; the UI reads
it to disable controls instead of letting them fail when pressed.

### Three limits worth knowing before you integrate

* **There is no prior-authorisation submission.** X12 278 does not exist on
  Stedi — verified against both a test and a production key, every candidate
  path 404s. `POST /api/preauth/{id}/submit` therefore returns **501** with the
  reason rather than minting an authorisation number nobody issued.
* **Ontada cannot be reached server-to-server.** The gateway advertises
  `authorization_code` only, so a person completes a browser login once and the
  refresh token carries it from there. Endpoints that need it answer **428**
  `ontada_not_connected` until that happens.
* **Money is in cents**, always integers. Line arithmetic has to be exact.

### Errors

Every non-2xx response is the same envelope:

```json
{ "error": { "code": "unconfigured", "message": "…", "detail": { } } }
```

`code` is machine-readable; `message` preserves the upstream's own words,
because a payer saying "member not found" is the useful part of the response.
"""

TAGS = [
    {"name": "health", "description": "Liveness, and an honest report of what is wired."},
    {"name": "payers", "description": "The live Stedi payer network — resolve an insurer name to the "
                                       "trading-partner id an eligibility request needs."},
    {"name": "eligibility", "description": "The payer-specific intake form and the real X12 270/271. "
                                            "Which identifiers a payer matches on differs by plan family, "
                                            "and sending the wrong one earns an AAA rejection — the form "
                                            "schema encodes those rules."},
    {"name": "ontada", "description": "SMART on FHIR against Ontada / iKnowMed. Authorization-code only, "
                                       "so a human signs in once and offline_access keeps the backend "
                                       "running. The connection is PROVIDER-scoped: user/* reads the "
                                       "clinician's whole panel, and every read names its patient "
                                       "explicitly because the token carries no patient context."},
    {"name": "admin", "description": "Cancer centers and hospitals — this platform's own tenant "
                                      "configuration, not clinical data."},
    {"name": "casebooks", "description": "One patient's record, plus coverage discovery for them."},
    {"name": "preauth", "description": "Authorisation packages: billable lines, the payer's benefit "
                                        "response, and the resulting cost estimate."},
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="GeneSilico EHR API",
        version="0.1.0",
        summary="Ontada (iKnowMed) FHIR + Stedi eligibility for Texas Oncology.",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        contact={"name": "GeneSilico", "email": "developers@genesilico.ai"},
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        servers=[{"url": "http://localhost:8090", "description": "Local"}],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(Exception, unhandled_handler)

    for r in (health.router, payers.router, eligibility.router, ontada.router,
              admin.router, casebooks.router, preauth.router):
        app.include_router(r, prefix="/api")

    @app.on_event("startup")
    async def _startup() -> None:
        await db.init_db()
        log.info("stedi=%s ontada_configured=%s db=%s",
                 config.stedi_mode(), bool(config.ONTADA_CLIENT_ID),
                 config.DATABASE_URL.split("///")[-1])

    return app


app = create_app()
