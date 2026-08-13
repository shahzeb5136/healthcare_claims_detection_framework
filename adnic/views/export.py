"""Export — findings, decisions and the full audit record."""

from __future__ import annotations

import io
import json
from datetime import datetime

import pandas as pd
import streamlit as st

from .. import theme
from ..schema import dumps

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render() -> None:
    theme.page_header(
        "Export",
        "The audit record, in a form somebody else can use",
        "Every finding carries the agent and version that produced it, the citation it "
        "relied on, the trace identifier, and the human decision recorded against it. "
        "A finding whose provenance cannot be reconstructed is not an audit finding.",
    )

    results = st.session_state.results
    claims = {c.claim_id: c for c in st.session_state.claims}

    if not results:
        st.info("No audit results to export yet.")
        return

    findings_rows = []
    claim_rows = []

    for cid, res in results.items():
        claim = claims.get(cid)
        h3 = res.consolidation.get("H03") or {}
        human = res.consolidation.get("human_disposition") or {}
        risk = res.consolidation.get("risk") or {}

        claim_rows.append(
            {
                "Claim ID": cid,
                "Facility": claim.facility_name if claim else "",
                "Specialty": claim.clinician_specialty if claim else "",
                "Setting": claim.encounter_type if claim else "",
                "Gross (AED)": claim.gross_amount if claim else None,
                "Net claimed (AED)": claim.net_amount if claim else None,
                "Risk score": risk.get("score"),
                "Risk band": risk.get("band"),
                "Agent results": len(res.findings),
                "Findings raised": len(res.open_findings()),
                "Findings accepted": len(
                    [f for f in res.open_findings() if f.human_decision in ("accepted", "amended")]
                ),
                "Findings rejected": len(
                    [f for f in res.open_findings() if f.human_decision == "rejected"]
                ),
                "Findings pending": len(
                    [f for f in res.open_findings() if f.human_decision == "pending"]
                ),
                "Max severity": res.max_severity or "",
                "Exposure (AED)": res.total_exposure,
                "H03 recommendation": h3.get("disposition", ""),
                "H03 settlement (AED)": h3.get("recommended_settlement_aed"),
                "Human disposition": human.get("disposition", ""),
                "Human settlement (AED)": human.get("settlement_aed"),
                "Authority": human.get("authority", ""),
                "Decided by": human.get("decided_by", ""),
                "Decided at": human.get("decided_ts", ""),
                "Review complete": res.review_complete,
            }
        )

        for f in res.findings:
            grounded = [c for c in f.citations if c.grounded]
            findings_rows.append(
                {
                    "Claim ID": cid,
                    "Agent ID": f.agent_id,
                    "Agent": f.agent_name,
                    "Agent version": f.agent_version,
                    "Squad": f.squad,
                    "Tier": f.tier,
                    "Knowledge mode": f.knowledge_mode,
                    "Result": f.result,
                    "Severity": f.severity,
                    "Confidence": round(f.confidence, 3),
                    "Exposure (AED)": f.exposure_aed,
                    "Line ref": f.line_ref,
                    "Statement": f.statement,
                    "Rationale": f.rationale,
                    "Recommended action": f.recommended_action,
                    "PACS domain": f.pacs_domain,
                    "Citations": " | ".join(
                        f"{c.locator or '—'} ({c.source_name}"
                        f"{'' if c.grounded else ', UNVERIFIED'})"
                        for c in f.citations
                    ),
                    "Grounded citations": len(grounded),
                    "Evidence": " | ".join(f.evidence_refs),
                    "Human decision": f.human_decision,
                    "Amended exposure (AED)": f.amended_exposure_aed,
                    "Effective exposure (AED)": f.effective_exposure,
                    "Reviewer note": f.reviewer_note,
                    "Decided by": f.decided_by,
                    "Decided at": f.decided_ts,
                    "Model": f.model_ref,
                    "Trace ID": f.trace_id,
                    "Latency (ms)": f.latency_ms,
                    "Input tokens": f.input_tokens,
                    "Output tokens": f.output_tokens,
                }
            )

    claims_df = pd.DataFrame(claim_rows)
    findings_df = pd.DataFrame(findings_rows)

    theme.tiles(
        [
            ("Claims", str(len(claims_df)), "in the audit record"),
            ("Agent results", str(len(findings_df)), "every call, including abstentions"),
            ("Findings raised", str(int((findings_df["Result"] == "finding").sum())),
             "the reviewable subset"),
            ("Grounded citations", str(int(findings_df["Grounded citations"].sum())),
             "resolved to a real clause"),
            ("Exposure", theme.money_short(float(claims_df["Exposure (AED)"].sum())),
             "after human decisions"),
        ]
    )

    st.markdown("### Claim summary")
    st.dataframe(claims_df, use_container_width=True, hide_index=True)

    st.markdown("### Findings register")
    st.dataframe(findings_df, use_container_width=True, hide_index=True, height=420)

    st.markdown("### Download")
    stamp = datetime.now().strftime("%Y%m%d-%H%M")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        claims_df.to_excel(writer, index=False, sheet_name="Claim summary")
        findings_df.to_excel(writer, index=False, sheet_name="Findings register")
    buf.seek(0)

    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button(
            "Audit record (.xlsx)",
            data=buf.getvalue(),
            file_name=f"ADNIC_audit_record_{stamp}.xlsx",
            mime=XLSX_MIME,
            use_container_width=True,
        )
    with d2:
        st.download_button(
            "Findings register (.csv)",
            data=findings_df.to_csv(index=False).encode("utf-8"),
            file_name=f"ADNIC_findings_{stamp}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with d3:
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "platform": "ADNIC Agentic Medical Claims Audit — demonstrator",
            "provider": st.session_state.llm.provider,
            "model": st.session_state.llm.model,
            "claims": [
                {
                    "claim_id": cid,
                    "consolidation": {
                        k: v for k, v in res.consolidation.items() if not k.startswith("_")
                    },
                    "findings": [f.to_dict() for f in res.findings],
                }
                for cid, res in results.items()
            ],
        }
        st.download_button(
            "Full record (.json)",
            data=dumps(payload).encode("utf-8"),
            file_name=f"ADNIC_audit_record_{stamp}.json",
            mime="application/json",
            use_container_width=True,
        )

    st.caption(
        "The JSON export carries the complete agent output contract per finding — result, "
        "severity, calibrated confidence, exposure, statement, rationale, citations with "
        "their grounding status, evidence references, recommended action, PACS domain, "
        "model reference, trace identifier and the human decision. That is what makes a "
        "finding defensible six months later when a provider challenges it."
    )

    with st.expander("Preview the JSON for one claim", expanded=False):
        cid = st.selectbox("Claim", list(results), key="export_json_pick")
        res = results[cid]
        st.code(
            dumps(
                {
                    "claim_id": cid,
                    "consolidation": {
                        k: v for k, v in res.consolidation.items() if not k.startswith("_")
                    },
                    "findings": [f.to_dict() for f in res.findings[:4]],
                }
            ),
            language="json",
        )
        st.caption("First four findings shown. The download contains all of them.")
