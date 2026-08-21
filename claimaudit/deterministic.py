"""
Tier 0 — deterministic pre-checks.

"Deterministic before probabilistic" is a design principle of the fleet: anything
settleable by a lookup, an arithmetic check or a rule is settled that way, and a
language model is used for judgement, not for arithmetic it will do worse.

Everything in this module is ordinary Python. It runs on 100% of claims, needs no
API key, and costs nothing. It also feeds the risk gate that decides which claims
are worth the cost of full agentic review.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime

from .schema import Citation, Claim, Finding, make_trace_id

TIER0_VERSION = "1.0.0"

# Code-shape patterns. Shape validity only — whether the code *exists* and is
# current is agent B01/B02's job against the licensed code sets.
_ICD10 = re.compile(r"^[A-TV-Z][0-9][0-9AB](?:\.[0-9A-TV-Z]{1,4})?$")
_CPT = re.compile(r"^(?:\d{5}|\d{4}[A-Z])$")
_HCPCS = re.compile(r"^[A-V]\d{4}$")

# Quantity ceilings by code family — a coarse, licence-free stand-in for the MUE
# tables.
_QTY_CEILING = {
    "surgical": 2,     # 10000–69999
    "radiology": 4,    # 70000–79999
    "pathology": 6,    # 80000–89999
    "medicine": 12,    # 90000–99199
    "em": 1,           # 99200–99499 evaluation & management
}


def _parse(d: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(d).strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _cpt_family(code: str) -> str | None:
    if not code.isdigit() or len(code) != 5:
        return None
    n = int(code)
    if 10000 <= n <= 69999:
        return "surgical"
    if 70000 <= n <= 79999:
        return "radiology"
    if 80000 <= n <= 89999:
        return "pathology"
    if 99200 <= n <= 99499:
        return "em"
    if 90000 <= n <= 99199:
        return "medicine"
    return None


def _finding(
    check_id: str,
    name: str,
    claim: Claim,
    result: str,
    severity: str,
    statement: str,
    rationale: str,
    exposure: float = 0.0,
    line_ref: str = "",
    action: str = "request_information",
    pacs: str = "coding_integrity",
    evidence: list[str] | None = None,
) -> Finding:
    return Finding(
        agent_id=check_id,
        agent_name=name,
        agent_version=TIER0_VERSION,
        squad="T0",
        claim_id=claim.claim_id,
        result=result,
        severity=severity,
        confidence=1.0,  # deterministic: the check either fires or it does not
        exposure_aed=round(exposure, 2),
        statement=statement,
        rationale=rationale,
        line_ref=line_ref,
        citations=[
            Citation(
                source_id="CANON",
                source_name="Canonical claim model and arithmetic rules",
                version=TIER0_VERSION,
                locator=check_id,
                passage="Deterministic rule evaluated in-application.",
                grounded=True,
            )
        ],
        evidence_refs=evidence or [],
        recommended_action=action,
        pacs_domain=pacs,
        model_ref="deterministic",
        trace_id=make_trace_id(claim.claim_id, check_id),
        tier=0,
        knowledge_mode="deterministic",
    )


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def run_tier0(claim: Claim) -> list[Finding]:
    out: list[Finding] = []

    # T0-01 — line arithmetic --------------------------------------------
    for a in claim.activities:
        expected = a.computed_amount
        if abs(expected - a.gross_amount) > 0.01:
            out.append(
                _finding(
                    "T0-01",
                    "Line arithmetic reconciliation",
                    claim,
                    "finding",
                    "moderate",
                    f"Line {a.line_ref} does not reconcile: "
                    f"{a.quantity} x AED {a.unit_price:,.2f} = AED {expected:,.2f}, "
                    f"but AED {a.gross_amount:,.2f} is billed.",
                    f"Quantity multiplied by unit price must equal the line gross amount. "
                    f"The variance is AED {abs(expected - a.gross_amount):,.2f}.",
                    exposure=abs(expected - a.gross_amount),
                    line_ref=a.line_ref,
                    action="deduct",
                    pacs="financial_integrity",
                    evidence=[f"activity {a.line_ref}"],
                )
            )

    # T0-02 — claim total reconciliation ---------------------------------
    if claim.activities:
        total = claim.line_total
        if abs(total - claim.gross_amount) > 0.01:
            out.append(
                _finding(
                    "T0-02",
                    "Claim total reconciliation",
                    claim,
                    "finding",
                    "moderate",
                    f"Itemised lines sum to AED {total:,.2f} but the claim header "
                    f"declares AED {claim.gross_amount:,.2f}.",
                    "The claim header gross amount must equal the sum of the itemised "
                    f"service lines. Variance AED {abs(total - claim.gross_amount):,.2f}.",
                    exposure=abs(total - claim.gross_amount),
                    action="request_information",
                    pacs="financial_integrity",
                )
            )

    expected_net = round(claim.gross_amount - claim.patient_share, 2)
    if abs(expected_net - claim.net_amount) > 0.01:
        out.append(
            _finding(
                "T0-03",
                "Member share reconciliation",
                claim,
                "finding",
                "moderate",
                f"Gross AED {claim.gross_amount:,.2f} less member share "
                f"AED {claim.patient_share:,.2f} is AED {expected_net:,.2f}, "
                f"but AED {claim.net_amount:,.2f} is claimed from the insurer.",
                "Net claimed must equal gross billed less the member share applied.",
                exposure=abs(expected_net - claim.net_amount),
                action="deduct",
                pacs="financial_integrity",
            )
        )

    # T0-04 — date sequencing --------------------------------------------
    start, end = _parse(claim.encounter_start), _parse(claim.encounter_end)
    submitted = _parse(claim.submission_date)

    if start and end and end < start:
        out.append(
            _finding(
                "T0-04",
                "Impossible date sequence",
                claim,
                "finding",
                "major",
                f"Encounter ends {claim.encounter_end}, before it starts "
                f"{claim.encounter_start}.",
                "The encounter end timestamp precedes the start timestamp.",
                action="request_information",
                pacs="documentation",
            )
        )
    if submitted and end and submitted < end:
        out.append(
            _finding(
                "T0-04",
                "Impossible date sequence",
                claim,
                "finding",
                "moderate",
                f"Claim submitted {claim.submission_date}, before the encounter "
                f"ended {claim.encounter_end}.",
                "A claim cannot be submitted before the episode of care concludes.",
                action="request_information",
                pacs="documentation",
            )
        )

    for a in claim.activities:
        ad = _parse(a.start_date)
        if ad and start and end and not (start <= ad <= end):
            out.append(
                _finding(
                    "T0-05",
                    "Activity outside the encounter window",
                    claim,
                    "finding",
                    "moderate",
                    f"Line {a.line_ref} is dated {a.start_date}, outside the "
                    f"encounter window {claim.encounter_start} to {claim.encounter_end}.",
                    "Every billed activity must fall inside the declared encounter "
                    "period, or be attached to a different encounter.",
                    exposure=a.gross_amount,
                    line_ref=a.line_ref,
                    action="request_information",
                    pacs="documentation",
                    evidence=[f"activity {a.line_ref}"],
                )
            )

    # T0-06 — cover in force on the date of service ----------------------
    ps, pe = _parse(claim.policy_start), _parse(claim.policy_end)
    if start and ps and pe and not (ps <= start <= pe):
        out.append(
            _finding(
                "T0-06",
                "Service outside the policy period",
                claim,
                "finding",
                "critical",
                f"Date of service {claim.encounter_start} falls outside the policy "
                f"period {claim.policy_start} to {claim.policy_end}.",
                "Cover must be in force on the date of service. A service rendered "
                "before inception or after termination is not payable.",
                exposure=claim.net_amount,
                action="deny",
                pacs="policy_adjudication",
            )
        )

    # T0-07 — encounter type against length of stay -----------------------
    los = claim.length_of_stay_days
    if start and end:
        derived = (end - start).days
        if claim.encounter_type == "inpatient" and derived <= 0:
            out.append(
                _finding(
                    "T0-07",
                    "Encounter type and setting consistency",
                    claim,
                    "finding",
                    "moderate",
                    "Encounter is declared inpatient but admission and discharge fall "
                    "on the same day.",
                    "An admission and discharge on the same calendar day is a day case, "
                    "which is priced differently from an inpatient admission.",
                    action="request_information",
                    pacs="coding_integrity",
                )
            )
        if claim.encounter_type in ("outpatient", "daycase") and derived > 0:
            out.append(
                _finding(
                    "T0-07",
                    "Encounter type and setting consistency",
                    claim,
                    "finding",
                    "moderate",
                    f"Encounter is declared {claim.encounter_type} but spans "
                    f"{derived} day(s).",
                    "An encounter spanning more than one calendar day is an inpatient "
                    "admission, not an outpatient or day case attendance.",
                    action="request_information",
                    pacs="coding_integrity",
                )
            )
        if los and derived and abs(los - derived) > 1:
            out.append(
                _finding(
                    "T0-08",
                    "Declared length of stay mismatch",
                    claim,
                    "finding",
                    "minor",
                    f"Declared length of stay is {los} day(s); the admission and "
                    f"discharge dates give {derived}.",
                    "Length of stay is a derived field and must agree with the "
                    "encounter timestamps.",
                    action="request_information",
                    pacs="documentation",
                )
            )

    # T0-09 — code shape validity ----------------------------------------
    for d in claim.diagnoses:
        if d.code_system.startswith("ICD") and not _ICD10.match(d.diagnosis_code.upper()):
            out.append(
                _finding(
                    "T0-09",
                    "Code format validity",
                    claim,
                    "finding",
                    "minor",
                    f"Diagnosis code {d.diagnosis_code} is not a well-formed "
                    f"{d.code_system} code.",
                    "ICD-10 codes take the form letter, digit, digit or letter, "
                    "optionally followed by a point and up to four characters.",
                    action="request_information",
                    pacs="coding_integrity",
                )
            )
    for a in claim.activities:
        code = a.activity_code.upper()
        if a.code_system == "CPT" and not _CPT.match(code):
            out.append(
                _finding(
                    "T0-09",
                    "Code format validity",
                    claim,
                    "finding",
                    "minor",
                    f"Line {a.line_ref}: {a.activity_code} is not a well-formed CPT code.",
                    "CPT codes are five digits, or four digits followed by a letter for "
                    "Category II and III codes.",
                    line_ref=a.line_ref,
                    action="request_information",
                    pacs="coding_integrity",
                )
            )
        if a.code_system == "HCPCS" and not _HCPCS.match(code):
            out.append(
                _finding(
                    "T0-09",
                    "Code format validity",
                    claim,
                    "finding",
                    "minor",
                    f"Line {a.line_ref}: {a.activity_code} is not a well-formed "
                    "HCPCS Level II code.",
                    "HCPCS Level II codes are one letter A–V followed by four digits.",
                    line_ref=a.line_ref,
                    action="request_information",
                    pacs="coding_integrity",
                )
            )

    # T0-10 — principal diagnosis present ---------------------------------
    if not claim.diagnoses:
        out.append(
            _finding(
                "T0-10",
                "Mandatory element missing",
                claim,
                "finding",
                "major",
                "The claim carries no diagnosis codes.",
                "At least one diagnosis is mandatory; without it the clinical "
                "coherence and necessity checks cannot be performed at all.",
                action="request_information",
                pacs="documentation",
            )
        )
    elif not claim.principal_diagnosis:
        out.append(
            _finding(
                "T0-10",
                "Mandatory element missing",
                claim,
                "finding",
                "moderate",
                "No diagnosis is designated as principal.",
                "Exactly one diagnosis must be sequenced as principal; this drives "
                "DRG assignment and payment.",
                action="request_information",
                pacs="coding_integrity",
            )
        )
    else:
        principals = [d for d in claim.diagnoses if d.diagnosis_type == "principal"]
        if len(principals) > 1:
            out.append(
                _finding(
                    "T0-10",
                    "Mandatory element missing",
                    claim,
                    "finding",
                    "moderate",
                    f"{len(principals)} diagnoses are designated principal.",
                    "Exactly one diagnosis may be sequenced as principal.",
                    action="request_information",
                    pacs="coding_integrity",
                )
            )

    # T0-11 — exact duplicate lines ---------------------------------------
    seen = Counter(
        (a.activity_code, a.start_date, a.quantity, a.unit_price)
        for a in claim.activities
    )
    for (code, dos, qty, price), n in seen.items():
        if n > 1:
            refs = [
                a.line_ref
                for a in claim.activities
                if (a.activity_code, a.start_date, a.quantity, a.unit_price)
                == (code, dos, qty, price)
            ]
            dup_value = qty * price * (n - 1)
            out.append(
                _finding(
                    "T0-11",
                    "Duplicate line within claim",
                    claim,
                    "finding",
                    "major",
                    f"{code} appears {n} times on {dos} with identical quantity and "
                    f"price (lines {', '.join(refs)}).",
                    "Identical code, date, quantity and unit price on the same claim is "
                    "a duplicate unless a repeat-procedure modifier documents otherwise.",
                    exposure=dup_value,
                    line_ref=refs[-1],
                    action="deduct",
                    pacs="financial_integrity",
                    evidence=[f"activity {r}" for r in refs],
                )
            )

    # T0-12 — quantity plausibility ---------------------------------------
    for a in claim.activities:
        fam = _cpt_family(a.activity_code) if a.code_system == "CPT" else None
        ceiling = _QTY_CEILING.get(fam, 0)
        if fam == "em" and claim.encounter_type in ("inpatient", "daycase"):
            # Daily subsequent-care visits are expected across an admission, so the
            # ceiling scales with the stay rather than sitting at one per encounter.
            ceiling = max(1, claim.length_of_stay_days or 1)
        if fam and a.quantity > ceiling:
            out.append(
                _finding(
                    "T0-12",
                    "Quantity plausibility ceiling",
                    claim,
                    "finding",
                    "moderate",
                    f"Line {a.line_ref}: quantity {a.quantity:g} on {a.activity_code} "
                    f"exceeds the plausible ceiling of {ceiling} for a "
                    f"{fam} code on one encounter.",
                    "Quantities above the per-encounter ceiling are usually a unit or "
                    "decimal error; the excess units are treated as at risk pending "
                    "confirmation against the licensed edit tables.",
                    exposure=(a.quantity - _QTY_CEILING[fam]) * a.unit_price,
                    line_ref=a.line_ref,
                    action="request_information",
                    pacs="financial_integrity",
                    evidence=[f"activity {a.line_ref}"],
                )
            )

    # T0-13 — documentation present ---------------------------------------
    surgical = [
        a
        for a in claim.activities
        if a.code_system == "CPT" and _cpt_family(a.activity_code) == "surgical"
    ]
    if surgical and not any(
        k in " ".join(claim.attachments).lower()
        for k in ("operative", "surgery", "procedure report", "op note")
    ):
        out.append(
            _finding(
                "T0-13",
                "Documentation sufficiency",
                claim,
                "finding",
                "major",
                f"{len(surgical)} surgical line(s) billed with no operative note "
                "among the attachments.",
                "A surgical claim requires an operative note. Without it the coding, "
                "laterality and bundling checks cannot be evidenced.",
                exposure=sum(a.gross_amount for a in surgical),
                action="request_information",
                pacs="documentation",
                evidence=[f"activity {a.line_ref}" for a in surgical],
            )
        )

    return out


# --------------------------------------------------------------------------
# Risk gate (Section 5.6 — risk-triaged execution)
# --------------------------------------------------------------------------


def risk_score(claim: Claim, tier0: list[Finding]) -> tuple[int, list[str]]:
    """Score 0–100 and the reasons, combining deterministic hits with claim value."""
    score, reasons = 0, []

    hits = [f for f in tier0 if f.is_finding]
    if hits:
        weight = {"critical": 30, "major": 18, "moderate": 9, "minor": 3}
        s = sum(weight.get(f.severity, 3) for f in hits)
        score += min(s, 55)
        reasons.append(f"{len(hits)} deterministic rule hit(s)")

    if claim.gross_amount >= 50_000:
        score += 25
        reasons.append("claim value at or above AED 50,000")
    elif claim.gross_amount >= 15_000:
        score += 15
        reasons.append("claim value at or above AED 15,000")
    elif claim.gross_amount >= 5_000:
        score += 8
        reasons.append("claim value at or above the pre-authorisation threshold")

    if claim.encounter_type in ("inpatient", "daycase"):
        score += 10
        reasons.append(f"{claim.encounter_type} setting")

    if claim.prior_auth_status in ("not_obtained", "expired", "mismatch"):
        score += 12
        reasons.append(f"pre-authorisation {claim.prior_auth_status.replace('_', ' ')}")

    if claim.place_of_treatment.strip().lower() not in (
        "united arab emirates",
        "uae",
    ):
        score += 15
        reasons.append("treatment outside the UAE")

    if claim.network_tier.lower() not in ("gold", "gold network"):
        score += 8
        reasons.append(f"non-standard network tier ({claim.network_tier})")

    return min(score, 100), reasons


def risk_band(score: int) -> str:
    if score >= 60:
        return "High"
    if score >= 30:
        return "Medium"
    return "Low"
