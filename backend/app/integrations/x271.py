"""X12 271 (eligibility & benefit response) parser.

A 271 from a commercial payer is not a flat "deductible / OOP" record — a Surest
(UnitedHealthcare) response, for example, carries ~700 EB segments: one per
covered procedure, per network side, per coverage level. This module turns that
into the structures the pre-auth flow actually grades against:

  · coverage      — active / inactive, plan name, plan period, group
  · accumulators  — out-of-pocket & deductible by coverage level / network /
                    time qualifier (Service Year, Year to Date, Remaining)
  · copays        — the per-procedure copay schedule, keyed by the payer's own
                    benefit description ("SPECIALTY TIER 2 DRUGS", "CAR T …")
  · limitations   — visit / quantity caps
  · oncology      — the copay lines that govern a cancer regimen

Nothing here is invented: every value is lifted from an EB segment in the
payer's own response. `benefitAmount` on an EB*B is the member's copay, on an
EB*G the out-of-pocket stop-loss, on an EB*C the deductible.
"""
from __future__ import annotations

import re

# EB01 — eligibility or benefit information codes
EB_ACTIVE = {"1", "2", "3", "4", "5"}
EB_INACTIVE = {"6", "7", "8"}
EB_DEDUCTIBLE = "C"
EB_COINSURANCE = "A"
EB_COPAY = "B"
EB_OOP = "G"
EB_LIMITATION = "F"
EB_NON_COVERED = "I"

# The benefit descriptions a payer uses for the lines that price cancer care.
# Ordered — the first match wins.
ONCOLOGY_PATTERNS = [
    (r"SPECIALTY TIER (\d+) DRUGS", "specialty_pharmacy"),
    (r"^TIER (\d+) DRUGS", "retail_pharmacy"),
    (r"PROVIDER ADMINISTERED DRUG TIER (\d+)", "provider_administered"),
    (r"CAR T THERAPY", "cellular_therapy"),
    (r"CANCER GENE AND CELLULAR THERAPY", "cellular_therapy"),
    (r"BONE MARROW (BIOPSY|HARVESTING|TRANSPLANT)", "procedure"),
    (r"SURGICAL BIOPSY", "procedure"),
    (r"(BONE|SOFT TISSUE|PROSTATE REMOVAL SURGERY FOR) CANCER", "cancer_surgery"),
    (r"CANCER SURGERY", "cancer_surgery"),
    (r"PREVENTIVE DRUGS", "retail_pharmacy"),
]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _desc(eb: dict) -> str:
    """The payer's own free-text description for this benefit line."""
    for ai in eb.get("additionalInformation") or []:
        d = (ai.get("description") or "").strip()
        if d:
            return d
    return ""


def _iso_date(d: str) -> str:
    """CCYYMMDD -> ISO. Returns '' for anything else."""
    d = (d or "").strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
    return ""


def _plan_period(resp: dict) -> dict:
    """planDateInformation.plan is 'CCYYMMDD-CCYYMMDD'."""
    raw = ((resp.get("planDateInformation") or {}).get("plan") or "").strip()
    a, _, b = raw.partition("-")
    return {"start": _iso_date(a), "end": _iso_date(b), "raw": raw}


def _coverage(resp: dict) -> dict:
    """Active-coverage state and the plan it names."""
    active, plan_details, service_types = None, "", []
    for ps in resp.get("planStatus") or []:
        code = str(ps.get("statusCode") or "")
        if active is None and code in EB_ACTIVE:
            active = True
        elif active is None and code in EB_INACTIVE:
            active = False
        if not plan_details and ps.get("planDetails"):
            plan_details = ps["planDetails"]
        for st in ps.get("serviceTypes") or []:
            if st not in service_types:
                service_types.append(st)

    insurance_type = ""
    for eb in resp.get("benefitsInformation") or []:
        if active is None and str(eb.get("code") or "") in EB_ACTIVE:
            active = True
        if not plan_details and eb.get("planCoverage"):
            plan_details = eb["planCoverage"]
        if not insurance_type and eb.get("insuranceType"):
            insurance_type = eb["insuranceType"]

    return {"active": active, "plan_name": plan_details,
            "insurance_type": insurance_type, "service_types": service_types}


def _accumulators(resp: dict) -> list[dict]:
    """Every EB*G (out-of-pocket stop-loss) and EB*C (deductible) segment.

    A plan reports the same accumulator three ways — Service Year (the limit),
    Year to Date (spent) and Remaining — for each of individual/family and
    in/out of network. All of them are kept; `pick_accumulator` selects one.
    """
    out = []
    for eb in resp.get("benefitsInformation") or []:
        code = str(eb.get("code") or "").upper()
        if code not in (EB_OOP, EB_DEDUCTIBLE):
            continue
        amount = _num(eb.get("benefitAmount"))
        if amount is None:
            continue
        out.append({
            "kind": "out_of_pocket" if code == EB_OOP else "deductible",
            "amount": amount,
            "coverage_level": eb.get("coverageLevel") or "",
            "network": eb.get("inPlanNetworkIndicator") or "",
            "time_qualifier": eb.get("timeQualifier") or "",
            "service_types": eb.get("serviceTypes") or [],
        })
    return out


def pick_accumulator(accums: list[dict], kind: str, *, level: str = "Individual",
                     network: str = "Yes", period: str = "Service Year"):
    """One accumulator figure, or None when the payer did not report it."""
    for a in accums:
        if (a["kind"] == kind and a["coverage_level"] == level
                and a["network"] == network and a["time_qualifier"] == period):
            return a["amount"]
    return None


def _copays(resp: dict) -> list[dict]:
    """The per-procedure copay schedule (EB*B), deduplicated.

    A plan of this shape lists the same description more than once — the copay
    differs by network side and by place of service (e.g. a $675 facility copay
    and a $100 office copay for the same drug tier). Every distinct line is kept
    with its own amount so the caller can choose the site of care.
    """
    rows, seen = [], set()
    for eb in resp.get("benefitsInformation") or []:
        if str(eb.get("code") or "").upper() != EB_COPAY:
            continue
        amount = _num(eb.get("benefitAmount"))
        if amount is None:
            continue
        desc = _desc(eb)
        key = (desc, amount, eb.get("inPlanNetworkIndicator"),
               ",".join(eb.get("serviceTypes") or []), eb.get("coverageLevel"))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "description": desc,
            "amount": amount,
            "network": eb.get("inPlanNetworkIndicator") or "",
            "coverage_level": eb.get("coverageLevel") or "",
            "service_types": eb.get("serviceTypes") or [],
        })
    return rows


def _limitations(resp: dict) -> list[dict]:
    out = []
    for eb in resp.get("benefitsInformation") or []:
        if str(eb.get("code") or "").upper() != EB_LIMITATION:
            continue
        out.append({
            "description": _desc(eb),
            "quantity": _num(eb.get("benefitQuantity")),
            "unit": eb.get("quantityQualifier") or "",
            "time_qualifier": eb.get("timeQualifier") or "",
            "network": eb.get("inPlanNetworkIndicator") or "",
            "service_types": eb.get("serviceTypes") or [],
        })
    return out


def _classify(description: str) -> tuple[str, str]:
    """(category, tier) for a benefit description that governs cancer care."""
    d = (description or "").upper()
    for pattern, category in ONCOLOGY_PATTERNS:
        m = re.search(pattern, d)
        if not m:
            continue
        tier = m.group(1) if m.groups() and (m.group(1) or "").isdigit() else ""
        return category, tier
    return "", ""


def _oncology(copays: list[dict]) -> list[dict]:
    """The copay lines that price a cancer regimen, in-network first."""
    out = []
    for row in copays:
        category, tier = _classify(row["description"])
        if not category:
            continue
        out.append({**row, "category": category,
                    "tier": int(tier) if tier else None})
    out.sort(key=lambda r: (r["category"], r["tier"] is None,
                            r["tier"] or 0, r["network"] != "Yes", r["amount"]))
    return out


def cost_share_for(oncology: list[dict], category: str, tier: int | None = None,
                   *, network: str = "Yes", site: str = "office") -> dict | None:
    """The member copay for one benefit category, at a site of care.

    A tier that lists two in-network amounts is priced by place of service: the
    lower is the office/clinic copay, the higher the hospital-outpatient one.
    `site` picks between them; the payer does not label which is which, so the
    ordering — not a guess at the code — is what selects it.
    """
    def _side(r):
        return r["network"] == network or r["network"] == "Not Applicable"

    rows = [r for r in oncology
            if r["category"] == category and _side(r)
            and (tier is None or r["tier"] == tier)]
    if not rows:
        return None
    rows.sort(key=lambda r: r["amount"])
    row = rows[0] if site == "office" else rows[-1]
    return {**row, "site": site,
            "alternatives": [r["amount"] for r in rows]}


def parse(resp: dict) -> dict:
    """Parse a 271 into the structures the pre-auth flow grades against."""
    sub = resp.get("subscriber") or {}
    payer = resp.get("payer") or {}
    provider = resp.get("provider") or {}
    cov = _coverage(resp)
    accums = _accumulators(resp)
    copays = _copays(resp)
    errors = resp.get("errors") or sub.get("aaaErrors") or []

    return {
        "member": {
            "first_name": sub.get("firstName", ""),
            "last_name": sub.get("lastName", ""),
            "member_id": sub.get("memberId", ""),
            "group_number": sub.get("groupNumber", "")
                            or (resp.get("planInformation") or {}).get("groupNumber", ""),
            "dob": _iso_date(sub.get("dateOfBirth", "")),
            "gender": sub.get("gender", ""),
            "address": sub.get("address") or {},
            "relationship": sub.get("entityIdentifier", ""),
        },
        "payer": {
            "name": payer.get("name", ""),
            "payer_id": payer.get("payorIdentification", "")
                        or resp.get("tradingPartnerServiceId", ""),
        },
        "provider": {
            "name": provider.get("providerName", ""),
            "npi": provider.get("npi", ""),
        },
        "coverage": {**cov, "plan_period": _plan_period(resp)},
        "accumulators": accums,
        "copays": copays,
        "limitations": _limitations(resp),
        "oncology": _oncology(copays),
        "errors": [{"code": e.get("code"),
                    "description": e.get("description"),
                    "resolution": (e.get("possibleResolutions") or "").split("\n")[0]}
                   for e in errors],
        "trace": (resp.get("meta") or {}).get("traceId", ""),
        "control_number": resp.get("controlNumber", ""),
        "eligibility_search_id": resp.get("eligibilitySearchId", ""),
        "application_mode": (resp.get("meta") or {}).get("applicationMode", ""),
        "segment_count": len(resp.get("benefitsInformation") or []),
    }


def summarise(parsed: dict) -> dict:
    """The flat projection the coverage analysis reads."""
    a = parsed["accumulators"]
    return {
        "active": parsed["coverage"]["active"],
        "plan_name": parsed["coverage"]["plan_name"],
        "plan_type": parsed["coverage"]["insurance_type"],
        "oop_max": pick_accumulator(a, "out_of_pocket"),
        "oop_spent": pick_accumulator(a, "out_of_pocket", period="Year to Date"),
        "oop_remaining": pick_accumulator(a, "out_of_pocket", period="Remaining"),
        "oop_max_family": pick_accumulator(a, "out_of_pocket", level="Family"),
        "oop_remaining_family": pick_accumulator(a, "out_of_pocket", level="Family",
                                                 period="Remaining"),
        "oop_max_oon": pick_accumulator(a, "out_of_pocket", network="No"),
        "deductible": pick_accumulator(a, "deductible"),
    }
