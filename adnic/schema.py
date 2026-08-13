"""
Canonical claim model and the uniform agent output contract.

The shapes here follow Appendix B (canonical claim model) and Appendix C
(agent output schema) of the ADNIC proposal. Everything is plain dataclasses
and dicts — no ORM, no database. A demo run holds the whole book of claims in
session state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any


# --------------------------------------------------------------------------
# Controlled vocabularies (Appendix B / Table 13)
# --------------------------------------------------------------------------

ENCOUNTER_TYPES = [
    "inpatient",
    "daycase",
    "outpatient",
    "emergency",
    "home",
    "telemedicine",
]

CODE_SYSTEMS = ["CPT", "HCPCS", "dental", "drug", "service", "DRG"]
DIAGNOSIS_SYSTEMS = ["ICD-10-CM", "ICD-10-AM"]
DIAGNOSIS_TYPES = ["principal", "secondary", "admitting", "external_cause"]

RESULTS = ["finding", "no_finding", "insufficient_evidence", "not_applicable", "error"]
SEVERITIES = ["critical", "major", "moderate", "minor"]
SEVERITY_RANK = {"critical": 4, "major": 3, "moderate": 2, "minor": 1}

ACTIONS = [
    "accept",
    "deduct",
    "deny",
    "request_information",
    "refer_clinical",
    "refer_siu",
    "monitor",
]

PACS_DOMAINS = [
    "coding_integrity",
    "clinical_appropriateness",
    "policy_adjudication",
    "documentation",
    "financial_integrity",
    "none",
]

HUMAN_DECISIONS = ["pending", "accepted", "amended", "rejected", "escalated"]

DISPOSITIONS = [
    "approve",
    "partial_approve",
    "deny",
    "refer_clinical",
    "refer_siu",
    "request_information",
]


# --------------------------------------------------------------------------
# Canonical claim model
# --------------------------------------------------------------------------


@dataclass
class Activity:
    """One billed service line (Appendix B — activity)."""

    line_ref: str
    activity_code: str
    code_system: str
    description: str
    quantity: float
    unit_price: float
    gross_amount: float
    modifiers: list[str] = field(default_factory=list)
    start_date: str = ""
    duration_min: int | None = None
    performing_clinician: str = ""

    @property
    def computed_amount(self) -> float:
        return round(self.quantity * self.unit_price, 2)


@dataclass
class Diagnosis:
    """One coded diagnosis (Appendix B — diagnosis)."""

    diagnosis_code: str
    code_system: str
    diagnosis_type: str
    sequence: int
    description: str
    present_on_admission: bool | None = None


@dataclass
class Claim:
    """A whole claim: header, encounter, member surrogate, provider, lines."""

    # claim
    claim_id: str
    source_channel: str
    submission_date: str
    gross_amount: float
    patient_share: float
    net_amount: float

    # encounter
    encounter_type: str
    encounter_start: str
    encounter_end: str
    facility_name: str
    facility_licence_id: str
    facility_type: str
    network_tier: str
    emirate: str
    clinician_name: str
    clinician_licence_id: str
    clinician_specialty: str

    # member surrogate (Zone 2 — no direct identifiers)
    member_sk: str
    member_age: int
    member_gender: str
    policy_number: str
    plan_code: str
    policy_start: str
    policy_end: str
    scheme_inception: str

    # adjudication context
    prior_auth_number: str = ""
    prior_auth_status: str = "not_obtained"
    drg_code: str = ""
    length_of_stay_days: int = 0
    place_of_treatment: str = "United Arab Emirates"

    # clinical narrative + attachments
    clinical_notes: str = ""
    attachments: list[str] = field(default_factory=list)

    # child collections
    activities: list[Activity] = field(default_factory=list)
    diagnoses: list[Diagnosis] = field(default_factory=list)

    # demo metadata — never shown to the agents
    demo_note: str = ""

    # ---------------------------------------------------------------- helpers

    @property
    def principal_diagnosis(self) -> Diagnosis | None:
        for d in self.diagnoses:
            if d.diagnosis_type == "principal":
                return d
        return self.diagnoses[0] if self.diagnoses else None

    @property
    def line_total(self) -> float:
        return round(sum(a.gross_amount for a in self.activities), 2)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def to_agent_context(self, include_notes: bool = True) -> str:
        """Render the claim as the de-identified text block an agent reads.

        Nothing here is a direct personal identifier: the member is a surrogate
        key with an age band and gender, matching Zone 2 of the proposal's
        trust-zone model.
        """
        band_lo = (self.member_age // 5) * 5
        age_band = f"{band_lo}-{band_lo + 4}" if self.member_age < 90 else "90+"

        lines = [
            f"CLAIM {self.claim_id}",
            f"Submission date: {self.submission_date}   Channel: {self.source_channel}",
            "",
            "ENCOUNTER",
            f"  Type: {self.encounter_type}",
            f"  Start: {self.encounter_start}   End: {self.encounter_end}"
            + (f"   Length of stay: {self.length_of_stay_days} day(s)" if self.length_of_stay_days else ""),
            f"  Place of treatment: {self.place_of_treatment} ({self.emirate})",
            f"  Facility: {self.facility_name} [{self.facility_type}, licence {self.facility_licence_id}]",
            f"  Network tier billed: {self.network_tier}",
            f"  Treating clinician: {self.clinician_name} "
            f"[{self.clinician_specialty}, licence {self.clinician_licence_id}]",
            f"  Billed DRG: {self.drg_code or 'n/a'}",
            "",
            "MEMBER (surrogate)",
            f"  Member key: {self.member_sk}   Age band: {age_band}   Gender: {self.member_gender}",
            f"  Policy: {self.policy_number}   Plan: {self.plan_code}",
            f"  Policy period: {self.policy_start} to {self.policy_end}",
            f"  Scheme inception (waiting periods run from here): {self.scheme_inception}",
            f"  Pre-authorisation: {self.prior_auth_status}"
            + (f" ({self.prior_auth_number})" if self.prior_auth_number else ""),
            "",
            "DIAGNOSES",
        ]
        for d in sorted(self.diagnoses, key=lambda x: x.sequence):
            poa = ""
            if d.present_on_admission is not None:
                poa = f", present on admission: {'yes' if d.present_on_admission else 'no'}"
            lines.append(
                f"  {d.sequence}. [{d.diagnosis_type}] {d.diagnosis_code} "
                f"({d.code_system}) — {d.description}{poa}"
            )

        lines += ["", "BILLED ACTIVITIES"]
        for a in self.activities:
            mods = f" modifiers={','.join(a.modifiers)}" if a.modifiers else ""
            dur = f" duration={a.duration_min}min" if a.duration_min else ""
            lines.append(
                f"  {a.line_ref}: {a.activity_code} ({a.code_system}) — {a.description}"
                f"{mods} | qty {a.quantity} x AED {a.unit_price:,.2f} "
                f"= AED {a.gross_amount:,.2f} | date {a.start_date}{dur}"
                f" | performed by {a.performing_clinician or 'not stated'}"
            )

        lines += [
            "",
            "FINANCIALS (AED)",
            f"  Gross billed: {self.gross_amount:,.2f}",
            f"  Member share applied: {self.patient_share:,.2f}",
            f"  Net claimed from insurer: {self.net_amount:,.2f}",
            f"  Sum of billed lines: {self.line_total:,.2f}",
            "",
            "SUPPORTING DOCUMENTATION ATTACHED",
        ]
        lines += [f"  - {doc}" for doc in self.attachments] or ["  - none attached"]

        if include_notes and self.clinical_notes:
            lines += ["", "CLINICAL RECORD EXTRACT", self.clinical_notes.strip()]

        return "\n".join(lines)


# --------------------------------------------------------------------------
# Agent output contract (Table 13 / Appendix C)
# --------------------------------------------------------------------------


@dataclass
class Citation:
    source_id: str
    source_name: str
    version: str
    locator: str
    passage: str = ""
    grounded: bool = False  # True when retrieved from the in-app corpus


@dataclass
class Finding:
    agent_id: str
    agent_name: str
    agent_version: str
    squad: str
    claim_id: str
    result: str
    severity: str
    confidence: float
    exposure_aed: float
    statement: str
    rationale: str
    line_ref: str = ""
    citations: list[Citation] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    recommended_action: str = "monitor"
    pacs_domain: str = "none"
    model_ref: str = ""
    trace_id: str = ""
    tier: int = 0
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    knowledge_mode: str = "model_memory"

    # human-in-the-loop state — mandatory before any downstream effect
    human_decision: str = "pending"
    decided_by: str = ""
    decided_ts: str = ""
    amended_exposure_aed: float | None = None
    reviewer_note: str = ""

    @property
    def key(self) -> str:
        return f"{self.claim_id}::{self.agent_id}::{self.line_ref or 'CLAIM'}"

    @property
    def effective_exposure(self) -> float:
        if self.human_decision == "rejected":
            return 0.0
        if self.amended_exposure_aed is not None:
            return float(self.amended_exposure_aed)
        return float(self.exposure_aed)

    @property
    def is_finding(self) -> bool:
        return self.result == "finding"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["effective_exposure_aed"] = self.effective_exposure
        return d


def make_trace_id(claim_id: str, agent_id: str) -> str:
    raw = f"{claim_id}|{agent_id}|{datetime.now().isoformat()}"
    return "tr_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# Consolidated claim-level result
# --------------------------------------------------------------------------


@dataclass
class ClaimResult:
    claim_id: str
    findings: list[Finding] = field(default_factory=list)
    consolidation: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    error: str = ""

    # ------------------------------------------------------------------ views

    def open_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.is_finding]

    def by_severity(self) -> dict[str, int]:
        out = {s: 0 for s in SEVERITIES}
        for f in self.open_findings():
            if f.human_decision != "rejected":
                out[f.severity] = out.get(f.severity, 0) + 1
        return out

    @property
    def max_severity(self) -> str | None:
        live = [f for f in self.open_findings() if f.human_decision != "rejected"]
        if not live:
            return None
        return max(live, key=lambda f: SEVERITY_RANK.get(f.severity, 0)).severity

    @property
    def total_exposure(self) -> float:
        """Exposure with overlap removed: per line, take the largest exposure."""
        by_line: dict[str, float] = {}
        for f in self.open_findings():
            if f.human_decision == "rejected":
                continue
            k = f.line_ref or "CLAIM"
            by_line[k] = max(by_line.get(k, 0.0), f.effective_exposure)
        return round(sum(by_line.values()), 2)

    @property
    def reviewed_count(self) -> int:
        return len([f for f in self.open_findings() if f.human_decision != "pending"])

    @property
    def review_complete(self) -> bool:
        opened = self.open_findings()
        return bool(opened) and self.reviewed_count == len(opened)


# --------------------------------------------------------------------------
# JSON helpers
# --------------------------------------------------------------------------


def _default(o: Any) -> Any:
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(f"not JSON serialisable: {type(o)}")


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=_default, ensure_ascii=False)
