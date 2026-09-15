"""Phrase a FHIR chart as the clinical picture a pre-auth reviewer needs.

A resource list is not a summary. 275 resources with 86 observations tells you
a chart exists; it does not tell you what the patient has, what they are on, or
whether the package is ready to submit. This module answers those three.

Two rules it does not break:

* **Deterministic.** Every sentence is assembled from fields that are present.
  Nothing is inferred, scored or predicted, so a number on this screen can
  always be traced back to a resource id. No model is involved.
* **Gaps stay visible.** A field the chart does not carry is listed in `gaps`,
  never filled with a plausible value. A summary that reads complete when it is
  not is worse than one that is honestly short — somebody would submit it.

It deliberately does NOT classify drugs into chemotherapy vs supportive care.
That needs a drug database we do not have, and guessing it would put the wrong
drug on an authorisation. Medications are grouped and ordered by how often they
were prescribed, which surfaces the regimen without claiming to know it.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

ICD10 = "http://hl7.org/fhir/sid/icd-10"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
SNOMED = "http://snomed.info/sct"

# Categories that describe a patient's circumstances, not the disease. Kept out
# of the problem list so food insecurity never reads as the reason for therapy.
_CONTEXT_CATEGORIES = {"sdoh", "health-concern", "social-history"}
_ACTIVE = {"active", "recurrence", "relapse"}

# Body-surface area and weight are what a cytotoxic dose is calculated from, so
# they are pulled out of the 28 vitals rather than left for someone to find.
_DOSING_MEASURES = {"bsa", "body surface area", "weight", "body weight",
                    "height", "body height", "bmi"}


def _codings(cc: Any) -> list[dict]:
    return (cc or {}).get("coding") or []


def _text(cc: Any) -> str:
    cc = cc or {}
    if cc.get("text"):
        return cc["text"]
    for c in _codings(cc):
        if c.get("display"):
            return c["display"]
    return ""


def _code(cc: Any, system: str) -> str:
    for c in _codings(cc):
        if (c.get("system") or "").startswith(system):
            return c.get("code") or ""
    return ""


def _categories(r: dict) -> set[str]:
    return {c.get("code") for cat in (r.get("category") or []) for c in _codings(cat)
            if c.get("code")}


def _status(r: dict) -> str:
    for c in _codings(r.get("clinicalStatus")):
        if c.get("code"):
            return c["code"]
    return r.get("status") or ""


def _when(r: dict) -> str:
    for k in ("recordedDate", "onsetDateTime", "authoredOn", "effectiveDateTime",
              "issued", "date"):
        v = r.get(k)
        if isinstance(v, str) and v:
            return v[:10]
    return ""


def _age(birth_date: str, on: str = "") -> int | None:
    """Whole years. `on` lets a caller age the patient at a past date."""
    if not birth_date:
        return None
    try:
        by, bm, bd = (int(x) for x in birth_date[:10].split("-"))
    except ValueError:
        return None
    ref = on[:10] if on else ""
    try:
        ry, rm, rd = (int(x) for x in ref.split("-")) if ref else (0, 0, 0)
    except ValueError:
        ry = 0
    if not ry:
        from datetime import date
        t = date.today()
        ry, rm, rd = t.year, t.month, t.day
    return ry - by - ((rm, rd) < (bm, bd))


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def problems(conditions: list[dict]) -> list[dict]:
    """Clinical problems, active first, newest first. Context findings dropped."""
    out = []
    for c in conditions:
        if not c.get("code"):
            continue
        icd = _code(c.get("code"), ICD10)
        if _categories(c) & _CONTEXT_CATEGORIES or icd.upper().startswith("Z"):
            continue
        label = _text(c.get("code"))
        if not label and not icd:
            continue
        out.append({
            "display": label,
            "icd10": icd,
            "snomed": _code(c.get("code"), SNOMED),
            "status": _status(c),
            "onset": _when(c),
        })
        out[-1]["stage"] = next(
            (t for st in (c.get("stage") or []) if (t := _text(st.get("summary")))), "")
        # Where a value came from decides what may be done with it. A stage read
        # off the chart can be cited to a payer; one typed by a person cannot,
        # and the two must never look the same on screen.
        out[-1]["stage_source"] = "chart" if out[-1]["stage"] else ""
    out.sort(key=lambda p: (p["status"] in _ACTIVE, p["onset"]), reverse=True)
    return out


def regimen(med_requests: list[dict], administrations: list[dict] | None = None) -> list[dict]:
    """Medications grouped by drug, with the order count and date span.

    Six separate Cetuximab orders is one regimen, not six drugs — grouping is
    what turns a flat list into "prior lines of therapy", which is exactly the
    medical-necessity question a payer asks.
    """
    groups: dict[str, dict] = defaultdict(
        lambda: {"orders": 0, "dates": [], "statuses": set(), "notes": [],
                 "rxnorm": "", "display": ""})

    for m in med_requests:
        cc = m.get("medicationCodeableConcept") or {}
        name = _text(cc) or (m.get("medicationReference") or {}).get("display") or ""
        if not name:
            continue
        rx = _code(cc, RXNORM)
        key = rx or name.lower()
        g = groups[key]
        g["display"] = g["display"] or name
        g["rxnorm"] = g["rxnorm"] or rx
        g["orders"] += 1
        if when := _when(m):
            g["dates"].append(when)
        if st := m.get("status"):
            g["statuses"].add(st)
        for d in m.get("dosageInstruction") or []:
            note = (d.get("text") or "").strip()
            # Ontada carries cycle information ("LOADING DOSE, C1D1 Only") in
            # free text. Keep the first line — the rest is mixing instructions.
            if note and note.splitlines()[0] not in g["notes"]:
                g["notes"].append(note.splitlines()[0])

    given: dict[str, int] = defaultdict(int)
    for a in administrations or []:
        cc = a.get("medicationCodeableConcept") or {}
        key = _code(cc, RXNORM) or (_text(cc) or "").lower()
        if key:
            given[key] += 1

    out = []
    for key, g in groups.items():
        dates = sorted(g["dates"])
        out.append({
            "drug": g["display"],
            "rxnorm": g["rxnorm"],
            "orders": g["orders"],
            "administered": given.get(key, 0),
            "first": dates[0] if dates else "",
            "last": dates[-1] if dates else "",
            "statuses": sorted(g["statuses"]),
            "notes": g["notes"][:2],
        })
    out.sort(key=lambda d: (d["orders"], d["last"]), reverse=True)
    return out


def dosing_basis(observations: list[dict]) -> dict:
    """Latest height, weight, BSA and BMI — what a dose is calculated from."""
    best: dict[str, dict] = {}
    for o in observations:
        label = _text(o.get("code"))
        key = label.strip().lower()
        if key not in _DOSING_MEASURES:
            continue
        q = o.get("valueQuantity") or {}
        if q.get("value") is None:
            continue
        when = _when(o)
        if key not in best or when > best[key]["as_of"]:
            best[key] = {"label": label, "value": q.get("value"),
                         "unit": q.get("unit") or "", "as_of": when}
    return best


def latest_labs(observations: list[dict], limit: int = 12) -> list[dict]:
    """Most recent value per laboratory test."""
    best: dict[str, dict] = {}
    for o in observations:
        if "laboratory" not in _categories(o):
            continue
        label = _text(o.get("code"))
        if not label:
            continue
        q = o.get("valueQuantity") or {}
        value = q.get("value")
        text = "" if value is not None else (
            _text(o.get("valueCodeableConcept"))
            or (o.get("valueString") or "")
            or ((o.get("text") or {}).get("div", "").split(">")[-2].split("<")[0]
                if o.get("text") else "")
        )
        if value is None and not text:
            continue
        when = _when(o)
        if label not in best or when > best[label]["as_of"]:
            best[label] = {"test": label, "value": value, "unit": q.get("unit") or "",
                           "text": text, "as_of": when,
                           "interpretation": _text((o.get("interpretation") or [{}])[0])}
    return sorted(best.values(), key=lambda x: x["as_of"], reverse=True)[:limit]


# HL7 v3 NullFlavor codes mean "no value", but they carry a display string
# ("Unknown", "Not asked") that reads like a real answer. Ontada types 10 of the
# 35 DocumentReferences this way, which collapsed them all into one "Unknown"
# bucket and hid what the documents actually are.
_NULL_FLAVOUR = {"unknown", "not asked", "masked", "not applicable",
                 "no information", "temporarily unavailable"}


def _kind_of(r: dict) -> str:
    """A usable label for a document or report, skipping NullFlavor placeholders."""
    for candidate in (_text(r.get("type")), _text(r.get("code"))):
        if candidate and candidate.strip().lower() not in _NULL_FLAVOUR:
            return candidate
    # Fall back to the category, which US Core populates even when type is null.
    for cat in r.get("category") or []:
        label = _text(cat)
        if label and label.strip().lower() not in _NULL_FLAVOUR:
            return label
    return "Untyped"


def evidence(documents: list[dict], reports: list[dict]) -> dict:
    """What is on file to attach to a package, counted by kind."""
    def tally(items: list[dict]) -> list[dict]:
        counts: dict[str, dict] = defaultdict(lambda: {"count": 0, "latest": ""})
        for r in items:
            kind = _kind_of(r)
            c = counts[kind]
            c["count"] += 1
            c["latest"] = max(c["latest"], _when(r))
        return sorted(({"kind": k, **v} for k, v in counts.items()),
                      key=lambda x: x["count"], reverse=True)

    return {"documents": tally(documents), "reports": tally(reports)}


# --------------------------------------------------------------------------- #
def summarise(resources: dict[str, list[dict]], *, casebook: dict | None = None) -> dict:
    """The whole picture, plus a plain-English narrative and the gaps."""
    patients = resources.get("Patient") or []
    patient = patients[0] if patients else {}
    name = ""
    if n := (patient.get("name") or [{}])[0]:
        name = " ".join(n.get("given") or []) + " " + (n.get("family") or "")
    birth = patient.get("birthDate") or ""

    probs = problems(resources.get("Condition") or [])
    meds = regimen(resources.get("MedicationRequest") or [],
                   resources.get("MedicationAdministration") or [])
    obs = resources.get("Observation") or []
    basis = dosing_basis(obs)
    labs = latest_labs(obs)
    ev = evidence(resources.get("DocumentReference") or [],
                  resources.get("DiagnosticReport") or [])

    primary = next((p for p in probs if p["status"] in _ACTIVE), probs[0] if probs else None)

    # Ontada carries no stage on any Condition — measured 2026-09-14 on the
    # certification chart: no `Condition.stage`, no staging extension, and no
    # TNM observation among 86. It lives in the pathology PDF. So a stage typed
    # by a user is the only way this gap ever closes, and taking it here is what
    # makes that entry worth doing.
    entered_stage = ((casebook or {}).get("stage") or "").strip()
    if primary and not primary.get("stage") and entered_stage:
        primary["stage"] = entered_stage
        primary["stage_source"] = "entered by hand"
    lead = next((m for m in meds if m["orders"] > 1), meds[0] if meds else None)

    # ---- narrative, assembled only from what is present -------------------
    bits: list[str] = []
    who = [x for x in (patient.get("gender"), f"age {_age(birth)}" if _age(birth) else "") if x]
    bits.append(f"{name.strip() or 'This patient'}"
                + (f" — {', '.join(who)}." if who else "."))

    if primary:
        code = primary["icd10"] or primary["snomed"]
        bits.append(f"Primary problem is {primary['display']}"
                    + (f" ({code})" if code else "")
                    + (f", recorded {primary['onset']}" if primary["onset"] else "")
                    + ".")
        others = [p for p in probs if p is not primary]
        if others:
            bits.append(f"{len(others)} other problem"
                        f"{'s' if len(others) > 1 else ''} on the list: "
                        + ", ".join(p["display"] for p in others[:3]) + ".")
    else:
        bits.append("No clinical problem is recorded on the chart.")

    if lead:
        span = (f" between {lead['first']} and {lead['last']}"
                if lead["first"] and lead["last"] and lead["first"] != lead["last"]
                else (f" on {lead['first']}" if lead["first"] else ""))
        bits.append(f"Most-ordered medication is {lead['drug']}"
                    + (f" (RxNorm {lead['rxnorm']})" if lead["rxnorm"] else "")
                    + f" — {lead['orders']} order{'s' if lead['orders'] > 1 else ''}{span}.")
        if lead["notes"]:
            bits.append(f"Dosing note: {lead['notes'][0]}")
        rest = len(meds) - 1
        if rest > 0:
            bits.append(f"{rest} other medication{'s' if rest > 1 else ''} on file.")
    else:
        bits.append("No medication orders are on the chart.")

    if basis:
        bits.append("Dosing basis on record: "
                    + ", ".join(f"{v['label']} {v['value']}{' ' + v['unit'] if v['unit'] else ''}"
                                for v in basis.values()) + ".")

    doc_total = sum(d["count"] for d in ev["documents"])
    rep_total = sum(d["count"] for d in ev["reports"])
    if doc_total or rep_total:
        bits.append(f"{doc_total} document{'s' if doc_total != 1 else ''} and "
                    f"{rep_total} diagnostic report{'s' if rep_total != 1 else ''} "
                    "are available to attach.")

    # ---- gaps -------------------------------------------------------------
    gaps: list[str] = []
    if not primary:
        gaps.append("No primary diagnosis — a pre-auth cannot state medical necessity without one.")
    elif not primary["icd10"]:
        gaps.append("Primary diagnosis has no ICD-10 code; only SNOMED is on the chart.")
    # Satisfied by the chart or by a hand entry, and by nothing else: an empty
    # casebook field means "nobody has supplied it", which is still a gap.
    if primary and not primary.get("stage"):
        gaps.append(
            f"No stage recorded on {primary['display']}. A payer's medical-necessity "
            "criteria are usually stage-specific, so this has to come from the "
            "pathology report or be entered by hand.")
    if not meds:
        gaps.append("No medication orders, so prior lines of therapy cannot be evidenced.")
    if not basis.get("bsa") and not basis.get("weight"):
        gaps.append("No BSA or weight on file — a cytotoxic dose cannot be checked.")
    if not labs:
        gaps.append("No laboratory results with values; organ-function criteria cannot be checked.")

    return {
        "narrative": " ".join(bits),
        "patient": {"name": name.strip(), "gender": patient.get("gender") or "",
                    "birth_date": birth, "age": _age(birth)},
        "problems": probs,
        "regimen": meds,
        "dosing_basis": list(basis.values()),
        "labs": labs,
        "evidence": ev,
        "gaps": gaps,
    }
