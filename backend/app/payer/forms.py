"""Payer-driven dynamic insurance-policy forms.

The insurance policy a clinic must capture is *not* one form — it changes with
the payer and the program the member is enrolled in. A Medicare FFS member has
an MBI and no group number; a BlueCard member's ID is meaningless without its
three-character alpha prefix; TRICARE is keyed on a DBN or the sponsor's SSN and
denies claims that carry the DoD ID; Medi-Cal will not answer an eligibility
request at all unless the provider's Medi-Cal PIN rides along.

This module turns that into a schema the UI renders and the API validates:

    resolve_payer(...)  -> real payer facts (live Stedi Payer Network)
    classify(...)       -> which payer family / program the member is in
    build_form(...)     -> ordered sections of fields, with real validation rules
    validate(...)       -> field-level errors, before we ever call the payer
    to_eligibility(...) -> maps the captured fields onto the real X12 270 request

Everything payer-specific here is either (a) read live from the Stedi payer
record — `programs`, `operatingStates`, `transactionSupport` — or (b) a cited
rule from the payer/CMS/X12 source named in `SOURCES`. Nothing is invented: a
field exists in a form only because a named source says that payer needs it.
"""
from __future__ import annotations

import re
from datetime import date

# --------------------------------------------------------------------------- #
# Sources — every payer-specific rule below cites one of these.
# --------------------------------------------------------------------------- #
SOURCES = {
    "mbi": {
        "label": "CMS — Understanding the Medicare Beneficiary Identifier (MBI) format",
        "url": "https://www.cms.gov/Medicare/New-Medicare-Card/MBI-Format-PDF.PDF",
    },
    "msp": {
        "label": "CMS MSP Manual ch.3 §20.2.1 — Medicare Secondary Payer questionnaire",
        "url": "https://www.cms.gov/regulations-and-guidance/guidance/manuals/downloads/msp105c03.pdf",
    },
    "bluecard": {
        "label": "BlueCard Program — three-character alpha prefix is required; never guess it",
        "url": "https://www.bcbstx.com/provider/claims/claims-eligibility/bluecard-prefix",
    },
    "tricare_id": {
        "label": "TRICARE — file with the 11-digit DBN or sponsor SSN; the DoD ID is not accepted",
        "url": "https://www.tricare.mil/FAQs/General/GEN_DBN_or_SSN_ForClaim",
    },
    "va_ccn": {
        "label": "VA Community Care — claims must carry the referral's VA authorization number",
        "url": "https://department.va.gov/vha/community-care/provider-claims/",
    },
    "medicaid_pin": {
        "label": "Stedi — payers requiring the provider's PIN on eligibility checks",
        "url": "https://www.stedi.com/docs/healthcare/eligibility-troubleshooting",
    },
    "stedi_270": {
        "label": "Stedi — real-time eligibility check (270/271) request schema",
        "url": "https://www.stedi.com/docs/healthcare/api-reference/post-healthcare-eligibility",
    },
    "stedi_pc": {
        "label": "Stedi — workers' compensation and automobile claims",
        "url": "https://www.stedi.com/docs/healthcare/submit-workers-comp-auto-liability-claims",
    },
    "x12_pc": {
        "label": "X12 — property & casualty claim number and date of loss",
        "url": "https://x12.org/examples/005010x223/example-02-property-and-casualty",
    },
    "hios": {
        "label": "CMS — Marketplace 14-character HIOS plan ID",
        "url": "https://www.cms.gov/marketplace/private-health-insurance/qualified-health-plan-certification",
    },
}

FORM_VERSION = "2026.08"

# --------------------------------------------------------------------------- #
# Validation patterns — each is the payer's own documented rule.
# --------------------------------------------------------------------------- #
# MBI: 11 chars. Positions 2,5,8,9 alphabetic; 1,4,7,10,11 numeric; 3,6
# alphanumeric. Position 1 is 1-9. Letters exclude S, L, O, I, B and Z.
_MBI_ALPHA = "ACDEFGHJKMNPQRTUVWXY"
MBI_RE = (rf"^[1-9][{_MBI_ALPHA}][{_MBI_ALPHA}0-9]\d"
          rf"[{_MBI_ALPHA}][{_MBI_ALPHA}0-9]\d[{_MBI_ALPHA}]{{2}}\d{{2}}$")
# Medicare Advantage / Part D contract: H/R/S/E + 4 digits, optional -PBP.
MA_CONTRACT_RE = r"^[HRSE]\d{4}$"
PBP_RE = r"^\d{3}$"
# BlueCard alpha prefix: three characters as printed (alpha, or alpha-numeric on
# newer cards). Leading character is always alphabetic.
ALPHA_PREFIX_RE = r"^[A-Z][A-Z0-9]{2}$"
DBN_RE = r"^\d{11}$"
SSN_RE = r"^\d{9}$"
DOD_ID_RE = r"^\d{10}$"          # rejected on purpose — see validate()
HIOS_RE = r"^\d{5}[A-Z]{2}\d{7}$"
RXBIN_RE = r"^\d{6}$"
NPI_RE = r"^\d{10}$"
US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO",
    "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "PR", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]

# Payers that really do reject eligibility checks without the provider's program
# PIN — Stedi carries the PIN in `portalPassword`. (Source: medicaid_pin)
PIN_REQUIRED_PAYERS = {
    "100065": "Medi-Cal provider PIN",
    "77039": "Kern Family Health Care provider PIN",
    "ALTAM": "AltaMed provider PIN",
}

# X12 individualRelationshipCode (271 loop 2000C) — drives subscriber vs dependent.
RELATIONSHIP_OPTS = [
    {"value": "self", "label": "Self — the patient is the subscriber", "x12": "18"},
    {"value": "spouse", "label": "Spouse", "x12": "01"},
    {"value": "child", "label": "Child", "x12": "19"},
    {"value": "other", "label": "Other dependent", "x12": "34"},
]

_BLUE_RE = re.compile(
    r"blue\s*cross|blue\s*shield|\bbcbs\b|anthem|highmark|premera|regence|"
    r"wellmark|carefirst|excellus|independence blue|horizon healthcare|"
    r"health care service corporation|elevance|capital blue|blue kc|bluecross",
    re.I)
_VA_RE = re.compile(r"champva|community care network|veterans affairs|\bva ccn\b|"
                    r"triwest|\bvcp\b|veterans health", re.I)
_MEDICARE_FFS_RE = re.compile(r"centers for medicare|medicare part [ab]\b|"
                              r"\bhets\b|railroad medicare|medicare fee.for.service", re.I)


# --------------------------------------------------------------------------- #
# Field helper
# --------------------------------------------------------------------------- #
def f(fid: str, label: str, *, type: str = "text", required: bool = False,
      help: str = "", placeholder: str = "", pattern: str = "",
      pattern_message: str = "", max_length: int | None = None,
      transform: str = "", options: list | None = None, show_if: dict | None = None,
      x12: str = "", source: str = "", value: str = "",
      readonly: bool = False, recommended: bool = False, sensitive: bool = False) -> dict:
    """Build one field descriptor. `x12` records where the value lands in the real
    270 request, so the form and the payer call cannot drift apart."""
    fld = {"id": fid, "label": label, "type": type, "required": required}
    for k, v in (("help", help), ("placeholder", placeholder), ("pattern", pattern),
                 ("pattern_message", pattern_message), ("transform", transform),
                 ("x12", x12), ("value", value)):
        if v:
            fld[k] = v
    if max_length:
        fld["max_length"] = max_length
    if options:
        fld["options"] = options
    if show_if:
        fld["show_if"] = show_if
    if source:
        fld["source"] = SOURCES[source]
    if readonly:
        fld["readonly"] = True
    if recommended:
        fld["recommended"] = True
    if sensitive:
        fld["sensitive"] = True
    return fld


def _opts(*pairs) -> list:
    return [{"value": v, "label": l} for v, l in pairs]


def _state_opts(prefer: list[str] | None = None) -> list:
    prefer = [s for s in (prefer or []) if s in US_STATES]
    rest = [s for s in US_STATES if s not in prefer]
    return _opts(*[(s, s) for s in prefer + rest])


# --------------------------------------------------------------------------- #
# Payer family classification — driven by the live Stedi payer record.
# --------------------------------------------------------------------------- #
FAMILIES = {
    "medicare_ffs": "Medicare fee-for-service (Original Medicare)",
    "medicare_advantage": "Medicare Advantage / Part D plan",
    "medicaid": "Medicaid / CHIP (state program or its managed-care plan)",
    "tricare": "TRICARE (military health)",
    "va": "VA Community Care / CHAMPVA",
    "bcbs": "Blue Cross Blue Shield plan (BlueCard)",
    "marketplace": "ACA Marketplace / exchange plan",
    "commercial": "Commercial / employer-sponsored plan",
    "workers_comp": "Workers' compensation (property & casualty)",
    "auto_medical": "Automobile medical / no-fault (property & casualty)",
}

# Plan-type text that pins the family directly. Matched as an ordered substring
# search, so "Medicare Advantage D-SNP" and "Medicare Part A & B" both land in
# the right family — and the more specific needle always wins.
_PLAN_TYPE_FAMILY = [
    ("tricare", "tricare"),
    ("champva", "va"),
    ("community care", "va"),
    ("medicaid", "medicaid"),
    ("medi-cal", "medicaid"),
    ("chip", "medicaid"),
    ("medicare advantage", "medicare_advantage"),
    ("part d", "medicare_advantage"),
    ("d-snp", "medicare_advantage"),
    ("c-snp", "medicare_advantage"),
    ("original medicare", "medicare_ffs"),
    ("medigap", "medicare_ffs"),
    ("medicare part", "medicare_ffs"),
    ("medicare fee", "medicare_ffs"),
    ("worker", "workers_comp"),
    ("no-fault", "auto_medical"),
    ("auto", "auto_medical"),
    ("marketplace", "marketplace"),
    ("exchange", "marketplace"),
]


def classify(payer: dict, plan_type: str = "") -> tuple[str, str]:
    """Return (family_id, why). `payer` is a Stedi payer record (may be empty).

    Precedence: an explicit plan_type the clinician picked wins, then the payer's
    real program list from the Stedi Payer Network, then its name/parent group.
    """
    name = f"{payer.get('name', '')} {payer.get('parent_group', '') or ''}"
    pid = (payer.get("payer_id") or "").upper()
    programs = {p.upper() for p in (payer.get("programs") or [])}
    pt = (plan_type or "").strip().lower()

    for needle, fam in _PLAN_TYPE_FAMILY:
        if needle in pt:
            return fam, f"plan type selected as '{plan_type}'"

    if _VA_RE.search(name) or pid in {"84146", "VACCN"}:
        return "va", "payer is in the VA Community Care / CHAMPVA family"
    if "TRICARE" in programs or re.search(r"tricare", name, re.I):
        return "tricare", "Stedi payer record lists the TRICARE program"
    if pid == "CMS" or _MEDICARE_FFS_RE.search(name):
        return "medicare_ffs", "payer is CMS itself — Original Medicare (HETS)"

    # Single-program payers are unambiguous.
    if programs == {"MEDICARE"}:
        return "medicare_advantage", "Stedi payer record lists MEDICARE as its only program"
    if programs == {"MEDICAID"}:
        return "medicaid", "Stedi payer record lists MEDICAID as its only program"

    if _BLUE_RE.search(name):
        return "bcbs", "payer is a Blue Cross Blue Shield licensee — BlueCard rules apply"
    if programs and "COMMERCIAL" in programs:
        return "commercial", "Stedi payer record lists a COMMERCIAL program"
    if programs:
        return "commercial", f"payer programs {sorted(programs)} — defaulting to commercial capture"
    return "commercial", "payer program not published; capturing the commercial field set"


def plan_type_options(family: str, payer: dict, current: str = "") -> list:
    """Plan-type choices that make sense for this payer, seeded from its real
    program list so we never offer a Medicaid plan type to a TRICARE payer."""
    opts = _plan_type_options(family, payer)
    if current and not any(o["value"] == current for o in opts):
        opts.insert(0, {"value": current, "label": current})
    return opts


def _plan_type_options(family: str, payer: dict) -> list:
    programs = {p.upper() for p in (payer.get("programs") or [])}
    if family == "medicare_ffs":
        return _opts(("Medicare Part A & B", "Medicare Part A & B"),
                     ("Medicare Part B only", "Medicare Part B only"),
                     ("Medicare + Medigap", "Medicare + Medigap supplement"))
    if family == "medicare_advantage":
        return _opts(("Medicare Advantage HMO", "Medicare Advantage HMO"),
                     ("Medicare Advantage PPO", "Medicare Advantage PPO"),
                     ("Medicare Advantage D-SNP", "Medicare Advantage D-SNP (dual eligible)"),
                     ("Medicare Advantage C-SNP", "Medicare Advantage C-SNP (chronic condition)"),
                     ("Medicare Part D", "Medicare Part D (prescription only)"))
    if family == "medicaid":
        return _opts(("Medicaid fee-for-service", "Medicaid fee-for-service"),
                     ("Medicaid managed care", "Medicaid managed care (MCO)"),
                     ("CHIP", "CHIP"),
                     ("Medicaid + Medicare (dual)", "Dual eligible (Medicaid + Medicare)"))
    if family == "tricare":
        return _opts(("TRICARE Prime", "TRICARE Prime"),
                     ("TRICARE Select", "TRICARE Select"),
                     ("TRICARE For Life", "TRICARE For Life"),
                     ("TRICARE Reserve Select", "TRICARE Reserve Select"),
                     ("TRICARE Young Adult", "TRICARE Young Adult"),
                     ("TRICARE Overseas", "TRICARE Overseas"))
    if family == "va":
        return _opts(("VA CCN", "VA Community Care Network"),
                     ("CHAMPVA", "CHAMPVA"),
                     ("Veterans Care Agreement", "Veterans Care Agreement"))
    if family == "marketplace":
        return _opts(("Marketplace HMO", "Marketplace HMO"), ("Marketplace PPO", "Marketplace PPO"),
                     ("Marketplace EPO", "Marketplace EPO"), ("Marketplace POS", "Marketplace POS"))
    if family in ("workers_comp", "auto_medical"):
        return _opts(("Workers compensation", "Workers' compensation"),
                     ("Auto / no-fault", "Auto medical / no-fault (PIP / MedPay)"))
    base = [("PPO", "PPO"), ("HMO", "HMO"), ("EPO", "EPO"), ("POS", "POS"),
            ("HDHP", "HDHP / high deductible"), ("Indemnity", "Indemnity / fee-for-service"),
            ("Self-funded (ASO)", "Self-funded employer plan (ASO)")]
    if "MEDICARE" in programs:
        base.append(("Medicare Advantage", "Medicare Advantage"))
    if "MEDICAID" in programs:
        base.append(("Medicaid", "Medicaid / managed Medicaid"))
    base.append(("Marketplace", "ACA Marketplace / exchange"))
    base.append(("Workers compensation", "Workers' compensation"))
    base.append(("Auto / no-fault", "Auto medical / no-fault"))
    return _opts(*base)


# --------------------------------------------------------------------------- #
# Section builders — the payer-specific field sets.
# --------------------------------------------------------------------------- #
def _is_blue(payer: dict) -> bool:
    return bool(_BLUE_RE.search(f"{payer.get('name', '')} {payer.get('parent_group', '') or ''}"))


def _alpha_prefix_field(required: bool = True) -> dict:
    return f("alpha_prefix", "Alpha prefix", required=required, transform="upper", max_length=3,
             pattern=ALPHA_PREFIX_RE, placeholder="ABC",
             pattern_message="The alpha prefix is the first three characters on the card and "
                             "starts with a letter.",
             help="The three characters that precede the member ID and route the claim to the "
                  "member's home Blue plan. Copy it exactly — never guess it; a wrong prefix "
                  "makes the claim unprocessable. A card with no prefix is not BlueCard-eligible.",
             x12="subscriber.memberId (prefix)", source="bluecard")


def _member_fields(family: str, payer: dict) -> list:
    """The identifiers this payer family actually adjudicates on."""
    fields = _member_fields_for(family, payer)
    # A Blue licensee prints the alpha prefix on every product it issues, not
    # only on its commercial book — add it wherever the family did not already.
    if _is_blue(payer) and family not in ("bcbs", "workers_comp", "auto_medical") \
            and not any(fl["id"] == "alpha_prefix" for fl in fields):
        fields.insert(0, _alpha_prefix_field(required=False))
    return fields


def _member_fields_for(family: str, payer: dict) -> list:
    states = payer.get("operating_states") or []
    pid = (payer.get("payer_id") or "").upper()

    if family == "medicare_ffs":
        return [
            f("mbi", "Medicare number (MBI)", required=True, transform="upper_alnum",
              max_length=11, pattern=MBI_RE, placeholder="1EG4TE5MK73",
              pattern_message="An MBI is 11 characters: positions 2, 5, 8 and 9 are letters, "
                              "1, 4, 7, 10 and 11 are digits, and the letters S, L, O, I, B "
                              "and Z are never used.",
              help="As printed on the red-white-and-blue Medicare card. Dashes are stripped "
                   "automatically. Original Medicare has no group number.",
              x12="subscriber.memberId", source="mbi"),
            f("part_a_effective", "Part A effective date", type="date",
              help="Optional — establishes the hospital-benefit period.",
              x12="—"),
            f("part_b_effective", "Part B effective date", type="date", recommended=True,
              help="Part B is the benefit that pays for physician-administered "
                   "(J-code) oncology drugs.", x12="—"),
        ]

    if family == "medicare_advantage":
        return [
            f("member_id", "Plan member ID", required=True, transform="upper",
              placeholder="As printed on the plan card",
              help="The Medicare Advantage plan's own member ID — not the MBI.",
              x12="subscriber.memberId", source="stedi_270"),
            f("ma_contract", "Medicare contract number", transform="upper", max_length=5,
              pattern=MA_CONTRACT_RE, placeholder="H1234", recommended=True,
              pattern_message="A CMS contract number is a letter (H, R, S or E) followed by "
                              "four digits, e.g. H1234.",
              help="H/R = Medicare Advantage, S = Part D, E = employer group. Identifies "
                   "which CMS-approved plan benefit applies.", x12="—"),
            f("ma_pbp", "Plan benefit package (PBP)", max_length=3, pattern=PBP_RE,
              placeholder="001", pattern_message="The PBP is three digits, e.g. 001.",
              help="Distinguishes benefit packages inside one contract.", x12="—"),
            f("mbi", "Medicare number (MBI)", transform="upper_alnum", max_length=11,
              pattern=MBI_RE, placeholder="1EG4TE5MK73", recommended=True,
              pattern_message="An MBI is 11 characters; positions 2, 5, 8 and 9 are letters and "
                              "S, L, O, I, B and Z are never used.",
              help="Needed when the member is dual-eligible or the plan coordinates back to "
                   "Original Medicare. Returned by the payer as `hicNumber`.",
              x12="subscriber.memberId (fallback)", source="mbi"),
            f("group_number", "Group number (EGWP)", transform="upper",
              help="Only employer group waiver plans carry one.", x12="subscriber.groupNumber"),
        ]

    if family == "medicaid":
        fields = [
            f("medicaid_state", "State program", type="select", required=True,
              options=_state_opts(states),
              value=states[0] if len(states) == 1 else "",
              help="Medicaid IDs are issued per state — a provider treating across state "
                   "lines has a different ID in each.", x12="—"),
            f("medicaid_id", "Medicaid / recipient ID", required=True, transform="upper",
              help="The state-issued recipient ID (RID / CIN). Format varies by state, so "
                   "it is checked for presence, not shape.",
              x12="subscriber.memberId", source="stedi_270"),
            f("mco_plan_name", "Managed-care plan (MCO)",
              show_if={"field": "plan_type", "contains": "managed care"},
              help="The MCO that administers the benefit, if the member is enrolled in one.",
              x12="—"),
            f("share_of_cost", "Share of cost / spend-down", type="money",
              help="Monthly liability the member must meet before Medicaid pays, where the "
                   "state operates a spend-down.", x12="—"),
        ]
        if pid in PIN_REQUIRED_PAYERS:
            fields.append(
                f("provider_pin", f"Provider PIN — {PIN_REQUIRED_PAYERS[pid]}", required=True,
                  sensitive=True,
                  help="This payer rejects eligibility checks without the requesting "
                       "provider's program PIN (AAA error 41, authorization/access "
                       "restrictions). It is sent as the eligibility portal secret and is "
                       "never stored in the packet.",
                  x12="portalPassword", source="medicaid_pin"))
        return fields

    if family == "tricare":
        region = ""
        nm = payer.get("name", "")
        for r, label in (("east", "East"), ("west", "West"), ("overseas", "Overseas"),
                         ("for life", "For Life")):
            if r in nm.lower():
                region = label
                break
        return [
            f("tricare_region", "TRICARE region", type="select", required=True,
              value=region,
              options=_opts(("East", "East (Humana Military)"), ("West", "West (TriWest)"),
                            ("Overseas", "Overseas (International SOS)"),
                            ("For Life", "For Life (WPS — Medicare wrap)")),
              help="Region determines the contractor that adjudicates the authorization.",
              x12="—"),
            f("tricare_id_type", "Identify the member by", type="radio", required=True,
              value="dbn",
              options=_opts(("dbn", "DoD Benefits Number (11 digits, back of the ID card)"),
                            ("sponsor_ssn", "Sponsor's SSN (9 digits)")),
              help="TRICARE accepts either. It does NOT accept the 10-digit DoD ID from the "
                   "front of the card — claims filed with it are denied.",
              source="tricare_id", x12="—"),
            f("dbn", "DoD Benefits Number (DBN)", required=True, transform="digits",
              max_length=11, pattern=DBN_RE, placeholder="11 digits, no dashes",
              pattern_message="A DBN is exactly 11 digits with no dashes. A 10-digit number is "
                              "the DoD ID (EDIPI), which TRICARE will deny.",
              show_if={"field": "tricare_id_type", "in": ["dbn"]},
              x12="subscriber.memberId", source="tricare_id"),
            f("sponsor_ssn", "Sponsor's SSN", required=True, transform="digits", max_length=9,
              pattern=SSN_RE, placeholder="9 digits", sensitive=True,
              pattern_message="A sponsor SSN is exactly 9 digits.",
              show_if={"field": "tricare_id_type", "in": ["sponsor_ssn"]},
              x12="subscriber.ssn", source="tricare_id"),
            f("sponsor_first", "Sponsor first name", required=True,
              help="The service member the benefit flows from — the patient may be a "
                   "family member.", x12="subscriber.firstName"),
            f("sponsor_last", "Sponsor last name", required=True, x12="subscriber.lastName"),
            f("sponsor_status", "Sponsor status", type="select", required=True,
              options=_opts(("active_duty", "Active duty"), ("retired", "Retired"),
                            ("guard_reserve", "Guard / Reserve"),
                            ("deceased", "Deceased (survivor benefit)"),
                            ("medically_retired", "Medically retired")),
              help="Drives which TRICARE plan the family is eligible for.", x12="—"),
        ]

    if family == "va":
        return [
            f("va_authorization_number", "VA authorization / referral number", required=True,
              transform="upper",
              help="From the VA referral (Form 10-7080). Community-care claims without the "
                   "referral's authorization number are rejected — this is the single most "
                   "common VA denial.", x12="—", source="va_ccn"),
            f("va_tpa", "Third-party administrator", type="select", required=True,
              options=_opts(("optum", "Optum — CCN Regions 1, 2, 3"),
                            ("triwest", "TriWest — CCN Regions 4, 5"),
                            ("champva_va", "VA directly (CHAMPVA)")),
              help="The referral states where the claim goes; filing to the wrong TPA is a "
                   "rejection, not a redirect.", x12="—", source="va_ccn"),
            f("referring_va_facility", "Referring VA facility",
              help="The VA medical centre that issued the referral.", x12="—"),
            f("member_id", "Member / beneficiary ID", required=True, transform="upper",
              help="CHAMPVA member number, or the Veteran's identifier on the referral.",
              x12="subscriber.memberId"),
            f("service_connected", "Service-connected condition?", type="select",
              options=_opts(("yes", "Yes — service-connected"), ("no", "No"),
                            ("unknown", "Unknown")),
              help="Non-service-connected care generally requires prior authorization.",
              x12="—", source="va_ccn"),
        ]

    if family == "bcbs":
        return [
            _alpha_prefix_field(required=True),
            f("member_id", "Member ID (after the prefix)", required=True, transform="upper",
              help="Entered without the prefix — the two are joined for the payer request.",
              x12="subscriber.memberId", source="bluecard"),
            f("group_number", "Group number", transform="upper", recommended=True,
              help="Identifies the employer group inside the home plan. Not required to "
                   "identify the member, but it pins which benefit set applies.",
              x12="subscriber.groupNumber"),
            f("home_plan", "Home Blue plan",
              help="The licensee named on the card, if it differs from the plan being billed.",
              x12="—"),
            f("bluecard_out_of_area", "BlueCard out-of-area member", type="checkbox",
              help="Tick when the card's home plan is not the local plan — benefits are quoted "
                   "by the home plan via BlueCard (verify on 1-800-676-BLUE).",
              x12="—", source="bluecard"),
        ]

    if family == "marketplace":
        return [
            f("member_id", "Member ID", required=True, transform="upper",
              x12="subscriber.memberId"),
            f("hios_plan_id", "HIOS plan ID", transform="upper", max_length=14,
              pattern=HIOS_RE, placeholder="12345AB1234567", recommended=True,
              pattern_message="A HIOS plan ID is 14 characters: 5 digits, 2 letters (state), "
                              "then 7 digits.",
              help="The 14-character standard component ID — pins the exact certified plan "
                   "benefit and its formulary.", x12="—", source="hios"),
            f("exchange", "Exchange", type="select",
              options=_opts(("healthcare.gov", "healthcare.gov (federal)"),
                            ("state", "State-based exchange"),
                            ("off_exchange", "Off-exchange (direct from issuer)")),
              x12="—"),
            f("group_number", "Group number", transform="upper",
              x12="subscriber.groupNumber"),
            f("aptc_grace_period", "In APTC grace period", type="checkbox",
              help="A subsidised member in the 90-day non-payment grace period: the issuer may "
                   "pend or later reverse payment for services in months 2 and 3.", x12="—"),
        ]

    if family in ("workers_comp", "auto_medical"):
        auto = family == "auto_medical"
        return [
            f("pc_claim_number", "Claim number", required=True, transform="upper",
              help="The property & casualty claim number that ties the policy to the injury — "
                   "the preferred identifier on an electronic medical bill.",
              x12="subscriber.memberId", source="x12_pc"),
            f("pc_policy_number", "Policy number", transform="upper",
              help="Send the policy number instead only when no claim number has been issued "
                   "yet — with the date of loss it substitutes for the claim number.",
              x12="—", source="x12_pc"),
            f("date_of_injury", "Date of " + ("accident" if auto else "injury"), type="date",
              required=True,
              help="The date of loss. Coverage is determined as of this date, not the date of "
                   "service.", x12="claimInformation.claimDateInformation.accidentDate",
              source="x12_pc"),
            f("accident_state", "Jurisdiction state", type="select", required=True,
              options=_state_opts(payer.get("operating_states")),
              help="The state whose fee schedule and rules govern the bill.",
              x12="claimInformation.autoAccidentStateCode" if auto else "—",
              source="stedi_pc"),
            f("employer_name", ("Insured / policyholder" if auto else "Employer"),
              required=not auto,
              help=("The insured named on the auto policy." if auto else
                    "On a workers' comp bill the employer is the subscriber and the injured "
                    "worker is the dependent."),
              x12="claimInformation.subscriber (P&C claim)", source="stedi_pc"),
            f("adjuster_name", "Adjuster", help="Who authorises treatment on the claim.", x12="—"),
            f("adjuster_phone", "Adjuster phone", type="tel", x12="—"),
        ]

    # commercial / employer-sponsored — the default
    return [
        f("member_id", "Member / subscriber ID", required=True, transform="upper",
          help="Exactly as printed, including any leading letters or suffix.",
          x12="subscriber.memberId", source="stedi_270"),
        f("group_number", "Group number", transform="upper", recommended=True,
          help="Nearly every employer-sponsored plan adjudicates against the group. The payer "
               "can find the member without it, but benefits are quoted more precisely with it.",
          x12="subscriber.groupNumber", source="stedi_270"),
        f("plan_sponsor", "Employer / plan sponsor",
          help="Identifies self-funded plans, whose benefits differ from the carrier's "
               "standard book.", x12="—"),
    ]


def _patient_fields(family: str) -> list:
    """Who the patient is relative to the policy. Drives the 270 dependent loop."""
    dependent_note = ("Include the dependent's date of birth — many payers return an error "
                      "without it, and only one dependent may be sent per request.")
    rel = f("relationship", "Relationship to subscriber", type="select",
            required=True, value="self",
            options=[{"value": o["value"], "label": o["label"]} for o in RELATIONSHIP_OPTS],
            help="Anything other than 'self' sends the patient in the dependent loop of the "
                 "eligibility request. " + dependent_note,
            x12="subscriber.individualRelationshipCode", source="stedi_270")
    if family == "medicaid":
        rel["help"] = ("Most Medicaid programs cannot be searched at the dependent level — each "
                       "member has their own recipient ID. Keep this as 'self' and enter the "
                       "patient's own Medicaid ID unless the state supports dependents.")
    if family == "workers_comp":
        rel = f("relationship", "Relationship to policyholder", type="select",
                required=True, value="other",
                options=_opts(("other", "Injured worker (dependent of the employer policy)"),
                              ("self", "Self — the patient holds the policy")),
                help="On a workers' compensation bill the employer holds the policy and the "
                     "injured worker is the dependent.",
                x12="subscriber.individualRelationshipCode", source="stedi_pc")
    person_subscriber = family not in ("workers_comp", "auto_medical")
    return [
        rel,
        f("patient_first", "Patient first name", required=True,
          help="Full legal first name — nicknames are a common cause of a 'subscriber not "
               "found' rejection.",
          x12="dependent.firstName / subscriber.firstName", source="stedi_270"),
        f("patient_last", "Patient last name", required=True,
          x12="dependent.lastName / subscriber.lastName"),
        f("dob", "Patient date of birth", type="date", required=True,
          help="Payers must return benefits when member ID, date of birth, first and last "
               "name are all supplied and the member exists.",
          x12="dependent.dateOfBirth / subscriber.dateOfBirth", source="stedi_270"),
        f("gender", "Patient sex", type="select",
          options=_opts(("F", "Female"), ("M", "Male"), ("U", "Unknown / not specified")),
          x12="dependent.gender / subscriber.gender"),
    ] + ([
        f("subscriber_first", "Subscriber first name", required=True,
          show_if={"field": "relationship", "in": ["spouse", "child", "other"]},
          x12="subscriber.firstName"),
        f("subscriber_last", "Subscriber last name", required=True,
          show_if={"field": "relationship", "in": ["spouse", "child", "other"]},
          x12="subscriber.lastName"),
        f("subscriber_dob", "Subscriber date of birth", type="date", recommended=True,
          help="Payers match the dependent against the subscriber's own date of birth — "
               "sending the patient's twice is a common cause of a false 'not found'.",
          show_if={"field": "relationship", "in": ["spouse", "child", "other"]},
          x12="subscriber.dateOfBirth"),
    ] if person_subscriber else [])


def _benefit_fields(family: str) -> list:
    """Which benefit pays for a physician-administered oncology drug — the split
    that decides whether a J-code claim or a pharmacy claim is authorized."""
    if family in ("workers_comp", "auto_medical", "va"):
        return []
    fields = [
        f("benefit_to_bill", "Benefit the therapy bills under", type="select",
          value="medical", required=True,
          options=_opts(("medical", "Medical benefit — buy-and-bill J-code (infusion)"),
                        ("pharmacy", "Pharmacy benefit — specialty pharmacy / NDC"),
                        ("unknown", "Not yet determined")),
          help="Infused oncology drugs usually sit on the medical benefit; oral targeted "
               "therapy usually sits on the pharmacy benefit, and each has its own prior-"
               "authorization pathway and cost share.", x12="encounter.serviceTypeCodes"),
        f("rx_bin", "Rx BIN", transform="digits", max_length=6, pattern=RXBIN_RE,
          placeholder="6 digits", pattern_message="An Rx BIN is six digits.",
          show_if={"field": "benefit_to_bill", "in": ["pharmacy"]},
          help="Routes the pharmacy claim to the PBM.", x12="—"),
        f("rx_pcn", "Rx PCN", transform="upper",
          show_if={"field": "benefit_to_bill", "in": ["pharmacy"]}, x12="—"),
        f("rx_group", "Rx group", transform="upper",
          show_if={"field": "benefit_to_bill", "in": ["pharmacy"]}, x12="—"),
    ]
    if family == "medicare_ffs":
        fields[0]["help"] = ("Part B pays for physician-administered drugs; Part D pays for "
                             "self-administered ones. Original Medicare has no medical-benefit "
                             "prior authorization for most Part B drugs, but the Part D plan does.")
    return fields


def _cob_fields(family: str) -> list:
    """Coordination of benefits. Medicare and Medicaid have statutory ordering, so
    for those families this is a required questionnaire rather than an optional one."""
    if family == "medicare_ffs":
        return [
            f("msp_other_coverage", "Is another payer primary to Medicare?", type="select",
              required=True, value="no",
              options=_opts(("no", "No — Medicare is primary"),
                            ("yes", "Yes — another payer pays first"),
                            ("unknown", "Not yet established")),
              help="The Medicare Secondary Payer questionnaire must be completed before "
                   "billing, and re-verified every 90 days or at a new injury.",
              x12="—", source="msp"),
            f("msp_reason", "Why is Medicare secondary?", type="select", required=True,
              show_if={"field": "msp_other_coverage", "in": ["yes"]},
              options=_opts(("working_aged", "Working aged — employer group health plan (20+ employees)"),
                            ("disability", "Disability — large group health plan (100+ employees)"),
                            ("esrd", "ESRD 30-month coordination period"),
                            ("workers_comp", "Workers' compensation"),
                            ("no_fault", "No-fault / auto insurance"),
                            ("liability", "Liability insurance"),
                            ("black_lung", "Federal Black Lung program"),
                            ("va", "VA-authorized care"),
                            ("federal_research", "Government research programme")),
              x12="—", source="msp"),
            f("msp_primary_payer", "Primary payer name", required=True,
              show_if={"field": "msp_other_coverage", "in": ["yes"]}, x12="—"),
            f("msp_primary_member_id", "Primary payer member ID", required=True,
              transform="upper", show_if={"field": "msp_other_coverage", "in": ["yes"]},
              x12="—"),
            f("msp_employer_name", "Employer providing the group plan",
              show_if={"field": "msp_reason", "in": ["working_aged", "disability"]}, x12="—"),
            f("msp_employer_size", "Employer size", type="select",
              options=_opts(("lt20", "Fewer than 20 employees"), ("20_99", "20–99 employees"),
                            ("100plus", "100 or more employees")),
              show_if={"field": "msp_reason", "in": ["working_aged", "disability"]},
              help="Employer size is what decides the payment order for working-aged and "
                   "disability beneficiaries.", x12="—", source="msp"),
            f("msp_accident_date", "Date of accident / injury", type="date", required=True,
              show_if={"field": "msp_reason", "in": ["workers_comp", "no_fault", "liability"]},
              x12="—", source="msp"),
            f("msp_esrd_first_dialysis", "First dialysis date", type="date",
              show_if={"field": "msp_reason", "in": ["esrd"]},
              help="Starts the 30-month coordination period during which the group plan pays "
                   "first.", x12="—", source="msp"),
        ]
    if family == "medicaid":
        return [
            f("tpl_other_coverage", "Does the member have any other coverage?", type="select",
              required=True, value="no",
              options=_opts(("no", "No other coverage"),
                            ("yes", "Yes — commercial, Medicare or other third party"),
                            ("unknown", "Unknown")),
              help="Medicaid is the payer of last resort: any liable third party must be "
                   "billed and adjudicated first.", x12="—"),
            f("tpl_primary_payer", "Primary payer name", required=True,
              show_if={"field": "tpl_other_coverage", "in": ["yes"]}, x12="—"),
            f("tpl_primary_member_id", "Primary payer member ID", required=True,
              transform="upper", show_if={"field": "tpl_other_coverage", "in": ["yes"]}, x12="—"),
        ]
    return [
        f("has_secondary", "Secondary coverage on file", type="checkbox",
          help="Tick to record a second policy; the pre-auth packet records the payment "
               "order so the secondary is not billed out of turn.", x12="—"),
        f("secondary_insurer", "Secondary payer", required=True,
          show_if={"field": "has_secondary", "truthy": True}, x12="—"),
        f("secondary_member_id", "Secondary member ID", required=True, transform="upper",
          show_if={"field": "has_secondary", "truthy": True}, x12="—"),
        f("coordination_order", "This policy is", type="select",
          value="primary", show_if={"field": "has_secondary", "truthy": True},
          options=_opts(("primary", "Primary"), ("secondary", "Secondary"),
                        ("tertiary", "Tertiary")), x12="—"),
    ]


def _contact_fields(family: str) -> list:
    label = {"medicare_ffs": "Medicare contractor (MAC) prior-auth line",
             "tricare": "Regional contractor authorization line",
             "va": "TPA authorization line"}.get(family, "Payer prior-authorization line")
    return [
        f("phone", label, type="tel",
          help="Printed on the back of the card — used when the payer must be reached for a "
               "peer-to-peer review.", x12="—"),
        f("portal_reference", "Payer portal reference / case number", transform="upper",
          help="If the authorization was started in the payer's own portal, record its case "
               "number so this packet attaches to it.", x12="—"),
        f("policy_effective_date", "Coverage effective date", type="date",
          help="A therapy start date before the effective date is denied outright.", x12="—"),
        f("policy_end_date", "Coverage end date", type="date",
          help="Leave blank if open-ended.", x12="—"),
    ]


# --------------------------------------------------------------------------- #
# Form assembly
# --------------------------------------------------------------------------- #
def build_form(payer: dict | None = None, plan_type: str = "",
               patient: dict | None = None, prefill: dict | None = None) -> dict:
    """Build the payer-specific policy form schema.

    `payer` is a resolved payer record (see `normalise_payer`); pass an empty
    dict before a payer is chosen and the generic commercial form comes back.
    `patient` prefills what the casebook already knows about the patient, and
    `prefill` what the payer has already told us about this member — the shape
    `PreAuth.policy_prefill` carries (`{insurer, payer_id, source, fields}`).
    A prefilled field is still the clinician's to change; the form records where
    the value came from so it is never mistaken for something they typed.
    """
    payer = dict(payer or {})
    family, why = classify(payer, plan_type)
    patient = patient or {}
    prefill = prefill or {}
    known = dict(prefill.get("fields") or {})

    plan_field = f("plan_type", "Plan type", type="select",
                   required=family not in ("workers_comp", "auto_medical"),
                   value=plan_type,
                   options=plan_type_options(family, payer, current=plan_type),
                   help="The benefit design the payer will adjudicate against. Changing it "
                        "re-derives the fields below.", x12="—")
    plan_name = f("plan_name", "Plan / product name",
                  help="As printed on the card, e.g. 'Choice Plus HSA'.",
                  x12="subscriber.idCard")

    sections = [
        {"id": "plan", "title": "Plan",
         "subtitle": "What kind of coverage this is — this is what selects the fields below.",
         "fields": [plan_field, plan_name]},
        {"id": "member", "title": "Member identification",
         "subtitle": f"Required by {payer.get('name') or 'this payer'} to identify the member.",
         "fields": _member_fields(family, payer)},
        {"id": "patient", "title": "Patient & subscriber",
         "subtitle": "Who is being treated, and whose policy it is.",
         "fields": _patient_fields(family)},
    ]
    benefit = _benefit_fields(family)
    if benefit:
        sections.append({"id": "benefit", "title": "Benefit routing",
                         "subtitle": "Which benefit the therapy is authorized under.",
                         "fields": benefit})
    sections.append({"id": "cob", "title": "Coordination of benefits",
                     "subtitle": ("Medicare Secondary Payer questionnaire — required before "
                                  "billing." if family == "medicare_ffs" else
                                  "Other coverage that pays before this policy."),
                     "fields": _cob_fields(family)})
    sections.append({"id": "contact", "title": "Authorization contact & dates",
                     "subtitle": "How the payer is reached, and when the policy is in force.",
                     "fields": _contact_fields(family)})

    # prefill from the casebook patient twin
    from_twin = {
        "patient_first": (patient.get("name") or "").split(" ")[0] if patient.get("name") else "",
        "patient_last": (patient.get("name") or "").split(" ")[-1] if patient.get("name") else "",
        "gender": patient.get("sex", "") if patient.get("sex") in ("F", "M") else "",
        "dob": patient.get("dob", "") or "",
    }
    for sec in sections:
        for fld in sec["fields"]:
            if from_twin.get(fld["id"]) and not fld.get("value"):
                fld["value"] = from_twin[fld["id"]]
                fld["prefilled_from"] = "casebook"
            # What the payer has already told us about this member outranks the
            # twin and any default: it is the payer's own answer.
            if fld["id"] in known and known[fld["id"]] not in ("", None):
                fld["value"] = known[fld["id"]]
                fld["prefilled_from"] = "payer"

    sources = []
    seen = set()
    for sec in sections:
        for fld in sec["fields"]:
            s = fld.get("source")
            if s and s["url"] not in seen:
                seen.add(s["url"])
                sources.append(s)

    return {
        "form_id": f"policy-form/{family}",
        "form_version": FORM_VERSION,
        "family": {"id": family, "label": FAMILIES[family], "why": why},
        "payer": payer,
        "sections": sections,
        "prefill": {"source": prefill.get("source", ""),
                    "fields": sorted(known.keys()),
                    "insurer": prefill.get("insurer", ""),
                    "payer_id": prefill.get("payer_id", "")} if known else None,
        "consent_text": "The patient has authorised use of these insurance details to "
                        "determine coverage and to request prior authorization for the "
                        "recommended therapy.",
        "sources": sources,
    }


def normalise_payer(rec: dict | None, insurer: str = "", payer_id: str = "") -> dict:
    """Flatten a Stedi payer record into the shape the form engine expects.

    Only real published facts are carried over; when the payer could not be
    resolved we say so rather than guessing its capabilities.
    """
    if not rec:
        return {"name": insurer, "payer_id": payer_id, "stedi_id": "", "programs": [],
                "operating_states": [], "coverage_types": [], "eligibility_support": "",
                "parent_group": "", "resolved": False,
                "source": SOURCES["stedi_270"]["url"]}
    raw = rec.get("raw") or rec
    ts = raw.get("transactionSupport") or {}
    return {
        "name": rec.get("name") or raw.get("displayName") or insurer,
        "payer_id": rec.get("payer_id") or raw.get("primaryPayerId") or payer_id,
        "stedi_id": rec.get("stedi_id") or raw.get("stediId", ""),
        "programs": raw.get("programs") or [],
        "operating_states": raw.get("operatingStates") or [],
        "coverage_types": raw.get("coverageTypes") or [],
        "eligibility_support": ts.get("eligibilityCheck", ""),
        "cob_support": ts.get("coordinationOfBenefits", ""),
        "parent_group": raw.get("parentPayerGroupName") or "",
        "resolved": True,
        "source": "https://www.stedi.com/healthcare/network",
    }


# --------------------------------------------------------------------------- #
# Transforms, visibility and validation
# --------------------------------------------------------------------------- #
def _apply_transform(kind: str, value):
    if not isinstance(value, str):
        return value
    v = value.strip()
    if kind == "upper":
        return v.upper()
    if kind == "digits":
        return re.sub(r"\D", "", v)
    if kind == "upper_alnum":
        return re.sub(r"[^A-Z0-9]", "", v.upper())
    return v


def normalise_values(form: dict, values: dict) -> dict:
    """Apply each field's declared transform — so 1EG4-TE5-MK73 and 1eg4te5mk73
    both become the MBI the payer expects."""
    out = dict(values or {})
    for sec in form["sections"]:
        for fld in sec["fields"]:
            fid = fld["id"]
            if fid in out and fld.get("transform"):
                out[fid] = _apply_transform(fld["transform"], out[fid])
    return out


def _visible(fld: dict, values: dict) -> bool:
    cond = fld.get("show_if")
    if not cond:
        return True
    v = values.get(cond["field"])
    if "in" in cond:
        return v in cond["in"]
    if "contains" in cond:
        return cond["contains"].lower() in str(v or "").lower()
    if "truthy" in cond:
        return bool(v) is bool(cond["truthy"])
    return True


def visible_fields(form: dict, values: dict) -> list:
    return [fld for sec in form["sections"] for fld in sec["fields"]
            if _visible(fld, values)]


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def validate(form: dict, values: dict, *, consent: bool | None = None) -> list[dict]:
    """Field-level validation against the payer's own rules, run before we spend
    a payer transaction. Returns [] when the form is submittable."""
    values = normalise_values(form, values)
    errors: list[dict] = []
    family = form["family"]["id"]

    def err(field: str, message: str, label: str = ""):
        errors.append({"field": field, "label": label, "message": message})

    for fld in visible_fields(form, values):
        fid, val = fld["id"], values.get(fld["id"])
        if fld.get("required") and _is_blank(val) and fld["type"] != "checkbox":
            err(fid, f"{fld['label']} is required by this payer.", fld["label"])
            continue
        if _is_blank(val):
            continue
        if fld.get("pattern") and isinstance(val, str):
            if not re.match(fld["pattern"], val):
                err(fid, fld.get("pattern_message")
                    or f"{fld['label']} is not in the format this payer expects.", fld["label"])
        if fld.get("max_length") and isinstance(val, str) and len(val) > fld["max_length"]:
            err(fid, f"{fld['label']} is longer than {fld['max_length']} characters.",
                fld["label"])
        if fld["type"] == "date":
            try:
                d = date.fromisoformat(val)
            except (TypeError, ValueError):
                err(fid, f"{fld['label']} must be a date (YYYY-MM-DD).", fld["label"])
                continue
            if fid in ("dob", "subscriber_dob", "date_of_injury", "msp_accident_date",
                       "msp_esrd_first_dialysis") and d > date.today():
                err(fid, f"{fld['label']} cannot be in the future.", fld["label"])

    # --- payer rules that span more than one field --------------------------- #
    if family == "tricare":
        # The DoD ID is on the front of every card and is the single most common
        # wrong entry; TRICARE denies claims that carry it. (Source: tricare_id)
        for fid in ("dbn", "sponsor_ssn"):
            v = values.get(fid) or ""
            if isinstance(v, str) and re.match(DOD_ID_RE, v):
                err(fid, "That is a 10-digit DoD ID (EDIPI) from the front of the card. "
                         "TRICARE denies claims filed with it — use the 11-digit DoD Benefits "
                         "Number from the back of the card, or the sponsor's 9-digit SSN.",
                    "TRICARE identifier")
        if values.get("tricare_id_type") == "dbn" and _is_blank(values.get("dbn")) \
                and not _is_blank(values.get("sponsor_ssn")):
            err("tricare_id_type", "A sponsor SSN was entered — switch the identifier type to "
                                   "'Sponsor's SSN' so it is sent in the right field.", "")

    if values.get("alpha_prefix"):
        prefix, mid = values.get("alpha_prefix") or "", values.get("member_id") or ""
        if prefix and mid.upper().startswith(prefix.upper()):
            err("member_id", "The member ID already starts with the alpha prefix — enter only "
                             "the part that follows it, so the prefix is not doubled.",
                "Member ID")

    if family == "medicare_ffs" and values.get("msp_other_coverage") == "unknown":
        err("msp_other_coverage", "The Medicare Secondary Payer question must be answered yes or "
                                  "no before billing — Medicare rejects a claim filed while "
                                  "primacy is unresolved.", "Medicare Secondary Payer")

    if family in ("workers_comp", "auto_medical"):
        if _is_blank(values.get("pc_claim_number")) and _is_blank(values.get("pc_policy_number")):
            err("pc_claim_number", "Enter the claim number, or the policy number if the carrier "
                                    "has not issued a claim number yet — the carrier cannot "
                                    "match the bill without one of them.", "Claim number")

    # dates must be in order
    eff, end = values.get("policy_effective_date"), values.get("policy_end_date")
    if eff and end:
        try:
            if date.fromisoformat(end) < date.fromisoformat(eff):
                err("policy_end_date", "Coverage end date is before the effective date.",
                    "Coverage end date")
        except ValueError:
            pass

    if consent is False:
        err("consent", "Patient consent is required before the payer can be contacted.",
            "Consent")
    return errors


# --------------------------------------------------------------------------- #
# Mapping onto the real payer transaction
# --------------------------------------------------------------------------- #
_REL_X12 = {o["value"]: o["x12"] for o in RELATIONSHIP_OPTS}
# X12 EB03 / 270 service type codes. 30 = Health Benefit Plan Coverage (accepted
# by every payer); 88 = Pharmacy. (Source: stedi_270)
SERVICE_TYPE_MEDICAL = "30"
SERVICE_TYPE_PHARMACY = "88"


def to_eligibility(form: dict, values: dict) -> dict:
    """Map the captured policy onto the real 270 request parameters.

    Each field's `x12` annotation in the schema is the contract this implements,
    so the form and the payer call cannot drift apart.
    """
    values = normalise_values(form, values)
    family = form["family"]["id"]
    payer = form.get("payer") or {}

    member_id = values.get("member_id") or ""
    ssn = ""
    if family == "medicare_ffs":
        member_id = values.get("mbi") or ""
    elif family == "medicare_advantage":
        member_id = values.get("member_id") or values.get("mbi") or ""
    elif family == "medicaid":
        member_id = values.get("medicaid_id") or ""
    elif family == "tricare":
        if values.get("tricare_id_type") == "sponsor_ssn":
            ssn = values.get("sponsor_ssn") or ""
            member_id = ssn      # TRICARE identifies the benefit by sponsor SSN
        else:
            member_id = values.get("dbn") or ""
    elif family in ("workers_comp", "auto_medical"):
        member_id = values.get("pc_claim_number") or values.get("pc_policy_number") or ""

    # BlueCard: the alpha prefix is part of the ID the home plan matches on.
    prefix = (values.get("alpha_prefix") or "").upper()
    if prefix and member_id and not member_id.upper().startswith(prefix):
        member_id = prefix + member_id

    relationship = values.get("relationship") or "self"
    is_dependent = relationship != "self"
    if family in ("workers_comp", "auto_medical"):
        # The carrier matches a P&C bill on the claim number and the injured
        # person; there is no organization name in the subscriber loop, so
        # sending the employer as a nameless subscriber would fail outright.
        is_dependent = False
    patient_first = values.get("patient_first") or ""
    patient_last = values.get("patient_last") or ""

    if family == "tricare":
        sub_first = values.get("sponsor_first") or patient_first
        sub_last = values.get("sponsor_last") or patient_last
        # the sponsor is the subscriber; a family member is the dependent
        is_dependent = relationship != "self" or bool(
            values.get("sponsor_last") and values.get("sponsor_last") != patient_last)
    elif is_dependent:
        sub_first = values.get("subscriber_first") or ""
        sub_last = values.get("subscriber_last") or ""
    else:
        sub_first, sub_last = patient_first, patient_last

    params: dict = {
        "payer": payer.get("payer_id") or payer.get("name") or "",
        "member_id": member_id,
        "first_name": sub_first,
        "last_name": sub_last,
        "dob": (values.get("subscriber_dob") or "") if is_dependent
               else (values.get("dob") or ""),
        "service_type_codes": [SERVICE_TYPE_PHARMACY
                               if values.get("benefit_to_bill") == "pharmacy"
                               else SERVICE_TYPE_MEDICAL],
    }
    if ssn:
        params["ssn"] = ssn
    if values.get("group_number"):
        params["group_number"] = values["group_number"]
    if values.get("provider_pin"):
        # This payer authenticates the requesting provider with a program PIN,
        # carried as the portal secret. (Source: medicaid_pin)
        params["portal_password"] = values["provider_pin"]
    if is_dependent:
        params["dependent"] = {
            "firstName": patient_first,
            "lastName": patient_last,
            "dateOfBirth": values.get("dob") or "",
            "relationshipCode": _REL_X12.get(relationship, "34"),
        }
    if values.get("date_of_injury"):
        params["accident_date"] = values["date_of_injury"]
    if values.get("accident_state"):
        params["accident_state"] = values["accident_state"]
    if family == "workers_comp":
        params["claim_filing_code"] = "WC"
        # The employer is the policyholder on the bill, but the eligibility
        # subscriber loop carries no organization name — it rides on the claim.
        params["employer_name"] = values.get("employer_name") or ""
    elif family == "auto_medical":
        params["claim_filing_code"] = "AM"

    notes = []
    if (payer.get("eligibility_support") or "").upper() != "SUPPORTED":
        notes.append(f"This payer's published eligibility support is "
                     f"'{payer.get('eligibility_support') or 'unknown'}' — the check may return "
                     f"an access error rather than benefits.")
    if family == "medicaid" and is_dependent:
        notes.append("Most Medicaid programs do not support dependent-level searches; if the "
                     "payer returns 'subscriber not found', file with the patient's own "
                     "recipient ID as the subscriber.")
    if notes:
        params["notes"] = notes
    return params
