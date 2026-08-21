"""
Fleet orchestration.

Execution order for one claim:

    Tier 0   deterministic checks (in-process, free, always)
      |
    risk gate  decides whether the claim earns full agentic review
      |
    Squads B / C / E   one call per agent, run concurrently
      |
    Squad H            synthesis over whatever the audit squads returned

Every agent returns the same JSON contract (Table 13 / Appendix C). A response
that will not parse, or that violates the contract, is recorded as an agent
error — it is never silently dropped and never shown to the auditor as a finding.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from . import deterministic as det
from .catalogue import AUDIT_SQUADS, AgentSpec
from .llm import LLMConfig, complete, extract_json
from .retrieval import PolicyCorpus, format_passages
from .schema import (
    ACTIONS,
    PACS_DOMAINS,
    RESULTS,
    SEVERITIES,
    SEVERITY_RANK,
    Citation,
    Claim,
    ClaimResult,
    Finding,
    make_trace_id,
)


# ==========================================================================
# Prompts
# ==========================================================================

_CONTRACT = """You are one agent in a fleet of specialist medical claims audit agents working for
a UAE health insurer. You answer exactly one question about one claim. Other
agents cover everything else — do not stray outside your scope, and do not repeat their work.

CHOOSING result — READ THIS TWICE, IT IS THE FIELD MOST OFTEN GOT WRONG
- "finding" means SOMETHING IS WRONG with this claim on your question. It is an adverse
  conclusion that would justify a deduction, a denial, a request for information or a
  referral. It does not mean "I reached a conclusion" and it does not mean "I have an
  observation".
- "no_finding" means YOU CHECKED AND THE CLAIM IS CORRECT on your question. This is the
  right answer for a well-coded, well-documented, properly covered claim, and it is
  expected to be the most common answer across a real book of claims. If your statement
  would read "this is appropriate", "this is covered", "this is supported" or "this is
  consistent", the result is no_finding — not finding. A clean claim must come back clean:
  a false positive costs an auditor's minute and costs the insurer a provider relationship.
- "insufficient_evidence" means the material in front of you does not settle the question.
  Say exactly which document or data item you would need. Do not guess and do not default
  to this when the claim as presented already answers the question.
- "not_applicable" means your check has nothing to bite on here — no modifiers for the
  modifier agent, no medicines for the pharmacy agent, no surgery for the surgical agent.
  Return it immediately rather than stretching to produce something.

HOW TO WRITE IT
Write for a professional reader — a medical auditor or a clinician who will have to defend
or overturn your conclusion. Be specific: name codes, line references, dates and amounts.
Never write "may be inappropriate" where you can write which line, why, and by how much.

HOW TO QUANTIFY
- exposure_aed is the money at risk if your finding is upheld, in AED. Not the whole claim
  value unless the whole claim is at risk. For a level-of-service downgrade it is the
  difference between the two levels; for an unbundled line it is that line; for a
  non-financial finding it is 0.
- Write exposure_aed as a plain JSON number in whole AED: 3200 or 3200.00. Never use a
  thousands separator, never abbreviate to thousands, never wrap it in quotes, never write
  a currency symbol. If the line at risk is AED 3,200.00 then the value is 3200.00 — a
  value of 3.2 or 3.00 for that line is wrong by three orders of magnitude and will produce
  a wrong settlement.
- confidence is your calibrated belief that a competent human auditor would uphold this
  finding, from 0.0 to 1.0. A confidence above 0.9 means you would be surprised to be
  overturned.

OUTPUT
Return one JSON object and nothing else — no preamble, no markdown fence, no commentary
before or after. Do not include internal or system XML tags in your response.

{
  "result": "finding | no_finding | insufficient_evidence | not_applicable",
  "severity": "critical | major | moderate | minor",
  "confidence": 0.0,
  "exposure_aed": 0.0,
  "line_ref": "the specific service line this attaches to, or \\"\\" for the whole claim",
  "statement": "the finding in one or two sentences",
  "rationale": "your reasoning, referencing the specific evidence you relied on",
  "citations": [
    {"source": "the rule or source you relied on",
     "locator": "the clause, section or guideline reference",
     "quote": "the operative words of the rule, if you have them"}
  ],
  "evidence_refs": ["activity ACT-002", "diagnosis M17.11", "attachment: operative note"],
  "recommended_action": "accept | deduct | deny | request_information | refer_clinical | refer_siu | monitor"
}

Set severity no higher than %(max_sev)s — that is this agent's ceiling.
When result is not "finding", set severity to "minor", exposure_aed to 0, confidence to
your certainty in that conclusion, and leave citations empty unless one is genuinely relevant."""

_SELF_CHECK = """Before you return, check three things:
1. Does your statement describe something WRONG with the claim? If not, result must be
   no_finding, not_applicable or insufficient_evidence — not "finding".
2. Is exposure_aed the right order of magnitude against the line amounts printed on the
   claim, as a plain number?
3. Is every assertion in your rationale supported by something actually in the claim, the
   clinical record or a cited rule — rather than by an assumption you made?"""

_KNOWLEDGE_MEMORY = """KNOWLEDGE SOURCE — IMPORTANT
No licensed code set or regulator's manual is loaded for this agent, so you are reasoning
from your own knowledge of ICD-10, CPT/HCPCS and clinical practice rather than from a
retrieved passage.

Because of that: state the rule you are relying on and where it comes from, but do not
invent a clause number, a page reference or a version you are not sure of. If you cannot
name the source with confidence, say "general coding practice" rather than fabricating a
citation. Every citation you produce here will be shown to the auditor marked UNVERIFIED."""

_KNOWLEDGE_RAG = """KNOWLEDGE SOURCE — RETRIEVED POLICY CLAUSES
The clauses below were retrieved from the member's actual policy wording. They are the
authority for your conclusion.

Rules:
- Rely only on these clauses. Do not import benefit rules from memory or from other insurers.
- Cite the clause locator exactly as printed (for example "§6.1" or "§4.2") in the
  "locator" field, and put the operative words in "quote".
- If the retrieved clauses do not settle the question, return insufficient_evidence and name
  the clause or schedule you would need. Do not extrapolate.

RETRIEVED CLAUSES FROM %(source)s (version %(version)s, effective %(effective)s)
%(passages)s"""

_SYNTHESIS_CONTRACT = """You are a synthesis agent in the insurer's medical claims audit fleet. The audit squads have
finished. You do not re-audit the claim and you do not invent new findings — you work only
from what the agents returned.

Return one JSON object and nothing else — no preamble, no markdown fence. Do not include
internal or system XML tags in your response.

%(schema)s"""

_H_SCHEMAS = {
    "H01": """{
  "consolidated_defects": [
    {"defect": "one plain-language description of the underlying defect",
     "severity": "critical | major | moderate | minor",
     "line_refs": ["ACT-002"],
     "contributing_agents": ["B08", "B07"],
     "exposure_aed": 0.0}
  ],
  "total_exposure_aed": 0.0,
  "duplicates_merged": 0,
  "summary": "two or three sentences on what is wrong with this claim overall"
}""",
    "H02": """{
  "conflicts": [
    {"question": "what the agents disagree about",
     "position_a": "agent id and what it concluded",
     "position_b": "agent id and what it concluded",
     "better_supported": "the agent id whose position is better supported, or \\"unresolved\\"",
     "why": "why, in terms of evidence quality and source authority",
     "what_would_settle_it": "the specific document or data item"}
  ],
  "summary": "one or two sentences; say plainly if the agents do not materially disagree"
}""",
    "H03": """{
  "disposition": "approve | partial_approve | deny | refer_clinical | refer_siu | request_information",
  "gross_billed_aed": 0.0,
  "deductions": [
    {"line_ref": "ACT-002", "amount_aed": 0.0, "reason": "short reason", "agent_id": "B08"}
  ],
  "total_deduction_aed": 0.0,
  "recommended_settlement_aed": 0.0,
  "denial_code": "a short internal denial code, or \\"\\" if nothing is denied",
  "authority_required": "auditor | audit manager | medical director | SIU referral",
  "rationale": "why this disposition follows from the findings, with the arithmetic shown"
}""",
    "H04": """{
  "internal_rationale": "the audit rationale for the permanent record — professional, complete, defensible on challenge",
  "provider_letter_en": "provider-facing explanation in English: the finding, the rule relied on, the evidence. No internal risk scoring, no agent names, no confidence values.",
  "provider_letter_ar": "the same provider-facing explanation in Arabic",
  "tone_check": "one sentence confirming no internal scoring or agent identifiers leaked into the provider-facing text"
}""",
}


def build_audit_prompt(
    agent: AgentSpec, claim: Claim, corpus: PolicyCorpus | None
) -> tuple[str, str, list[Citation]]:
    """Returns (system_prompt, user_prompt, grounded_citation_stubs)."""
    parts = [
        f"AGENT {agent.agent_id} — {agent.name}",
        f"SQUAD {agent.squad} — {agent.squad_name}",
        f"YOUR QUESTION: {agent.scope}",
        "",
        agent.instruction,
        "",
        _CONTRACT % {"max_sev": agent.max_severity},
    ]

    grounded: list[Citation] = []

    if agent.knowledge_mode == "rag_policy" and corpus is not None:
        hits = corpus.retrieve_for_agent(
            claim.to_agent_context(include_notes=False), agent.retrieval_hint, top_k=8
        )
        grounded = [
            Citation(
                source_id=h.chunk.source_id,
                source_name=h.chunk.source_name,
                version=h.chunk.version,
                locator=h.chunk.locator,
                passage=h.chunk.text.strip(),
                grounded=True,
            )
            for h in hits
        ]
        parts += [
            "",
            _KNOWLEDGE_RAG
            % {
                "source": corpus.source_name,
                "version": corpus.version,
                "effective": corpus.effective_from,
                "passages": format_passages(hits),
            },
        ]
    else:
        parts += ["", _KNOWLEDGE_MEMORY]

    parts += ["", _SELF_CHECK]

    user = (
        "Audit the following claim. It has been de-identified: the member is a "
        "surrogate key with an age band, and no direct identifiers are present.\n\n"
        + claim.to_agent_context()
        + "\n\nAnswer only your question. Return the JSON object."
    )
    return "\n".join(parts), user, grounded


def build_synthesis_prompt(
    agent: AgentSpec, claim: Claim, findings: list[Finding]
) -> tuple[str, str]:
    system = "\n".join(
        [
            f"AGENT {agent.agent_id} — {agent.name}",
            f"SQUAD {agent.squad} — {agent.squad_name}",
            f"YOUR QUESTION: {agent.scope}",
            "",
            agent.instruction,
            "",
            _SYNTHESIS_CONTRACT % {"schema": _H_SCHEMAS[agent.agent_id]},
        ]
    )

    payload = []
    for f in findings:
        payload.append(
            {
                "agent_id": f.agent_id,
                "agent_name": f.agent_name,
                "squad": f.squad,
                "result": f.result,
                "severity": f.severity,
                "confidence": round(f.confidence, 2),
                "exposure_aed": f.exposure_aed,
                "line_ref": f.line_ref,
                "statement": f.statement,
                "rationale": f.rationale,
                "recommended_action": f.recommended_action,
                "citations": [
                    {"source": c.source_name, "locator": c.locator, "grounded": c.grounded}
                    for c in f.citations
                ],
            }
        )

    user = (
        "CLAIM UNDER REVIEW\n"
        + claim.to_agent_context(include_notes=False)
        + "\n\nFINDINGS RAISED BY THE AUDIT SQUADS AND THE DETERMINISTIC CHECKS\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + "\n\nReturn the JSON object."
    )
    return system, user


# ==========================================================================
# Response -> Finding
# ==========================================================================


def _clamp_severity(value: str, ceiling: str) -> str:
    v = (value or "minor").strip().lower()
    if v not in SEVERITIES:
        v = "minor"
    if SEVERITY_RANK.get(v, 1) > SEVERITY_RANK.get(ceiling, 4):
        return ceiling
    return v


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if isinstance(v, str):
            v = v.replace(",", "").replace("AED", "").strip()
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_finding(
    agent: AgentSpec,
    claim: Claim,
    raw: dict[str, Any],
    grounded: list[Citation],
    latency_ms: int,
    in_tok: int,
    out_tok: int,
    model_ref: str,
) -> Finding:
    result = str(raw.get("result", "")).strip().lower()
    if result not in RESULTS:
        result = "error"

    severity = _clamp_severity(str(raw.get("severity", "minor")), agent.max_severity)
    confidence = max(0.0, min(1.0, _to_float(raw.get("confidence"), 0.5)))
    exposure = max(0.0, _to_float(raw.get("exposure_aed"), 0.0))

    # An agent cannot put more at risk than the claim billed. This is an invariant of
    # the domain, not a guess, so it is enforced here rather than asked for in the prompt.
    exposure = min(exposure, claim.gross_amount)

    if result != "finding":
        severity, exposure = "minor", 0.0

    action = str(raw.get("recommended_action", "monitor")).strip().lower()
    if action not in ACTIONS:
        action = "monitor" if result == "finding" else "accept"

    # Citations. For RAG agents the model returns a locator; we resolve it back to
    # the retrieved passage so the auditor sees the real clause text, not the
    # model's paraphrase of it. A locator that does not resolve is not grounded.
    by_locator = {c.locator: c for c in grounded}
    cites: list[Citation] = []
    for c in raw.get("citations") or []:
        if not isinstance(c, dict):
            continue
        locator = str(c.get("locator", "")).strip()
        resolved = by_locator.get(locator)
        if resolved is not None:
            cites.append(
                Citation(
                    source_id=resolved.source_id,
                    source_name=resolved.source_name,
                    version=resolved.version,
                    locator=resolved.locator,
                    passage=resolved.passage,
                    grounded=True,
                )
            )
        else:
            cites.append(
                Citation(
                    source_id="MODEL-MEMORY",
                    source_name=str(c.get("source", "unstated source")),
                    version="unverified",
                    locator=locator,
                    passage=str(c.get("quote", "")),
                    grounded=False,
                )
            )

    evidence = [str(e) for e in (raw.get("evidence_refs") or []) if e]

    return Finding(
        agent_id=agent.agent_id,
        agent_name=agent.name,
        agent_version=agent.version,
        squad=agent.squad,
        claim_id=claim.claim_id,
        result=result,
        severity=severity,
        confidence=confidence,
        exposure_aed=round(exposure, 2),
        statement=str(raw.get("statement", "")).strip(),
        rationale=str(raw.get("rationale", "")).strip(),
        line_ref=str(raw.get("line_ref", "")).strip(),
        citations=cites,
        evidence_refs=evidence,
        recommended_action=action,
        pacs_domain=agent.pacs_domain if agent.pacs_domain in PACS_DOMAINS else "none",
        model_ref=model_ref,
        trace_id=make_trace_id(claim.claim_id, agent.agent_id),
        tier=agent.tier,
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        knowledge_mode=agent.knowledge_mode,
    )


def error_finding(
    agent: AgentSpec, claim: Claim, message: str, latency_ms: int = 0
) -> Finding:
    return Finding(
        agent_id=agent.agent_id,
        agent_name=agent.name,
        agent_version=agent.version,
        squad=agent.squad,
        claim_id=claim.claim_id,
        result="error",
        severity="minor",
        confidence=0.0,
        exposure_aed=0.0,
        statement="Agent did not return a usable result.",
        rationale=message,
        recommended_action="monitor",
        pacs_domain="none",
        model_ref="n/a",
        trace_id=make_trace_id(claim.claim_id, agent.agent_id),
        tier=agent.tier,
        latency_ms=latency_ms,
        knowledge_mode=agent.knowledge_mode,
    )


# ==========================================================================
# Runner
# ==========================================================================


@dataclass
class RunOptions:
    use_risk_gate: bool = False
    gate_threshold: int = 30          # risk score at or above which agents run
    sample_rate_low_risk: float = 0.2  # I06's sampling quota, in miniature
    run_synthesis: bool = True
    concurrency: int = 6


@dataclass
class RunStats:
    calls: int = 0
    errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    wall_ms: int = 0
    gated_out: int = 0
    sampled_in: int = 0


ProgressFn = Callable[[int, int, str], None]


def _agent_task(
    agent: AgentSpec,
    claim: Claim,
    client: Any,
    cfg: LLMConfig,
    corpus: PolicyCorpus | None,
) -> Finding:
    system, user, grounded = build_audit_prompt(agent, claim, corpus)
    resp = complete(client, cfg, system, user)
    if not resp.ok:
        return error_finding(agent, claim, resp.error, resp.latency_ms)

    raw = extract_json(resp.text)
    if raw is None:
        return error_finding(
            agent,
            claim,
            "Response did not contain a parseable JSON object. First 300 characters: "
            + resp.text[:300],
            resp.latency_ms,
        )

    return parse_finding(
        agent,
        claim,
        raw,
        grounded,
        resp.latency_ms,
        resp.input_tokens,
        resp.output_tokens,
        f"{cfg.provider}/{cfg.model}",
    )


def _synthesis_task(
    agent: AgentSpec,
    claim: Claim,
    findings: list[Finding],
    client: Any,
    cfg: LLMConfig,
) -> tuple[str, dict[str, Any]]:
    system, user = build_synthesis_prompt(agent, claim, findings)
    resp = complete(client, cfg, system, user, max_tokens=max(cfg.max_tokens, 4000))
    if not resp.ok:
        return agent.agent_id, {"error": resp.error}
    raw = extract_json(resp.text)
    if raw is None:
        return agent.agent_id, {
            "error": "Response did not contain a parseable JSON object.",
            "raw": resp.text[:600],
        }
    raw["_usage"] = {
        "input_tokens": resp.input_tokens,
        "output_tokens": resp.output_tokens,
        "latency_ms": resp.latency_ms,
    }
    return agent.agent_id, raw


def run_book(
    claims: list[Claim],
    fleet: list[AgentSpec],
    client: Any,
    cfg: LLMConfig,
    corpus: PolicyCorpus | None,
    options: RunOptions,
    progress: ProgressFn | None = None,
) -> tuple[dict[str, ClaimResult], RunStats]:
    """Run the fleet over a book of claims. Returns results keyed by claim id."""
    started = datetime.now()
    stats = RunStats()
    results: dict[str, ClaimResult] = {}

    audit_agents = [
        a for a in fleet if a.enabled and a.squad in AUDIT_SQUADS
    ]
    synth_agents = [
        a for a in fleet if a.enabled and a.squad == "H"
    ]
    synth_agents.sort(key=lambda a: a.agent_id)

    # ---- Tier 0 and the risk gate -----------------------------------------
    schedule: list[tuple[Claim, AgentSpec]] = []
    for idx, claim in enumerate(claims):
        res = ClaimResult(claim_id=claim.claim_id, started_at=started.isoformat())
        t0 = det.run_tier0(claim)
        res.findings.extend(t0)
        score, reasons = det.risk_score(claim, t0)
        res.consolidation["risk"] = {
            "score": score,
            "band": det.risk_band(score),
            "reasons": reasons,
            "gated": False,
            "sampled": False,
        }
        results[claim.claim_id] = res

        run_agents = True
        if options.use_risk_gate and score < options.gate_threshold:
            # Sampling quota: a triage design that only ever examines what it
            # already thinks is risky cannot detect the risk it has learned to
            # ignore. Deterministic sample so a run is reproducible.
            sampled = (idx % max(1, int(round(1 / max(options.sample_rate_low_risk, 0.01))))) == 0
            run_agents = sampled
            res.consolidation["risk"]["gated"] = not sampled
            res.consolidation["risk"]["sampled"] = sampled
            if sampled:
                stats.sampled_in += 1
            else:
                stats.gated_out += 1

        if run_agents:
            schedule.extend((claim, a) for a in audit_agents)

    total = len(schedule) + (len(claims) * len(synth_agents) if options.run_synthesis else 0)
    done = 0

    def tick(label: str) -> None:
        nonlocal done
        done += 1
        if progress:
            progress(done, total, label)

    # ---- Audit squads, concurrently ---------------------------------------
    if schedule:
        with ThreadPoolExecutor(max_workers=max(1, options.concurrency)) as pool:
            futures = {
                pool.submit(_agent_task, agent, claim, client, cfg, corpus): (claim, agent)
                for claim, agent in schedule
            }
            for fut in as_completed(futures):
                claim, agent = futures[fut]
                try:
                    finding = fut.result()
                except Exception as exc:  # noqa: BLE001
                    finding = error_finding(agent, claim, f"Unhandled: {exc}")
                results[claim.claim_id].findings.append(finding)
                stats.calls += 1
                stats.input_tokens += finding.input_tokens
                stats.output_tokens += finding.output_tokens
                if finding.result == "error":
                    stats.errors += 1
                tick(f"{claim.claim_id} · {agent.agent_id} {agent.name}")

    # ---- Synthesis, per claim ---------------------------------------------
    if options.run_synthesis and synth_agents:
        with ThreadPoolExecutor(max_workers=max(1, options.concurrency)) as pool:
            futures = {}
            for claim in claims:
                res = results[claim.claim_id]
                material = [f for f in res.findings if f.result in ("finding", "insufficient_evidence")]
                for agent in synth_agents:
                    futures[
                        pool.submit(_synthesis_task, agent, claim, material, client, cfg)
                    ] = (claim, agent)
            for fut in as_completed(futures):
                claim, agent = futures[fut]
                try:
                    agent_id, payload = fut.result()
                except Exception as exc:  # noqa: BLE001
                    agent_id, payload = agent.agent_id, {"error": f"Unhandled: {exc}"}
                results[claim.claim_id].consolidation[agent_id] = payload
                stats.calls += 1
                usage = payload.get("_usage") or {}
                stats.input_tokens += usage.get("input_tokens", 0)
                stats.output_tokens += usage.get("output_tokens", 0)
                if "error" in payload:
                    stats.errors += 1
                tick(f"{claim.claim_id} · {agent.agent_id} {agent.name}")

    finished = datetime.now()
    stats.wall_ms = int((finished - started).total_seconds() * 1000)
    for res in results.values():
        res.finished_at = finished.isoformat()

    return results, stats


def run_tier0_only(claims: list[Claim]) -> dict[str, ClaimResult]:
    """Deterministic pass with no model calls — works with no API key."""
    now = datetime.now().isoformat()
    out: dict[str, ClaimResult] = {}
    for claim in claims:
        res = ClaimResult(claim_id=claim.claim_id, started_at=now, finished_at=now)
        t0 = det.run_tier0(claim)
        res.findings.extend(t0)
        score, reasons = det.risk_score(claim, t0)
        res.consolidation["risk"] = {
            "score": score,
            "band": det.risk_band(score),
            "reasons": reasons,
            "gated": False,
            "sampled": False,
        }
        out[claim.claim_id] = res
    return out
