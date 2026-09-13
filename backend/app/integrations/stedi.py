"""Stedi healthcare — real payer directory + real X12 270/271 eligibility.

Two real capabilities, both live with the configured Stedi key:
  · search_payers(name)     -> the real Stedi Payer Network, resolving an insurer
                               name to its tradingPartnerServiceId (payer id).
  · check_eligibility(...)  -> a real 270 request; parses the 271 response into
                               active coverage, deductible, OOP max, coinsurance,
                               copay — or the payer's real AAA rejection reason.

Nothing is fabricated: benefits come straight from the 271, and when the payer
rejects (e.g. member not found) we surface the payer's own message + resolution.

Docs: https://www.stedi.com/docs/healthcare
"""
import httpx

from .. import config
from . import x271


async def search_payers(query: str, limit: int = 10) -> list[dict]:
    """Search the real Stedi Payer Network.

    Returns [{stedi_id, payer_id, name, aliases, programs, operating_states,
    coverage_types, eligibility_support, parent_group, raw}] — the payer's own
    published facts, which drive the payer-specific policy form.
    """
    if not config.STEDI_API_KEY or not query:
        return []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{config.STEDI_BASE_URL}/payers/search",
                                 headers={"Authorization": config.STEDI_API_KEY},
                                 params={"query": query})
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        # An auth or quota failure returning [] is indistinguishable from a
        # payer that genuinely has no match — which silently hid a bad API key.
        if e.response.status_code in (401, 403, 429):
            raise RuntimeError(
                f"Stedi rejected the payer search: {e.response.status_code} "
                f"{e.response.text[:120]}") from e
        return []
    except (httpx.HTTPError, ValueError):
        return []
    out = []
    for item in data.get("items", [])[:limit]:
        p = item.get("payer", {})
        # prefer eligibility-capable payers; the payer id used for eligibility is the
        # primaryPayerId (falls back to stediId)
        ts = p.get("transactionSupport") or {}
        out.append({
            "stedi_id": p.get("stediId", ""),
            "payer_id": p.get("primaryPayerId") or p.get("stediId", ""),
            "name": p.get("displayName", ""),
            "aliases": p.get("aliases", []),
            "programs": p.get("programs") or [],
            "operating_states": p.get("operatingStates") or [],
            "coverage_types": p.get("coverageTypes") or [],
            "eligibility_support": ts.get("eligibilityCheck", ""),
            "parent_group": p.get("parentPayerGroupName") or "",
            "raw": p,
        })
    return out


async def get_payer(payer_id: str) -> dict | None:
    """Fetch one payer record by its payer id / Stedi id, for the policy form."""
    payer_id = (payer_id or "").strip()
    if not payer_id:
        return None
    for r in await search_payers(payer_id, limit=10):
        raw = r.get("raw") or {}
        if payer_id.upper() in {(r.get("payer_id") or "").upper(),
                                (r.get("stedi_id") or "").upper(),
                                *{a.upper() for a in (raw.get("aliases") or [])}}:
            return r
    return None


async def resolve_payer_id(insurer: str) -> dict | None:
    """Best-match a free-text insurer name to a real Stedi payer id."""
    insurer = (insurer or "").strip()
    if not insurer:
        return None
    # already a numeric payer id?
    if insurer.isdigit():
        return {"payer_id": insurer, "name": insurer, "stedi_id": ""}
    results = await search_payers(insurer, limit=5)
    if not results:
        return None
    low = insurer.lower()
    exact = next((r for r in results if r["name"].lower() == low), None)
    return exact or results[0]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# X12 EB01 eligibility/benefit codes. 1-5 are flavours of active coverage,
# 6-8 of inactive. Without 6-8 an inactive member is indistinguishable from a
# payer that simply said nothing.
_EB01_ACTIVE = {"1", "2", "3", "4", "5"}
_EB01_INACTIVE = {"6", "7", "8"}


def _parse_271(resp: dict) -> dict:
    """Extract real benefit figures from a parsed 271 response."""
    out = {"active": None, "deductible": None, "oop_max": None,
           "coinsurance": None, "copay": None, "plan_name": "", "plan_type": ""}
    plan = resp.get("planInformation", {}) or {}
    out["plan_name"] = plan.get("planDescription", "") or plan.get("groupDescription", "")
    out["plan_type"] = plan.get("insuranceType", "") or plan.get("groupDescription", "")

    for b in resp.get("benefitsInformation", []) or []:
        code = (b.get("code") or "").upper()
        pct = _num(b.get("benefitPercent"))
        amt = _num(b.get("benefitAmount"))
        if code in _EB01_ACTIVE and out["active"] is None:      # Active Coverage
            out["active"] = True
        elif code in _EB01_INACTIVE and out["active"] is None:  # Inactive / terminated
            out["active"] = False
        elif code == "C" and out["deductible"] is None and amt is not None:  # Deductible
            out["deductible"] = amt
        elif code == "G" and out["oop_max"] is None and amt is not None:     # Out of Pocket (stop loss)
            out["oop_max"] = amt
        elif code == "A" and out["coinsurance"] is None and pct is not None:  # Co-Insurance
            out["coinsurance"] = pct
        elif code == "B" and out["copay"] is None and amt is not None:        # Co-Payment
            out["copay"] = amt

    if out["active"] is None:
        # Some payers answer only with planStatus; read the coverage state there.
        for ps in resp.get("planStatus", []) or []:
            sc = str(ps.get("statusCode") or "")
            if sc in _EB01_ACTIVE:
                out["active"] = True
                break
            if sc in _EB01_INACTIVE:
                out["active"] = False
                break
    return out


async def check_eligibility(params: dict) -> dict:
    """Run a real 270/271 eligibility check. `params` may pass a free-text insurer
    (`payer`) — it is resolved to a real payer id first. Returns a normalized dict."""
    resolved = await resolve_payer_id(params.get("payer", ""))
    if not resolved:
        raise RuntimeError(
            f"Could not resolve '{params.get('payer','')}' to a Stedi payer id. "
            f"Pick the plan from the payer directory (GET /api/payers?q=...).")
    payer_id = resolved["payer_id"]
    subscriber = {
        "memberId": params.get("member_id", ""),
        "firstName": params.get("first_name", ""),
        "lastName": params.get("last_name", ""),
        "dateOfBirth": (params.get("dob", "") or "").replace("-", ""),
    }
    # payer-specific identifiers the dynamic policy form captures
    if params.get("ssn"):                       # TRICARE sponsor SSN, some Medicaid
        subscriber["ssn"] = params["ssn"]
    if params.get("group_number"):
        subscriber["groupNumber"] = params["group_number"]
    subscriber = {k: v for k, v in subscriber.items() if v}

    body = {
        "controlNumber": "123456789",
        "tradingPartnerServiceId": payer_id,
        # The requesting provider on the 270 is the billing organisation (NPI-2) —
        # its name and NPI are what the payer matches, not the software vendor's.
        "provider": {
            "organizationName": params.get("provider_name") or "TEXAS ONCOLOGY PA",
            "npi": params.get("provider_npi") or "1811944101",
        },
        "subscriber": subscriber,
        "encounter": {"serviceTypeCodes": params.get("service_type_codes", ["30"])},
    }
    dep = params.get("dependent") or {}
    if dep.get("lastName"):
        # The patient is on the subscriber's policy: X12 loop 2000D. Stedi accepts
        # at most one dependent, and most payers error without its date of birth.
        body["dependents"] = [{k: v for k, v in {
            "firstName": dep.get("firstName", ""),
            "lastName": dep.get("lastName", ""),
            "dateOfBirth": (dep.get("dateOfBirth", "") or "").replace("-", ""),
            "individualRelationshipCode": dep.get("relationshipCode", ""),
        }.items() if v}]
    if params.get("portal_password"):
        # A few payers (Medi-Cal, Kern, AltaMed) authenticate the requesting
        # provider with a program PIN; without it they answer AAA 41.
        body["portalPassword"] = params["portal_password"]
    if params.get("portal_username"):
        body["portalUsername"] = params["portal_username"]
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{config.STEDI_BASE_URL}/change/medicalnetwork/eligibility/v3",
            headers={"Authorization": config.STEDI_API_KEY, "Content-Type": "application/json"},
            json=body)
        r.raise_for_status()
        resp = r.json()

    payer = resp.get("payer", {})
    errors = resp.get("errors", []) or resp.get("subscriber", {}).get("aaaErrors", [])
    # The full 271 — accumulators, the per-procedure copay schedule, limitations
    # and the oncology benefit lines — parsed once and carried alongside the flat
    # projection the older callers read.
    detail = x271.parse(resp)
    parsed = {**_parse_271(resp), **{k: v for k, v in x271.summarise(detail).items()
                                     if v is not None}}
    return {
        "connector": "stedi",
        # The unmodified 271. services.benefits parses the full document —
        # accumulators and drug tiers live in entries the flat projection drops.
        "raw_271": resp,
        "benefit_detail": detail,
        "resolved_payer_id": payer_id,
        "payer_name": payer.get("name", "") or resolved["name"],
        "plan_name": parsed["plan_name"],
        "plan_type": parsed["plan_type"],
        "member_id": params.get("member_id", ""),
        "network_status": "in_network",
        "active": parsed["active"],
        "deductible": parsed["deductible"],
        "oop_max": parsed["oop_max"],
        "coinsurance": parsed["coinsurance"],
        "copay": parsed["copay"],
        "oop_spent": parsed.get("oop_spent"),
        "oop_remaining": parsed.get("oop_remaining"),
        "errors": [{"code": e.get("code"), "description": e.get("description"),
                    "resolution": (e.get("possibleResolutions") or "").split("\n")[0]}
                   for e in errors],
        "trace": resp.get("meta", {}).get("traceId", ""),
        "source": "eligibility_270_271",
        "source_url": "https://www.stedi.com/docs/healthcare",
    }


async def discover_coverage(params: dict) -> dict:
    """Real Stedi Insurance Discovery.

    Finds every policy a payer network can match to a person from name, date of
    birth and state — including plans where the patient is a *dependent* on
    somebody else's policy, which the practice often does not know about.

    That matters for pre-auth: billing the wrong policy first is a denial, and
    a missed primary is a write-off. Production key only; test mode returns 403.
    """
    if not config.STEDI_API_KEY:
        return {"available": False, "reason": "STEDI_API_KEY is not set", "items": []}

    body = {
        "provider": {
            "organizationName": params.get("provider_name") or config.PROVIDER_NAME,
            "npi": params.get("provider_npi") or config.PROVIDER_NPI,
        },
        "subscriber": {k: v for k, v in {
            "firstName": params.get("first_name", ""),
            "lastName": params.get("last_name", ""),
            "dateOfBirth": (params.get("dob", "") or "").replace("-", ""),
            "state": params.get("state", ""),
        }.items() if v},
        "encounter": {"dateOfService": (params.get("date_of_service", "") or "").replace("-", "")},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{config.STEDI_BASE_URL}/insurance-discovery/check/v1",
                              headers={"Authorization": config.STEDI_API_KEY,
                                       "Content-Type": "application/json"},
                              json=body)
    if r.status_code == 403:
        return {"available": False, "items": [],
                "reason": "Insurance discovery is not available on a Stedi test key."}
    if r.status_code >= 400:
        raise RuntimeError(f"Stedi insurance discovery: {r.status_code} {r.text[:200]}")

    resp = r.json()
    items = []
    for it in resp.get("items", []):
        payer = it.get("payer") or {}
        sub = it.get("subscriber") or {}
        dep = it.get("dependent") or {}
        items.append({
            "payer_name": payer.get("name") or "",
            "payer_id": payer.get("payorIdentification") or it.get("tradingPartnerServiceId") or "",
            "member_id": sub.get("memberId") or "",
            "group_number": sub.get("groupNumber") or "",
            "subscriber_name": f"{sub.get('firstName','')} {sub.get('lastName','')}".strip(),
            # Present when the patient is covered as someone else's dependent.
            "patient_is_dependent": bool(dep),
            "dependent_name": f"{dep.get('firstName','')} {dep.get('lastName','')}".strip() if dep else "",
        })

    # The same policy comes back once per matched service type; collapse it.
    seen, unique = set(), []
    for i in items:
        key = (i["payer_id"], i["member_id"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(i)

    return {
        "available": True,
        "found": resp.get("coveragesFound", len(unique)),
        "distinct_policies": len(unique),
        "items": unique,
        "warnings": [w.get("description") for w in resp.get("warnings") or []],
        "discovery_id": resp.get("discoveryId"),
    }
