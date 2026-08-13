"""
Claim ingestion: the upload contract, validation, and the downloadable template.

The canonical claim model is nested — a claim has an encounter, service lines and
diagnoses — so a single flat sheet cannot express it without either repeating the
header on every line or losing the line detail. The upload format is therefore a
three-sheet workbook with a shared key:

    Claims       one row per claim   — header, encounter, member, provider
    Activities   one row per line    — the billed services, keyed by Claim ID
    Diagnoses    one row per code    — the coded diagnoses, keyed by Claim ID

A single-sheet CSV is also accepted for a quick look: it must be the Claims sheet,
and claims uploaded that way carry no service lines, so the line-level agents will
correctly return insufficient_evidence rather than guessing.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .schema import (
    CODE_SYSTEMS,
    DIAGNOSIS_TYPES,
    ENCOUNTER_TYPES,
    Activity,
    Claim,
    Diagnosis,
)


@dataclass
class ColumnSpec:
    name: str
    required: bool
    kind: str          # text | number | date | enum | list
    description: str
    example: str
    allowed: tuple[str, ...] = ()


# --------------------------------------------------------------------------
# Sheet 1 — Claims
# --------------------------------------------------------------------------

CLAIMS_COLUMNS: list[ColumnSpec] = [
    ColumnSpec("Claim ID", True, "text",
               "Unique identifier for the claim. Must match the Claim ID used on the "
               "Activities and Diagnoses sheets.", "CLM-2026-000101"),
    ColumnSpec("Source Channel", False, "enum",
               "How the claim reached you.", "direct",
               ("direct", "tpa_1", "tpa_2", "tpa_3", "tpa_4", "reimbursement")),
    ColumnSpec("Submission Date", True, "date", "Date the claim was submitted (YYYY-MM-DD).",
               "2026-06-18"),
    ColumnSpec("Encounter Type", True, "enum",
               "The setting in which care was delivered.", "outpatient",
               tuple(ENCOUNTER_TYPES)),
    ColumnSpec("Encounter Start", True, "date",
               "Admission or attendance date (YYYY-MM-DD).", "2026-06-16"),
    ColumnSpec("Encounter End", True, "date",
               "Discharge or end-of-attendance date (YYYY-MM-DD).", "2026-06-16"),
    ColumnSpec("Length Of Stay Days", False, "number",
               "Inpatient bed days. 0 for outpatient and day case.", "0"),
    ColumnSpec("Place Of Treatment", False, "text",
               "Country where treatment was delivered. Drives the territorial check.",
               "United Arab Emirates"),
    ColumnSpec("Emirate", False, "text", "Emirate of treatment, or n/a if overseas.",
               "Abu Dhabi"),
    ColumnSpec("Facility Name", True, "text", "Treating facility.",
               "Al Noor Orthopaedic Centre"),
    ColumnSpec("Facility Licence ID", False, "text", "Regulator licence number of the facility.",
               "DOH-F-0004821"),
    ColumnSpec("Facility Type", False, "text",
               "Hospital, Clinic, Day Surgery Centre, Dental Clinic, Optical Centre, etc.",
               "Clinic"),
    ColumnSpec("Network Tier", False, "text",
               "Network tier billed against.", "Gold"),
    ColumnSpec("Clinician Name", False, "text", "Treating clinician.",
               "Dr Faisal Al Marzooqi"),
    ColumnSpec("Clinician Licence ID", False, "text", "Regulator licence number of the clinician.",
               "DOH-P-0091274"),
    ColumnSpec("Clinician Specialty", False, "text", "Specialty of the treating clinician.",
               "Orthopaedic Surgery"),
    ColumnSpec("Member Key", True, "text",
               "SURROGATE member key. Do not upload names, Emirates ID numbers, passport "
               "numbers or dates of birth — the platform does not need them and will not "
               "send them to a model.", "MBR-4471902"),
    ColumnSpec("Member Age", True, "number",
               "Age in years. Used only to derive a five-year age band.", "38"),
    ColumnSpec("Member Gender", True, "text", "male / female.", "male"),
    ColumnSpec("Policy Number", True, "text", "Policy or scheme identifier.", "POL-CORP-88214"),
    ColumnSpec("Plan Code", True, "text",
               "Product code. Selects the policy wording used by Squad E.",
               "ADN-COMP-GOLD-2026"),
    ColumnSpec("Policy Start", True, "date", "Policy period start (YYYY-MM-DD).", "2026-01-01"),
    ColumnSpec("Policy End", True, "date", "Policy period end (YYYY-MM-DD).", "2026-12-31"),
    ColumnSpec("Scheme Inception", True, "date",
               "Date the member's cover under this scheme began. Waiting periods are "
               "calculated from this date, so it must be right.", "2024-01-01"),
    ColumnSpec("Prior Auth Status", False, "enum",
               "Pre-authorisation state for this claim.", "not_obtained",
               ("obtained", "not_obtained", "not_required", "expired", "mismatch")),
    ColumnSpec("Prior Auth Number", False, "text", "Authorisation reference, if obtained.",
               "PA-2026-114552"),
    ColumnSpec("DRG Code", False, "text", "DRG as billed, if applicable.", ""),
    ColumnSpec("Gross Amount", True, "number", "Total billed, AED.", "1490.00"),
    ColumnSpec("Patient Share", True, "number",
               "Member share applied, AED (co-payment plus co-insurance plus deductible).",
               "258.00"),
    ColumnSpec("Net Amount", True, "number",
               "Amount claimed from the insurer, AED. Must equal Gross Amount less "
               "Patient Share.", "1232.00"),
    ColumnSpec("Attachments", False, "list",
               "Documents attached, separated by a semicolon.",
               "Consultation note; Physiotherapy session log"),
    ColumnSpec("Clinical Notes", False, "text",
               "The clinical record extract the agents read. This is where necessity, "
               "length of stay, indication and documentation findings come from — a thin "
               "note produces insufficient_evidence, not a finding.",
               "Post-operative review. Arthroscopic partial medial meniscectomy..."),
]

# --------------------------------------------------------------------------
# Sheet 2 — Activities
# --------------------------------------------------------------------------

ACTIVITIES_COLUMNS: list[ColumnSpec] = [
    ColumnSpec("Claim ID", True, "text", "Foreign key to the Claims sheet.", "CLM-2026-000101"),
    ColumnSpec("Line Ref", True, "text",
               "Unique line reference within the claim. Findings attach to this.", "ACT-001"),
    ColumnSpec("Activity Code", True, "text", "The billed code.", "97110"),
    ColumnSpec("Code System", True, "enum", "Which code set the code belongs to.", "CPT",
               tuple(CODE_SYSTEMS)),
    ColumnSpec("Description", True, "text", "Description of the service billed.",
               "Therapeutic exercise, each 15 minutes"),
    ColumnSpec("Quantity", True, "number", "Units billed.", "4"),
    ColumnSpec("Unit Price", True, "number", "Price per unit, AED.", "180.00"),
    ColumnSpec("Gross Amount", True, "number",
               "Line total, AED. Quantity x Unit Price is checked against this.", "720.00"),
    ColumnSpec("Modifiers", False, "list",
               "Modifiers in order, separated by a semicolon.", "25; 59"),
    ColumnSpec("Start Date", True, "date", "Date the service was delivered (YYYY-MM-DD).",
               "2026-06-16"),
    ColumnSpec("Duration Min", False, "number", "Duration in minutes, where recorded.", "60"),
    ColumnSpec("Performing Clinician", False, "text", "Who performed the service.",
               "S Raghavan, PT"),
]

# --------------------------------------------------------------------------
# Sheet 3 — Diagnoses
# --------------------------------------------------------------------------

DIAGNOSES_COLUMNS: list[ColumnSpec] = [
    ColumnSpec("Claim ID", True, "text", "Foreign key to the Claims sheet.", "CLM-2026-000101"),
    ColumnSpec("Diagnosis Code", True, "text", "The coded diagnosis.", "M23.322"),
    ColumnSpec("Code System", True, "enum", "ICD edition in use.", "ICD-10-CM",
               ("ICD-10-CM", "ICD-10-AM")),
    ColumnSpec("Diagnosis Type", True, "enum",
               "Exactly one diagnosis per claim must be principal.", "principal",
               tuple(DIAGNOSIS_TYPES)),
    ColumnSpec("Sequence", True, "number", "Coding order, starting at 1.", "1"),
    ColumnSpec("Description", True, "text", "Description of the diagnosis.",
               "Other meniscus derangements, posterior horn of medial meniscus, left knee"),
    ColumnSpec("Present On Admission", False, "text",
               "yes / no / blank. Inpatient claims only.", "yes"),
]

SHEETS = {
    "Claims": CLAIMS_COLUMNS,
    "Activities": ACTIVITIES_COLUMNS,
    "Diagnoses": DIAGNOSES_COLUMNS,
}


# --------------------------------------------------------------------------
# Template
# --------------------------------------------------------------------------


def _example_frame(cols: list[ColumnSpec], rows: list[dict[str, Any]]) -> pd.DataFrame:
    names = [c.name for c in cols]
    if not rows:
        return pd.DataFrame(columns=names)
    return pd.DataFrame(rows, columns=names)


def build_template_workbook() -> bytes:
    """A ready-to-fill workbook: the three sheets, a worked example, and a data dictionary."""
    claims_rows = [{c.name: c.example for c in CLAIMS_COLUMNS}]
    act_rows = [
        {c.name: c.example for c in ACTIVITIES_COLUMNS},
        {
            "Claim ID": "CLM-2026-000101",
            "Line Ref": "ACT-002",
            "Activity Code": "99214",
            "Code System": "CPT",
            "Description": "Office visit, established patient, moderate complexity",
            "Quantity": "1",
            "Unit Price": "450.00",
            "Gross Amount": "450.00",
            "Modifiers": "25",
            "Start Date": "2026-06-16",
            "Duration Min": "25",
            "Performing Clinician": "Dr Faisal Al Marzooqi",
        },
    ]
    dx_rows = [
        {c.name: c.example for c in DIAGNOSES_COLUMNS},
        {
            "Claim ID": "CLM-2026-000101",
            "Diagnosis Code": "Z98.890",
            "Code System": "ICD-10-CM",
            "Diagnosis Type": "secondary",
            "Sequence": "2",
            "Description": "Other specified postprocedural states",
            "Present On Admission": "",
        },
    ]

    dictionary_rows = []
    for sheet, cols in SHEETS.items():
        for c in cols:
            dictionary_rows.append(
                {
                    "Sheet": sheet,
                    "Column": c.name,
                    "Required": "Yes" if c.required else "Optional",
                    "Type": c.kind,
                    "Allowed values": ", ".join(c.allowed) if c.allowed else "",
                    "Description": c.description,
                    "Example": c.example,
                }
            )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _example_frame(CLAIMS_COLUMNS, claims_rows).to_excel(
            writer, index=False, sheet_name="Claims"
        )
        _example_frame(ACTIVITIES_COLUMNS, act_rows).to_excel(
            writer, index=False, sheet_name="Activities"
        )
        _example_frame(DIAGNOSES_COLUMNS, dx_rows).to_excel(
            writer, index=False, sheet_name="Diagnoses"
        )
        pd.DataFrame(dictionary_rows).to_excel(
            writer, index=False, sheet_name="Data dictionary"
        )
    buf.seek(0)
    return buf.getvalue()


def build_demo_workbook(claims: list[Claim]) -> bytes:
    """Export a set of claims in the upload format — the demo book round-trips."""
    claim_rows, act_rows, dx_rows = [], [], []
    for c in claims:
        claim_rows.append(
            {
                "Claim ID": c.claim_id,
                "Source Channel": c.source_channel,
                "Submission Date": c.submission_date,
                "Encounter Type": c.encounter_type,
                "Encounter Start": c.encounter_start,
                "Encounter End": c.encounter_end,
                "Length Of Stay Days": c.length_of_stay_days,
                "Place Of Treatment": c.place_of_treatment,
                "Emirate": c.emirate,
                "Facility Name": c.facility_name,
                "Facility Licence ID": c.facility_licence_id,
                "Facility Type": c.facility_type,
                "Network Tier": c.network_tier,
                "Clinician Name": c.clinician_name,
                "Clinician Licence ID": c.clinician_licence_id,
                "Clinician Specialty": c.clinician_specialty,
                "Member Key": c.member_sk,
                "Member Age": c.member_age,
                "Member Gender": c.member_gender,
                "Policy Number": c.policy_number,
                "Plan Code": c.plan_code,
                "Policy Start": c.policy_start,
                "Policy End": c.policy_end,
                "Scheme Inception": c.scheme_inception,
                "Prior Auth Status": c.prior_auth_status,
                "Prior Auth Number": c.prior_auth_number,
                "DRG Code": c.drg_code,
                "Gross Amount": c.gross_amount,
                "Patient Share": c.patient_share,
                "Net Amount": c.net_amount,
                "Attachments": "; ".join(c.attachments),
                "Clinical Notes": c.clinical_notes,
            }
        )
        for a in c.activities:
            act_rows.append(
                {
                    "Claim ID": c.claim_id,
                    "Line Ref": a.line_ref,
                    "Activity Code": a.activity_code,
                    "Code System": a.code_system,
                    "Description": a.description,
                    "Quantity": a.quantity,
                    "Unit Price": a.unit_price,
                    "Gross Amount": a.gross_amount,
                    "Modifiers": "; ".join(a.modifiers),
                    "Start Date": a.start_date,
                    "Duration Min": a.duration_min if a.duration_min is not None else "",
                    "Performing Clinician": a.performing_clinician,
                }
            )
        for d in c.diagnoses:
            dx_rows.append(
                {
                    "Claim ID": c.claim_id,
                    "Diagnosis Code": d.diagnosis_code,
                    "Code System": d.code_system,
                    "Diagnosis Type": d.diagnosis_type,
                    "Sequence": d.sequence,
                    "Description": d.description,
                    "Present On Admission": (
                        "" if d.present_on_admission is None
                        else ("yes" if d.present_on_admission else "no")
                    ),
                }
            )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(claim_rows, columns=[c.name for c in CLAIMS_COLUMNS]).to_excel(
            writer, index=False, sheet_name="Claims"
        )
        pd.DataFrame(act_rows, columns=[c.name for c in ACTIVITIES_COLUMNS]).to_excel(
            writer, index=False, sheet_name="Activities"
        )
        pd.DataFrame(dx_rows, columns=[c.name for c in DIAGNOSES_COLUMNS]).to_excel(
            writer, index=False, sheet_name="Diagnoses"
        )
    buf.seek(0)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Parsing and validation
# --------------------------------------------------------------------------


@dataclass
class IngestReport:
    claims: list[Claim]
    errors: list[str]
    warnings: list[str]
    info: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors and bool(self.claims)


def _s(v: Any, default: str = "") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    s = str(v).strip()
    if s.lower() in ("nan", "nat", "none"):
        return default
    return s


def _n(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        if isinstance(v, str):
            v = v.replace(",", "").replace("AED", "").strip()
            if not v:
                return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _d(v: Any) -> str:
    """Normalise anything date-like to YYYY-MM-DD; leave junk as-is for the validator."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, (pd.Timestamp,)):
        return v.date().isoformat()
    s = str(v).strip()
    if not s or s.lower() in ("nan", "nat", "none"):
        return ""
    try:
        return pd.to_datetime(s, dayfirst=False).date().isoformat()
    except (ValueError, TypeError):
        try:
            return pd.to_datetime(s, dayfirst=True).date().isoformat()
        except (ValueError, TypeError):
            return s


def _split(v: Any) -> list[str]:
    s = _s(v)
    if not s:
        return []
    sep = ";" if ";" in s else ","
    return [p.strip() for p in s.split(sep) if p.strip()]


def _check_columns(df: pd.DataFrame, cols: list[ColumnSpec], sheet: str) -> list[str]:
    missing = [c.name for c in cols if c.required and c.name not in df.columns]
    if missing:
        return [
            f"Sheet '{sheet}' is missing required column(s): {', '.join(missing)}. "
            "Column names are case-sensitive — download the template and match them exactly."
        ]
    return []


def parse_workbook(file: Any) -> IngestReport:
    """Read an uploaded .xlsx / .csv / .json into Claim objects."""
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    name = getattr(file, "name", "upload")
    lower = name.lower()

    # ---- JSON: the canonical model, straight through ----------------------
    if lower.endswith(".json"):
        try:
            payload = json.load(file)
        except json.JSONDecodeError as exc:
            return IngestReport([], [f"Could not parse JSON: {exc}"], [], [])
        records = payload if isinstance(payload, list) else payload.get("claims", [])
        claims = []
        for rec in records:
            try:
                acts = [Activity(**a) for a in rec.pop("activities", [])]
                dxs = [Diagnosis(**d) for d in rec.pop("diagnoses", [])]
                rec.pop("demo_note", None)
                claims.append(Claim(activities=acts, diagnoses=dxs, **rec))
            except TypeError as exc:
                errors.append(f"Claim {rec.get('claim_id', '?')}: {exc}")
        info.append(f"Read {len(claims)} claim(s) from the canonical JSON model.")
        return IngestReport(claims, errors, warnings, info)

    # ---- CSV: Claims sheet only -------------------------------------------
    if lower.endswith(".csv"):
        try:
            claims_df = pd.read_csv(file, dtype=str, keep_default_na=False)
        except Exception as exc:  # noqa: BLE001
            return IngestReport([], [f"Could not read the CSV: {exc}"], [], [])
        acts_df = pd.DataFrame(columns=[c.name for c in ACTIVITIES_COLUMNS])
        dx_df = pd.DataFrame(columns=[c.name for c in DIAGNOSES_COLUMNS])
        warnings.append(
            "A single CSV carries claim headers only. Without service lines and diagnosis "
            "codes the line-level agents will return insufficient_evidence. Use the "
            "three-sheet workbook for a full audit."
        )
    else:
        # ---- Workbook ------------------------------------------------------
        try:
            book = pd.read_excel(file, sheet_name=None, dtype=object, engine="openpyxl")
        except Exception as exc:  # noqa: BLE001
            return IngestReport([], [f"Could not read the workbook: {exc}"], [], [])

        sheet_map = {k.strip().lower(): v for k, v in book.items()}
        if "claims" not in sheet_map:
            return IngestReport(
                [],
                [
                    "The workbook has no sheet named 'Claims'. Found: "
                    + ", ".join(book.keys())
                    + ". Download the template for the expected structure."
                ],
                [],
                [],
            )
        claims_df = sheet_map["claims"]
        acts_df = sheet_map.get(
            "activities", pd.DataFrame(columns=[c.name for c in ACTIVITIES_COLUMNS])
        )
        dx_df = sheet_map.get(
            "diagnoses", pd.DataFrame(columns=[c.name for c in DIAGNOSES_COLUMNS])
        )
        if "activities" not in sheet_map:
            warnings.append("No 'Activities' sheet found — claims will carry no service lines.")
        if "diagnoses" not in sheet_map:
            warnings.append("No 'Diagnoses' sheet found — claims will carry no diagnosis codes.")

    errors += _check_columns(claims_df, CLAIMS_COLUMNS, "Claims")
    if not acts_df.empty:
        errors += _check_columns(acts_df, ACTIVITIES_COLUMNS, "Activities")
    if not dx_df.empty:
        errors += _check_columns(dx_df, DIAGNOSES_COLUMNS, "Diagnoses")
    if errors:
        return IngestReport([], errors, warnings, info)

    # Drop the template's example row if the user left it in place.
    claims_df = claims_df[claims_df.apply(lambda r: _s(r.get("Claim ID")) != "", axis=1)]

    # ---- Group children by claim ------------------------------------------
    acts_by_claim: dict[str, list[Activity]] = {}
    for _, row in acts_df.iterrows():
        cid = _s(row.get("Claim ID"))
        if not cid:
            continue
        qty = _n(row.get("Quantity"), 1.0)
        price = _n(row.get("Unit Price"))
        gross = _n(row.get("Gross Amount"), round(qty * price, 2))
        dur = row.get("Duration Min")
        acts_by_claim.setdefault(cid, []).append(
            Activity(
                line_ref=_s(row.get("Line Ref")) or f"ACT-{len(acts_by_claim.get(cid, [])) + 1:03d}",
                activity_code=_s(row.get("Activity Code")),
                code_system=_s(row.get("Code System"), "CPT"),
                description=_s(row.get("Description")),
                quantity=qty,
                unit_price=price,
                gross_amount=gross,
                modifiers=_split(row.get("Modifiers")),
                start_date=_d(row.get("Start Date")),
                duration_min=int(_n(dur)) if _s(dur) else None,
                performing_clinician=_s(row.get("Performing Clinician")),
            )
        )

    dx_by_claim: dict[str, list[Diagnosis]] = {}
    for _, row in dx_df.iterrows():
        cid = _s(row.get("Claim ID"))
        if not cid:
            continue
        poa_raw = _s(row.get("Present On Admission")).lower()
        poa = True if poa_raw in ("yes", "y", "true", "1") else (
            False if poa_raw in ("no", "n", "false", "0") else None
        )
        dx_by_claim.setdefault(cid, []).append(
            Diagnosis(
                diagnosis_code=_s(row.get("Diagnosis Code")),
                code_system=_s(row.get("Code System"), "ICD-10-CM"),
                diagnosis_type=_s(row.get("Diagnosis Type"), "secondary").lower(),
                sequence=int(_n(row.get("Sequence"), len(dx_by_claim.get(cid, [])) + 1)),
                description=_s(row.get("Description")),
                present_on_admission=poa,
            )
        )

    # ---- Build claims ------------------------------------------------------
    claims: list[Claim] = []
    seen: set[str] = set()

    for i, row in claims_df.iterrows():
        cid = _s(row.get("Claim ID"))
        rownum = int(i) + 2  # +1 for header, +1 for 1-based
        if cid in seen:
            errors.append(f"Row {rownum}: duplicate Claim ID '{cid}'.")
            continue
        seen.add(cid)

        enc = _s(row.get("Encounter Type"), "outpatient").lower()
        if enc not in ENCOUNTER_TYPES:
            warnings.append(
                f"Claim {cid}: encounter type '{enc}' is not one of "
                f"{', '.join(ENCOUNTER_TYPES)} — treated as outpatient."
            )
            enc = "outpatient"

        gross = _n(row.get("Gross Amount"))
        share = _n(row.get("Patient Share"))
        net = _n(row.get("Net Amount"), round(gross - share, 2))

        for req in ("Submission Date", "Encounter Start", "Policy Start", "Scheme Inception"):
            if not _d(row.get(req)):
                errors.append(f"Row {rownum} (claim {cid}): '{req}' is missing or unreadable.")

        claim = Claim(
            claim_id=cid,
            source_channel=_s(row.get("Source Channel"), "direct"),
            submission_date=_d(row.get("Submission Date")),
            gross_amount=gross,
            patient_share=share,
            net_amount=net,
            encounter_type=enc,
            encounter_start=_d(row.get("Encounter Start")),
            encounter_end=_d(row.get("Encounter End")) or _d(row.get("Encounter Start")),
            facility_name=_s(row.get("Facility Name"), "not stated"),
            facility_licence_id=_s(row.get("Facility Licence ID")),
            facility_type=_s(row.get("Facility Type"), "not stated"),
            network_tier=_s(row.get("Network Tier"), "Gold"),
            emirate=_s(row.get("Emirate"), "not stated"),
            clinician_name=_s(row.get("Clinician Name"), "not stated"),
            clinician_licence_id=_s(row.get("Clinician Licence ID")),
            clinician_specialty=_s(row.get("Clinician Specialty"), "not stated"),
            member_sk=_s(row.get("Member Key"), "unknown"),
            member_age=int(_n(row.get("Member Age"), 0)),
            member_gender=_s(row.get("Member Gender"), "not stated").lower(),
            policy_number=_s(row.get("Policy Number")),
            plan_code=_s(row.get("Plan Code")),
            policy_start=_d(row.get("Policy Start")),
            policy_end=_d(row.get("Policy End")),
            scheme_inception=_d(row.get("Scheme Inception")),
            prior_auth_number=_s(row.get("Prior Auth Number")),
            prior_auth_status=_s(row.get("Prior Auth Status"), "not_obtained").lower(),
            drg_code=_s(row.get("DRG Code")),
            length_of_stay_days=int(_n(row.get("Length Of Stay Days"))),
            place_of_treatment=_s(row.get("Place Of Treatment"), "United Arab Emirates"),
            clinical_notes=_s(row.get("Clinical Notes")),
            attachments=_split(row.get("Attachments")),
            activities=acts_by_claim.get(cid, []),
            diagnoses=dx_by_claim.get(cid, []),
        )
        claims.append(claim)

    # ---- Cross-sheet integrity --------------------------------------------
    orphan_acts = sorted(set(acts_by_claim) - seen)
    orphan_dx = sorted(set(dx_by_claim) - seen)
    if orphan_acts:
        warnings.append(
            f"{len(orphan_acts)} Claim ID(s) on the Activities sheet have no matching row "
            f"on the Claims sheet and were ignored: {', '.join(orphan_acts[:5])}"
            + ("…" if len(orphan_acts) > 5 else "")
        )
    if orphan_dx:
        warnings.append(
            f"{len(orphan_dx)} Claim ID(s) on the Diagnoses sheet have no matching row "
            f"on the Claims sheet and were ignored: {', '.join(orphan_dx[:5])}"
            + ("…" if len(orphan_dx) > 5 else "")
        )

    no_lines = [c.claim_id for c in claims if not c.activities]
    if no_lines:
        warnings.append(
            f"{len(no_lines)} claim(s) carry no service lines. Line-level agents will return "
            f"insufficient_evidence for them: {', '.join(no_lines[:5])}"
            + ("…" if len(no_lines) > 5 else "")
        )
    thin_notes = [c.claim_id for c in claims if len(c.clinical_notes) < 60]
    if thin_notes:
        warnings.append(
            f"{len(thin_notes)} claim(s) have little or no clinical note. Squad C reads that "
            f"field to judge necessity, so those claims will return insufficient_evidence "
            f"rather than findings: {', '.join(thin_notes[:5])}"
            + ("…" if len(thin_notes) > 5 else "")
        )

    if claims:
        info.append(
            f"Read {len(claims)} claim(s), "
            f"{sum(len(c.activities) for c in claims)} service line(s), "
            f"{sum(len(c.diagnoses) for c in claims)} diagnosis code(s)."
        )

    # ---- PHI tripwire ------------------------------------------------------
    phi_hits = _phi_scan(claims_df)
    if phi_hits:
        warnings.append(
            "Possible direct identifiers detected in the upload ("
            + ", ".join(phi_hits)
            + "). The platform de-identifies before any model call, but the canonical "
            "model does not want these fields at all — please remove them at source."
        )

    return IngestReport(claims, errors, warnings, info)


_PHI_COLUMN_HINTS = (
    "patient name", "member name", "full name", "first name", "last name",
    "emirates id", "eid", "passport", "date of birth", "dob", "mobile",
    "phone", "email", "address", "national id",
)


def _phi_scan(df: pd.DataFrame) -> list[str]:
    hits = []
    for col in df.columns:
        c = str(col).strip().lower()
        if any(h in c for h in _PHI_COLUMN_HINTS):
            hits.append(str(col))
    return hits
