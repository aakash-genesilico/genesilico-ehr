"""Capability report. The UI reads this to know what is actually wired."""
from fastapi import APIRouter

from .. import config
from ..integrations import ontada

from .. import schemas as S

router = APIRouter(tags=["health"])


@router.get("/health", responses={200: {"model": S.Health}})
async def health():
    return {"status": "ok", "env": config.APP_ENV}


@router.get("/capabilities", responses={200: {"model": S.Capabilities}, **S.ERRORS})
async def capabilities():
    """What this deployment can genuinely do, and what it cannot.

    Every `available: false` carries the reason, so a screen can say why a
    control is disabled instead of failing when it is pressed.
    """
    stedi_mode = config.stedi_mode()
    stedi_on = stedi_mode != "unconfigured"

    return {
        "stedi": {
            "mode": stedi_mode,
            "payer_search": {"available": stedi_on, "real": True},
            "eligibility_270_271": {
                "available": stedi_on,
                "real": True,
                "note": (
                    "Test keys answer only for Stedi's published fixture identities. "
                    "Production keys reach real payers and need real member IDs."
                ),
            },
            "claim_status_276_277": {
                "available": stedi_mode == "production",
                "reason": None if stedi_mode == "production" else "Blocked in Stedi test mode",
            },
            "insurance_discovery": {
                "available": stedi_mode == "production",
                "reason": None if stedi_mode == "production" else "Blocked in Stedi test mode",
            },
            "prior_auth_278": {
                "available": False,
                "reason": (
                    "Stedi exposes no X12 278 endpoint. Verified against both the test and "
                    "production key — every candidate path returns 404. Real prior-auth "
                    "submission needs a different clearinghouse, a payer portal, or Da Vinci PAS."
                ),
            },
        },
        "ontada": {
            "configured": ontada.configured(),
            "fhir_base": config.ONTADA_FHIR_BASE or None,
            "client_auth": ontada.auth_mode() if ontada.configured() else None,
            "grant_types": ["authorization_code"],
            "service_to_service": {
                "available": False,
                "reason": (
                    "The gateway advertises only authorization_code. A practitioner must "
                    "complete a browser login once; the refresh token then keeps the "
                    "backend running unattended."
                ),
            },
        },
        "cancerai_digital_twin": {
            "available": False,
            "reason": "Lives in gSage. No endpoint is wired into this module yet.",
        },
    }
