"""Claims — load the sample book, or upload your own in the required format."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import branding, theme
from ..demo_data import build_demo_claims
from ..deterministic import risk_band, risk_score, run_tier0
from ..ingest import (
    SHEETS,
    build_demo_workbook,
    build_template_workbook,
    parse_workbook,
)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render(goto) -> None:
    theme.page_header(
        "Claims",
        "The book under audit",
        "Use the fifteen synthetic sample claims, or upload your own in the format "
        "below. Uploaded claims are held in memory for this browser session only and are "
        "never written to disk.",
    )

    tab_book, tab_upload, tab_format = st.tabs(
        ["Current book", "Upload claims", "Input requirements"]
    )

    # ======================================================================
    with tab_book:
        _render_book(goto)

    # ======================================================================
    with tab_upload:
        _render_upload()

    # ======================================================================
    with tab_format:
        _render_format()


# --------------------------------------------------------------------------


def _render_book(goto) -> None:
    claims = st.session_state.claims
    source = st.session_state.get("claims_source", "demo")

    if not claims:
        st.warning("No claims loaded. Upload a workbook, or restore the sample book.")
        if st.button("Load the sample book"):
            st.session_state.claims = build_demo_claims()
            st.session_state.claims_source = "demo"
            st.session_state.results = {}
            st.rerun()
        return

    gross = sum(c.gross_amount for c in claims)
    lines = sum(len(c.activities) for c in claims)
    inpatient = len([c for c in claims if c.encounter_type in ("inpatient", "daycase")])

    theme.tiles(
        [
            ("Claims", str(len(claims)), "sample book" if source == "demo" else "uploaded"),
            ("Gross billed", theme.money_short(gross), "across the book"),
            ("Service lines", str(lines), "line-level findings attach here"),
            ("Inpatient / day case", str(inpatient), "higher tier by default"),
        ]
    )

    rows = []
    for c in claims:
        t0 = run_tier0(c)
        score, _ = risk_score(c, t0)
        rows.append(
            {
                "Claim ID": c.claim_id,
                "Setting": c.encounter_type,
                "Facility": c.facility_name,
                "Specialty": c.clinician_specialty,
                "Age": c.member_age,
                "Gross (AED)": c.gross_amount,
                "Lines": len(c.activities),
                "Dx": len(c.diagnoses),
                "Pre-auth": c.prior_auth_status.replace("_", " "),
                "Tier 0 hits": len([f for f in t0 if f.is_finding]),
                "Risk": risk_band(score),
                "Score": score,
            }
        )
    df = pd.DataFrame(rows)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Gross (AED)": st.column_config.NumberColumn(format="%.2f"),
            "Score": st.column_config.ProgressColumn(
                "Risk score", min_value=0, max_value=100, format="%d"
            ),
        },
    )

    st.caption(
        "Tier 0 hits and the risk score are computed in-process with no model call — this "
        "table is live before any key is entered."
    )

    st.markdown("### Inspect a claim")
    ids = [c.claim_id for c in claims]
    chosen = st.selectbox("Claim", ids, key="claims_inspect")
    claim = next(c for c in claims if c.claim_id == chosen)

    left, right = st.columns([1, 1])

    with left:
        theme.panel_open("Claim and encounter")
        st.markdown(
            theme.kv_rows(
                [
                    ("Claim", claim.claim_id),
                    ("Channel", claim.source_channel),
                    ("Submitted", claim.submission_date),
                    ("Setting", claim.encounter_type),
                    ("Period", f"{claim.encounter_start} → {claim.encounter_end}"),
                    ("Length of stay", f"{claim.length_of_stay_days} day(s)"),
                    ("Place of treatment", f"{claim.place_of_treatment} ({claim.emirate})"),
                    ("Facility", f"{claim.facility_name} · {claim.facility_type}"),
                    ("Facility licence", claim.facility_licence_id or "not stated"),
                    ("Clinician", f"{claim.clinician_name} · {claim.clinician_specialty}"),
                    ("Network tier", claim.network_tier),
                    ("Billed DRG", claim.drg_code or "n/a"),
                ]
            ),
            unsafe_allow_html=True,
        )
        theme.panel_close()

    with right:
        theme.panel_open("Member, policy and money")
        band_lo = (claim.member_age // 5) * 5
        st.markdown(
            theme.kv_rows(
                [
                    ("Member key", claim.member_sk),
                    ("Age band", f"{band_lo}-{band_lo + 4}" if claim.member_age < 90 else "90+"),
                    ("Gender", claim.member_gender),
                    ("Policy", claim.policy_number),
                    ("Plan", claim.plan_code),
                    ("Policy period", f"{claim.policy_start} → {claim.policy_end}"),
                    ("Scheme inception", claim.scheme_inception),
                    ("Pre-authorisation",
                     claim.prior_auth_status.replace("_", " ")
                     + (f" · {claim.prior_auth_number}" if claim.prior_auth_number else "")),
                    ("Gross billed", theme.money(claim.gross_amount)),
                    ("Member share", theme.money(claim.patient_share)),
                    ("Net claimed", theme.money(claim.net_amount)),
                    ("Sum of lines", theme.money(claim.line_total)),
                ]
            ),
            unsafe_allow_html=True,
        )
        theme.panel_close()

    if claim.diagnoses:
        dx_rows = "".join(
            f"<tr><td class='num'>{d.sequence}</td>"
            f"<td class='mono'>{theme.esc(d.diagnosis_code)}</td>"
            f"<td>{theme.esc(d.code_system)}</td>"
            f"<td>{theme.esc(d.diagnosis_type)}</td>"
            f"<td>{theme.esc(d.description)}</td></tr>"
            for d in sorted(claim.diagnoses, key=lambda x: x.sequence)
        )
        st.markdown(
            f'<div class="ca-panel"><div class="ca-panel-head">Diagnoses</div>'
            f'<div class="ca-panel-body lines"><table><thead><tr>'
            f"<th>Seq</th><th>Code</th><th>System</th><th>Type</th><th>Description</th>"
            f"</tr></thead><tbody>{dx_rows}</tbody></table></div></div>",
            unsafe_allow_html=True,
        )

    if claim.activities:
        act_rows = "".join(
            f"<tr><td class='mono'>{theme.esc(a.line_ref)}</td>"
            f"<td class='mono'>{theme.esc(a.activity_code)}</td>"
            f"<td>{theme.esc(a.code_system)}</td>"
            f"<td>{theme.esc(a.description)}</td>"
            f"<td class='mono'>{theme.esc(', '.join(a.modifiers) or '—')}</td>"
            f"<td class='num'>{a.quantity:g}</td>"
            f"<td class='num'>{a.unit_price:,.2f}</td>"
            f"<td class='num'>{a.gross_amount:,.2f}</td>"
            f"<td>{theme.esc(a.start_date)}</td></tr>"
            for a in claim.activities
        )
        st.markdown(
            f'<div class="ca-panel"><div class="ca-panel-head">Billed activities</div>'
            f'<div class="ca-panel-body lines"><table><thead><tr>'
            f"<th>Line</th><th>Code</th><th>System</th><th>Description</th><th>Mod</th>"
            f"<th>Qty</th><th>Unit</th><th>Amount</th><th>Date</th>"
            f"</tr></thead><tbody>{act_rows}</tbody></table></div></div>",
            unsafe_allow_html=True,
        )

    if claim.clinical_notes:
        with st.expander("Clinical record extract — this is what Squad C reads", expanded=False):
            st.text(claim.clinical_notes)

    if claim.attachments:
        st.caption("Attached: " + " · ".join(claim.attachments))

    if claim.demo_note:
        st.markdown(
            f'<div class="notice"><strong>What this claim was built to exercise.</strong> '
            f"{theme.esc(claim.demo_note)}<br><em>This note is sample metadata. It is "
            f"never included in anything sent to an agent.</em></div>",
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("Run the audit", type="primary", use_container_width=True):
            goto("Run audit")


# --------------------------------------------------------------------------


def _render_upload() -> None:
    st.markdown("### Bring your own claims")
    theme.notice(
        "Read the <strong>Input requirements</strong> tab first, or download the template "
        "below — it has the three sheets, a worked example and a full data dictionary. "
        "Column names are case-sensitive.",
        kind="info",
    )

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Download the blank template (.xlsx)",
            data=build_template_workbook(),
            file_name=branding.export_name("claims_template"),
            mime=XLSX_MIME,
            use_container_width=True,
        )
    with c2:
        st.download_button(
            "Download the sample book (.xlsx)",
            data=build_demo_workbook(build_demo_claims()),
            file_name=branding.export_name("sample_claims"),
            mime=XLSX_MIME,
            use_container_width=True,
            help="The fifteen sample claims exported in the upload format — the "
                 "quickest way to see a correctly filled workbook.",
        )

    uploaded = st.file_uploader(
        "Claims workbook (.xlsx), Claims sheet only (.csv), or canonical model (.json)",
        type=["xlsx", "csv", "json"],
    )

    if uploaded is not None:
        # Streamlit hands back the same file object on every rerun, and the previous
        # parse left the cursor at EOF. Rewind before re-reading.
        try:
            uploaded.seek(0)
        except (AttributeError, OSError):
            pass
        with st.spinner("Reading and validating…"):
            report = parse_workbook(uploaded)
        st.session_state.ingest_report = report

        for msg in report.errors:
            st.error(msg)
        for msg in report.warnings:
            st.warning(msg)
        for msg in report.info:
            st.info(msg)

        if report.ok:
            st.success(
                f"Validated. {len(report.claims)} claim(s) ready to load. Loading replaces "
                "the current book and clears any existing audit results."
            )
            preview = pd.DataFrame(
                [
                    {
                        "Claim ID": c.claim_id,
                        "Setting": c.encounter_type,
                        "Facility": c.facility_name,
                        "Gross (AED)": c.gross_amount,
                        "Lines": len(c.activities),
                        "Dx": len(c.diagnoses),
                        "Notes (chars)": len(c.clinical_notes),
                    }
                    for c in report.claims
                ]
            )
            st.dataframe(preview, use_container_width=True, hide_index=True)

            if st.button("Load these claims", type="primary"):
                st.session_state.claims = report.claims
                st.session_state.claims_source = "upload"
                st.session_state.results = {}
                st.session_state.run_stats = None
                st.session_state.selected_claim = None
                st.success(f"Loaded {len(report.claims)} claim(s).")
                st.rerun()

    st.markdown("---")
    st.markdown("##### Restore the sample book")
    if st.button("Reload the fifteen sample claims"):
        st.session_state.claims = build_demo_claims()
        st.session_state.claims_source = "demo"
        st.session_state.results = {}
        st.session_state.run_stats = None
        st.rerun()


# --------------------------------------------------------------------------


def _render_format() -> None:
    st.markdown("### What the platform needs from you")
    st.markdown(
        "The canonical claim model is nested — a claim has an encounter, service lines and "
        "diagnosis codes — so one flat sheet cannot express it without either repeating the "
        "header on every line or losing the line detail. The upload format is therefore a "
        "**three-sheet Excel workbook** joined on `Claim ID`."
    )

    a, b, c = st.columns(3)
    with a:
        theme.card(
            "Sheet 1 · Claims",
            "<strong>One row per claim.</strong> Header, encounter, facility, clinician, "
            "member surrogate, policy dates and money. This is the only mandatory sheet.",
        )
    with b:
        theme.card(
            "Sheet 2 · Activities",
            "<strong>One row per billed service line.</strong> Keyed by <code>Claim ID</code>. "
            "Findings attach to <code>Line Ref</code>, so line references must be unique "
            "within a claim.",
        )
    with c:
        theme.card(
            "Sheet 3 · Diagnoses",
            "<strong>One row per diagnosis code.</strong> Keyed by <code>Claim ID</code>. "
            "Exactly one row per claim must have <code>Diagnosis Type = principal</code>.",
        )

    theme.notice(
        "<strong>Do not upload direct identifiers.</strong> The canonical model has no field "
        "for a patient name, an Emirates ID, a passport number, a date of birth, a phone "
        "number or an address, because the platform does not need them and will not send "
        "them across a model boundary. Supply a surrogate member key and an age in years — "
        "the application derives a five-year age band from it and discards the rest. Columns "
        "whose names look like direct identifiers are flagged on upload."
    )

    st.markdown("#### Two fields do most of the work")
    d1, d2 = st.columns(2)
    with d1:
        theme.card(
            "Clinical Notes",
            "Squad C reads this field to judge medical necessity, guideline concordance, "
            "length of stay, indication and dosing. A one-line note produces "
            "<code>insufficient_evidence</code>, not a finding — which is the correct "
            "behaviour, but it tells you nothing about the claim. Paste the real clinical "
            "record extract.",
        )
    with d2:
        theme.card(
            "Scheme Inception",
            "Every waiting-period calculation runs from this date, not from "
            "<code>Policy Start</code>. If a member joined an existing scheme part-way "
            "through the policy year, this is their individual inception date. Getting it "
            "wrong makes Squad E confidently wrong.",
        )

    st.markdown("#### Column reference")
    for sheet_name, cols in SHEETS.items():
        with st.expander(
            f"Sheet: {sheet_name}  ·  "
            f"{len([c for c in cols if c.required])} required, "
            f"{len([c for c in cols if not c.required])} optional",
            expanded=(sheet_name == "Claims"),
        ):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Column": col.name,
                            "Required": "Required" if col.required else "Optional",
                            "Type": col.kind,
                            "Allowed values": ", ".join(col.allowed) if col.allowed else "",
                            "Description": col.description,
                            "Example": col.example,
                        }
                        for col in cols
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("#### Other accepted formats")
    st.markdown(
        "- **`.csv`** — treated as the Claims sheet alone. Quick to try, but with no service "
        "lines and no diagnosis codes the line-level agents will correctly return "
        "`insufficient_evidence`.\n"
        "- **`.json`** — the canonical model directly, as a list of claim objects or "
        "`{\"claims\": [...]}`. Each claim may carry nested `activities` and `diagnoses` "
        "arrays. This is the shape to emit from an upstream claims pipeline."
    )

    st.markdown("#### Validation performed on upload")
    st.markdown(
        "- Required columns present on every sheet, with exact names\n"
        "- `Claim ID` unique on the Claims sheet, and resolvable from the child sheets\n"
        "- Dates parseable, and the four date fields the audit depends on present\n"
        "- Encounter type within the controlled vocabulary\n"
        "- Orphaned Activities and Diagnoses rows reported rather than silently dropped\n"
        "- Claims with no service lines, or with a thin clinical note, flagged so you know "
        "why those agents will abstain\n"
        "- Column names resembling direct identifiers flagged"
    )

    st.download_button(
        "Download the blank template (.xlsx)",
        data=build_template_workbook(),
        file_name=branding.export_name("claims_template"),
        mime=XLSX_MIME,
        key="format_tab_template",
    )
