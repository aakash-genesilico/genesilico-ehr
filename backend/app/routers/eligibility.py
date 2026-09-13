"""Eligibility: the payer-specific intake form, and the real 270/271 call.

The form is not cosmetic. Which identifiers a payer will match on differs by
plan family — a Medicare MBI, a BlueCard alpha prefix, a TRICARE sponsor SSN
and a commercial member ID are not interchangeable, and sending the wrong one
returns an AAA rejection. `app.payer.forms` encodes those rules and maps the
captured values onto the 270 through each field's `x12` annotation.
"""
import json
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .. import config
from ..errors import ApiError, Unconfigured, UpstreamError
from ..integrations import stedi
from ..payer import forms as payer_forms
from ..services import benefits

from .. import schemas as S

router = APIRouter(prefix="/eligibility", tags=["eligibility"])

# A stored production 271. Lets the benefits screens be exercised without
# spending a billable transaction against a live payer.
REPLAY_DIR = Path(config.DATA_DIR)


@router.get("/form", responses={200: {"model": S.PolicyForm}, **S.ERRORS})
async def get_form(
    insurer: str = Query("", description="Payer name as the user typed it"),
    payer_id: str = Query("", description="Stedi trading partner service id"),
    plan_type: str = Query(""),
):
    """The payer-specific field schema the UI renders."""
    rec = None
    if config.STEDI_API_KEY and (insurer or payer_id):
        try:
            hits = await stedi.search_payers(insurer or payer_id, 5)
            rec = next((h for h in hits if h.get("payer_id") == payer_id), hits[0] if hits else None)
        except Exception:
            rec = None  # the form still builds without a resolved payer
    payer = payer_forms.normalise_payer(rec, insurer=insurer, payer_id=payer_id)
    return payer_forms.build_form(payer, plan_type=plan_type)


class RunRequest(BaseModel):
    insurer: str = ""
    payer_id: str = ""
    plan_type: str = ""
    values: dict = Field(default_factory=dict)
    service_type_codes: list[str] = Field(default_factory=lambda: ["30"])
    lines: list[dict] = Field(default_factory=list)
    network: str = "in"
    # Replay a stored 271 instead of calling the payer. Never silently on.
    replay: str | None = None


@router.post("/run", responses={200: {"model": S.EligibilityRun}, **S.ERRORS})
async def run(req: RunRequest):
    """Validate the form, then either call the payer or replay a stored 271."""
    rec = None
    if config.STEDI_API_KEY and (req.insurer or req.payer_id):
        try:
            hits = await stedi.search_payers(req.insurer or req.payer_id, 5)
            rec = next((h for h in hits if h.get("payer_id") == req.payer_id), hits[0] if hits else None)
        except Exception:
            rec = None
    payer = payer_forms.normalise_payer(rec, insurer=req.insurer, payer_id=req.payer_id)
    form = payer_forms.build_form(payer, plan_type=req.plan_type or req.values.get("plan_type", ""))
    values = payer_forms.normalise_values(form, req.values)
    errors = payer_forms.validate(form, values)
    if errors:
        raise ApiError("The policy form is incomplete.", status=422,
                       code="form_invalid", detail={"errors": errors})

    if req.replay:
        raw = _load_replay(req.replay)
        source = {"kind": "replay", "file": req.replay}
    else:
        if not config.STEDI_API_KEY:
            raise Unconfigured("Stedi eligibility", "Set STEDI_API_KEY in backend/.env")
        params = payer_forms.to_eligibility(form, values)
        params.setdefault("provider_npi", config.PROVIDER_NPI or None)
        params.setdefault("provider_name", config.PROVIDER_NAME)
        params["service_type_codes"] = req.service_type_codes
        params = {k: v for k, v in params.items() if v}
        try:
            result = await stedi.check_eligibility(params)
        except Exception as exc:
            raise UpstreamError("stedi", str(exc)) from exc
        raw = result.get("raw_271") or result
        source = {"kind": "live", "mode": config.stedi_mode()}

    parsed = benefits.parse(raw)
    payload = {"source": source, "benefits": parsed}
    if req.lines:
        payload["estimate"] = benefits.estimate(req.lines, parsed, network=req.network)
    return payload


@router.get("/replays", responses={200: {"model": S.ReplayList}})
async def replays():
    """Stored 271 responses available for replay."""
    out = []
    for p in sorted(REPLAY_DIR.glob("271-*.json")):
        try:
            parsed = benefits.parse(json.loads(p.read_text()))
        except Exception:
            continue
        out.append({
            "file": p.name,
            "payer": parsed["payer"]["name"],
            "member_id": parsed["member"]["member_id"],
            "name": f"{parsed['member']['first_name']} {parsed['member']['last_name']}".title(),
            "plan": parsed["plan"]["name"],
            "mode": parsed["mode"],
            "entries": parsed["entry_count"],
        })
    return {"count": len(out), "results": out}


def _load_replay(name: str) -> dict:
    path = REPLAY_DIR / Path(name).name          # no traversal
    if not path.exists():
        raise ApiError(f"No stored 271 named {name}", status=404)
    return json.loads(path.read_text())
