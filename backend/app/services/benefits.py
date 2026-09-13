"""Parse a real X12 271 into something a pre-auth screen can use.

Written against a live UnitedHealthcare production response (701
`benefitsInformation` entries). Two things about real 271s break the naive
"read the first copay" approach that works on test fixtures:

  · A commercial plan can carry hundreds of copay lines. They differ by
    service type, by in/out-of-network, and by a free-text label in
    `additionalInformation` — for oncology that label is the drug tier
    ("PROVIDER ADMINISTERED DRUG TIER 9"). Picking the first is meaningless.

  · Accumulators come as several EB=G lines distinguished by `coverageLevel`
    (Individual/Family), network, and `timeQualifier` (Service Year / Year to
    Date / Remaining). The remaining figure is what actually caps a patient's
    exposure, and it is a different line from the annual maximum.

The 271 never says which tier a given HCPCS code sits in — that is a formulary
question. So this module surfaces the tier table and leaves the choice to the
caller rather than guessing.
"""
from __future__ import annotations

import re
from typing import Any

EB_ACTIVE = {"1", "2", "3", "4", "5"}
EB_INACTIVE = {"6", "7", "8"}

CODE_NAMES = {
    "A": "coinsurance", "B": "copay", "C": "deductible", "G": "out_of_pocket",
    "F": "limitation", "1": "active",
}

_TIER_RE = re.compile(r"\bTIER\s*(\d+)\b", re.I)


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _info(entry: dict) -> list[str]:
    return [a.get("description", "") for a in (entry.get("additionalInformation") or []) if a.get("description")]


def _network(entry: dict) -> str:
    """'in' | 'out' | 'na' — the payer's word, normalised."""
    return {"Yes": "in", "No": "out"}.get(entry.get("inPlanNetworkIndicator") or "", "na")


def parse(resp: dict) -> dict:
    """Full structured read of a 271."""
    entries = resp.get("benefitsInformation") or []
    sub = resp.get("subscriber") or {}
    errors = resp.get("errors") or sub.get("aaaErrors") or []

    return {
        "active": _active(resp, entries),
        "payer": {
            "name": (resp.get("payer") or {}).get("name"),
            "id": resp.get("tradingPartnerServiceId"),
        },
        "plan": _plan(resp, entries),
        "member": {
            "member_id": sub.get("memberId"),
            "group_number": sub.get("groupNumber") or (resp.get("planInformation") or {}).get("groupNumber"),
            "first_name": sub.get("firstName"),
            "last_name": sub.get("lastName"),
            "date_of_birth": sub.get("dateOfBirth"),
            "gender": sub.get("gender"),
            "address": sub.get("address"),
        },
        "accumulators": _accumulators(entries),
        "copays": _copays(entries),
        "drug_tiers": _drug_tiers(entries),
        "coinsurance": _coinsurance(entries),
        "deductibles": _deductibles(entries),
        "limitations": _limitations(entries),
        "referrals": _referrals(entries),
        "errors": [
            {"code": e.get("code"), "description": e.get("description"),
             "resolution": (e.get("possibleResolutions") or "").split("\n")[0]}
            for e in errors
        ],
        "trace_id": (resp.get("meta") or {}).get("traceId"),
        "search_id": resp.get("eligibilitySearchId"),
        "mode": (resp.get("meta") or {}).get("applicationMode"),
        "entry_count": len(entries),
    }


def _active(resp: dict, entries: list[dict]) -> bool | None:
    for ps in resp.get("planStatus") or []:
        sc = str(ps.get("statusCode") or "")
        if sc in EB_ACTIVE:
            return True
        if sc in EB_INACTIVE:
            return False
    for e in entries:
        code = str(e.get("code") or "")
        if code in EB_ACTIVE:
            return True
        if code in EB_INACTIVE:
            return False
    return None


def _plan(resp: dict, entries: list[dict]) -> dict:
    details = next((ps.get("planDetails") for ps in resp.get("planStatus") or [] if ps.get("planDetails")), None)
    period = (resp.get("planDateInformation") or {}).get("plan") or ""
    start, _, end = period.partition("-")
    fmt = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else None
    insurance_type = next((e.get("insuranceType") for e in entries if e.get("insuranceType")), None)
    return {
        "name": details,
        "insurance_type": insurance_type,
        "period_start": fmt(start),
        "period_end": fmt(end),
    }


def _accumulators(entries: list[dict]) -> list[dict]:
    """EB=G / EB=C accumulators, keyed so a UI can find 'individual, in-network,
    remaining' without re-deriving the X12 semantics."""
    out = []
    for e in entries:
        if e.get("code") not in ("G", "C"):
            continue
        amount = _num(e.get("benefitAmount"))
        if amount is None:
            continue
        out.append({
            "kind": "out_of_pocket" if e.get("code") == "G" else "deductible",
            "level": (e.get("coverageLevel") or "").lower() or "unknown",   # individual | family
            "network": _network(e),
            "basis": (e.get("timeQualifier") or "").lower() or "unknown",   # service year | year to date | remaining
            "amount": amount,
            "service_types": e.get("serviceTypes") or [],
        })
    return out


def find_accumulator(accs: list[dict], kind: str, level: str, network: str, basis: str) -> float | None:
    for a in accs:
        if (a["kind"] == kind and a["level"] == level
                and a["network"] == network and a["basis"] == basis):
            return a["amount"]
    return None


def _copays(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        if e.get("code") != "B":
            continue
        amount = _num(e.get("benefitAmount"))
        if amount is None:
            continue
        out.append({
            "amount": amount,
            "network": _network(e),
            "service_types": e.get("serviceTypes") or [],
            "service_type_codes": e.get("serviceTypeCodes") or [],
            "labels": _info(e),
            "coverage_level": (e.get("coverageLevel") or "").lower() or None,
            "time_qualifier": (e.get("timeQualifier") or "").lower() or None,
        })
    return out


def _drug_tiers(entries: list[dict]) -> list[dict]:
    """Provider-administered and pharmacy drug tiers, in/out-of-network.

    This is the table that actually prices an oncology regimen: an infused drug
    lands in a tier and the tier carries the copay.
    """
    tiers: dict[tuple[str, int], dict] = {}
    for e in entries:
        if e.get("code") != "B":
            continue
        amount = _num(e.get("benefitAmount"))
        if amount is None:
            continue
        for label in _info(e):
            m = _TIER_RE.search(label)
            if not m:
                continue
            up = label.upper()
            if "DRUG" not in up and "TIER" not in up:
                continue
            kind = ("provider_administered" if "PROVIDER ADMINISTERED" in up
                    else "specialty" if "SPECIALTY" in up else "pharmacy")
            key = (kind, int(m.group(1)))
            row = tiers.setdefault(key, {
                "kind": kind, "tier": int(m.group(1)), "label": label,
                "in_network": None, "out_of_network": None,
                "varies_by_location": False, "service_types": e.get("serviceTypes") or [],
            })
            net = _network(e)
            if net == "in":
                # A tier can carry several in-network amounts that vary by site
                # of care; keep the lowest and flag that it varies.
                if row["in_network"] is None or amount < row["in_network"]:
                    if row["in_network"] is not None:
                        row["varies_by_location"] = True
                    row["in_network"] = amount
                elif amount != row["in_network"]:
                    row["varies_by_location"] = True
            elif net == "out":
                if row["out_of_network"] is None or amount > row["out_of_network"]:
                    row["out_of_network"] = amount
            else:
                # "Not Applicable" means the amount holds regardless of network
                # — typically a $0 tier. Record it on both sides.
                if row["in_network"] is None:
                    row["in_network"] = amount
                if row["out_of_network"] is None:
                    row["out_of_network"] = amount
            if any("VARIES BY LOCATION" in l.upper() for l in _info(e)):
                row["varies_by_location"] = True

    return sorted(tiers.values(), key=lambda r: (r["kind"], r["tier"]))


def _coinsurance(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        if e.get("code") != "A":
            continue
        pct = _num(e.get("benefitPercent"))
        if pct is None:
            continue
        out.append({"percent": pct, "network": _network(e),
                    "service_types": e.get("serviceTypes") or [], "labels": _info(e)})
    return out


def _deductibles(entries: list[dict]) -> list[dict]:
    return [a for a in _accumulators(entries) if a["kind"] == "deductible"]


def _limitations(entries: list[dict]) -> list[dict]:
    seen, out = set(), []
    for e in entries:
        if e.get("code") != "F":
            continue
        row = {
            "quantity": _num(e.get("benefitQuantity")),
            "unit": e.get("quantityQualifier"),
            "service_types": e.get("serviceTypes") or [],
            "labels": _info(e),
            "network": _network(e),
        }
        key = (row["quantity"], row["unit"], tuple(row["service_types"]), row["network"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _referrals(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        if e.get("code") not in ("U", "X"):
            continue
        for ent in (e.get("benefitsRelatedEntities") or []):
            out.append({
                "role": ent.get("entityIdentifier"),
                "name": ent.get("entityName"),
                "contacts": [
                    c.get("communicationNumber")
                    for c in ((ent.get("contactInformation") or {}).get("contacts") or [])
                ],
            })
    return out


# --------------------------------------------------------------------------- #
# Estimating what the patient pays
# --------------------------------------------------------------------------- #

def estimate(lines: list[dict], parsed: dict, *, network: str = "in") -> dict:
    """Price billed lines against the parsed 271.

    A line may carry `drug_tier` and `tier_kind` — the formulary answer for that
    HCPCS code. Without it a drug line cannot be priced, and it is reported
    unpriced rather than guessed at.

    The running total is capped by the member's REMAINING out-of-pocket, which
    is a real figure the payer supplied. Copays past that cap are not owed.
    """
    if parsed.get("active") is False:
        return _all_billed(lines, "Coverage reported inactive by the payer")

    tiers = {(t["kind"], t["tier"]): t for t in parsed.get("drug_tiers") or []}
    coins = next((c["percent"] for c in parsed.get("coinsurance") or []
                  if c["network"] == network), None)
    remaining = find_accumulator(parsed.get("accumulators") or [],
                                 "out_of_pocket", "individual", network, "remaining")

    out, running = [], 0.0
    for line in lines:
        billed = int(line.get("billed_cents") or 0)
        amount_c: int | None = None
        basis = None

        tier = line.get("drug_tier")
        kind = line.get("tier_kind") or "provider_administered"
        if tier is not None and (kind, int(tier)) in tiers:
            t = tiers[(kind, int(tier))]
            copay = t["in_network"] if network == "in" else t["out_of_network"]
            if copay is not None:
                amount_c = int(round(copay * 100))
                basis = f"{t['label']} copay ${copay:g} ({'in' if network == 'in' else 'out of'} network)"
                if t["varies_by_location"]:
                    basis += " — payer states the amount varies by site of care"
        elif coins is not None:
            amount_c = int(round(billed * float(coins)))
            basis = f"Coinsurance {round(float(coins) * 100)}% from the 271"

        capped = False
        if amount_c is not None and remaining is not None:
            room = max(0.0, remaining * 100 - running)
            if amount_c > room:
                amount_c = int(room)
                capped = True
            running += amount_c

        out.append({
            **line,
            "patient_estimate_cents": amount_c,
            "estimate_basis": basis or (
                "No drug tier set for this line — the 271 prices provider-administered "
                "drugs by tier, and the tier is a formulary lookup, not something the "
                "payer returned."),
            "capped_by_oop": capped,
            "estimated": amount_c is not None,
        })

    known = [l for l in out if l["patient_estimate_cents"] is not None]
    return {
        "lines": out,
        "network": network,
        "oop_remaining": remaining,
        "totals": {
            "billed_cents": sum(int(l.get("billed_cents") or 0) for l in out),
            "patient_estimate_cents": sum(l["patient_estimate_cents"] for l in known),
            "lines_estimated": len(known),
            "lines_unknown": len(out) - len(known),
        },
        "disclaimer": (
            "Estimates derived from the payer's 271 benefit response and capped by the "
            "member's remaining out-of-pocket. Not a payer authorisation decision — no "
            "X12 278 prior-authorisation transaction is available through this integration."
        ),
    }


def _all_billed(lines: list[dict], reason: str) -> dict:
    out = [{**l, "patient_estimate_cents": int(l.get("billed_cents") or 0),
            "estimate_basis": reason, "capped_by_oop": False, "estimated": True}
           for l in lines]
    return {
        "lines": out, "network": "na", "oop_remaining": None,
        "totals": {
            "billed_cents": sum(int(l.get("billed_cents") or 0) for l in out),
            "patient_estimate_cents": sum(l["patient_estimate_cents"] for l in out),
            "lines_estimated": len(out), "lines_unknown": 0,
        },
        "disclaimer": reason,
    }
