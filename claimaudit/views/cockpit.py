"""Audit cockpit — the prioritised work queue across the whole book."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import theme
from ..schema import SEVERITY_RANK


def render(goto) -> None:
    theme.page_header(
        "Audit cockpit",
        "Where the day starts",
        "One queue across the book, ordered by what actually deserves an auditor's next "
        "minute: severity first, then money, then age. Open a claim to work it in the "
        "review workbench.",
    )

    results = st.session_state.results
    claims = {c.claim_id: c for c in st.session_state.claims}

    if not results:
        st.info(
            "No audit results yet. Run the fleet — or run the deterministic checks alone, "
            "which need no API key."
        )
        if st.button("Go to Run audit", type="primary"):
            goto("Run audit")
        return

    # ------------------------------------------------------------------ rows
    rows = []
    for cid, res in results.items():
        claim = claims.get(cid)
        if claim is None:
            continue
        open_f = [f for f in res.open_findings() if f.human_decision != "rejected"]
        sev = res.max_severity or "—"
        disposition = (res.consolidation.get("H03") or {}).get("disposition", "")
        settlement = (res.consolidation.get("H03") or {}).get("recommended_settlement_aed")
        risk = res.consolidation.get("risk", {})
        errors = len([f for f in res.findings if f.result == "error"])

        rows.append(
            {
                "Claim ID": cid,
                "Specialty": claim.clinician_specialty,
                "Facility": claim.facility_name,
                "Setting": claim.encounter_type,
                "Gross (AED)": claim.gross_amount,
                "Exposure (AED)": res.total_exposure,
                "Exposure %": (
                    round(100 * res.total_exposure / claim.gross_amount, 1)
                    if claim.gross_amount else 0.0
                ),
                "Findings": len(open_f),
                "Max severity": sev,
                "Recommended": (disposition or "—").replace("_", " "),
                "Settlement (AED)": settlement if isinstance(settlement, (int, float)) else None,
                "Reviewed": f"{res.reviewed_count}/{len(res.open_findings())}",
                "Risk": risk.get("band", "—"),
                "Agent errors": errors,
                "_sev_rank": SEVERITY_RANK.get(sev, 0),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        st.info("No results for the claims currently loaded.")
        return

    # -------------------------------------------------------------- headline
    total_gross = df["Gross (AED)"].sum()
    total_exp = df["Exposure (AED)"].sum()
    open_findings = int(df["Findings"].sum())
    clean = int((df["Findings"] == 0).sum())
    critical = int((df["Max severity"] == "critical").sum())

    theme.tiles(
        [
            ("Claims audited", str(len(df)), f"{clean} returned clean"),
            ("Open findings", str(open_findings), "awaiting a human decision"),
            ("Exposure", theme.money_short(total_exp),
             f"{100 * total_exp / total_gross:,.1f}% of gross" if total_gross else ""),
            ("Critical", str(critical), "claims carrying a critical finding"),
            ("Gross under audit", theme.money_short(total_gross), "billed value in scope"),
        ]
    )

    # --------------------------------------------------------------- filters
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        sev_filter = st.multiselect(
            "Severity", ["critical", "major", "moderate", "minor", "—"],
            default=["critical", "major", "moderate", "minor", "—"],
        )
    with f2:
        min_exposure = st.number_input("Minimum exposure (AED)", 0.0, value=0.0, step=500.0)
    with f3:
        setting = st.multiselect(
            "Setting", sorted(df["Setting"].unique()), default=list(df["Setting"].unique())
        )
    with f4:
        order = st.selectbox(
            "Order by", ["Severity, then exposure", "Exposure", "Findings", "Claim ID"]
        )

    view = df[
        df["Max severity"].isin(sev_filter)
        & (df["Exposure (AED)"] >= min_exposure)
        & df["Setting"].isin(setting)
    ].copy()

    if order == "Severity, then exposure":
        view = view.sort_values(["_sev_rank", "Exposure (AED)"], ascending=[False, False])
    elif order == "Exposure":
        view = view.sort_values("Exposure (AED)", ascending=False)
    elif order == "Findings":
        view = view.sort_values("Findings", ascending=False)
    else:
        view = view.sort_values("Claim ID")

    st.dataframe(
        view.drop(columns=["_sev_rank"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Gross (AED)": st.column_config.NumberColumn(format="%.2f"),
            "Exposure (AED)": st.column_config.NumberColumn(format="%.2f"),
            "Settlement (AED)": st.column_config.NumberColumn(format="%.2f"),
            "Exposure %": st.column_config.NumberColumn(format="%.1f%%"),
        },
        height=min(420, 60 + 36 * len(view)),
    )

    # ------------------------------------------------------------------ open
    st.markdown("### Open a claim")
    o1, o2 = st.columns([3, 1])
    with o1:
        pick = st.selectbox(
            "Claim",
            list(view["Claim ID"]),
            format_func=lambda cid: (
                f"{cid} · {view.loc[view['Claim ID'] == cid, 'Findings'].iloc[0]} finding(s) · "
                f"{theme.money(float(view.loc[view['Claim ID'] == cid, 'Exposure (AED)'].iloc[0]))}"
            ),
            key="cockpit_pick",
        )
    with o2:
        st.write("")
        if st.button("Review this claim", type="primary", use_container_width=True):
            st.session_state.selected_claim = pick
            goto("Claim review workbench")

    # --------------------------------------------------------- fleet activity
    st.markdown("### Which agents are doing the work")
    st.caption(
        "Precision per agent is what the assurance layer measures in production. Here it is "
        "raw activity — but a squad that never returns no_finding is a squad worth "
        "interrogating."
    )

    agent_rows: dict[str, dict] = {}
    for res in results.values():
        for f in res.findings:
            k = f.agent_id
            row = agent_rows.setdefault(
                k,
                {
                    "ID": f.agent_id,
                    "Agent": f.agent_name,
                    "Squad": f.squad,
                    "finding": 0,
                    "no_finding": 0,
                    "insufficient_evidence": 0,
                    "not_applicable": 0,
                    "error": 0,
                    "Exposure (AED)": 0.0,
                    "conf_sum": 0.0,
                    "conf_n": 0,
                },
            )
            row[f.result] = row.get(f.result, 0) + 1
            if f.is_finding:
                row["Exposure (AED)"] += f.effective_exposure
                row["conf_sum"] += f.confidence
                row["conf_n"] += 1

    agent_df = pd.DataFrame(
        [
            {
                "ID": r["ID"],
                "Agent": r["Agent"],
                "Squad": r["Squad"],
                "Findings": r["finding"],
                "Clean": r["no_finding"],
                "Insufficient": r["insufficient_evidence"],
                "N/A": r["not_applicable"],
                "Errors": r["error"],
                "Exposure (AED)": round(r["Exposure (AED)"], 2),
                "Mean confidence": round(r["conf_sum"] / r["conf_n"], 2) if r["conf_n"] else None,
            }
            for r in agent_rows.values()
        ]
    ).sort_values(["Squad", "ID"])

    st.dataframe(
        agent_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Exposure (AED)": st.column_config.NumberColumn(format="%.2f"),
            "Mean confidence": st.column_config.NumberColumn(format="%.2f"),
        },
        height=min(520, 60 + 36 * len(agent_df)),
    )
