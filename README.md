# ADNIC — Agentic Medical Claims Audit Platform (demonstrator)

A working demonstrator of the platform described in *ADNIC — Agentic Medical Claims Audit
Platform, Proposal v1.0*. A fleet of specialist agents audits medical claims across coding
integrity, clinical appropriateness and policy adjudication, consolidates the findings into
one reviewable decision, and hands it to a human. Nothing reaches a payment decision without
a person.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Bring your own API key — Anthropic by default, OpenAI or a local Ollama model as
alternatives. Keys are held in memory for the browser session only. The deterministic
checks and the whole UI work with no key at all.

---

## What is built, and what is not

The proposal specifies **62 agents across nine squads**. This demonstrator builds **28** —
the squads that can be shown honestly without ADNIC's licensed code sets, tariff files,
provider contracts or historical claim store.

| | Squad | Agents | Knowledge source here |
|---|---|---|---|
| ✅ | **B** — Coding integrity | 10 | Model memory. Citations shown as **UNVERIFIED**. |
| ✅ | **C** — Clinical appropriateness and medical necessity | 8 | Model memory. Citations shown as **UNVERIFIED**. |
| ✅ | **E** — Policy, benefit and contract adjudication | 6 | **In-app RAG** over a real policy wording. Citations **grounded**. |
| ✅ | **H** — Synthesis, scoring and explanation | 4 | Consumes the audit squads' findings. |
| ✅ | **Tier 0** — deterministic pre-checks | 13 checks | Ordinary Python. No model, no key, no cost. |

Deliberately out of scope, and why:

| Squad | Agents | Why |
|---|---|---|
| **A** — Intake, data quality, eligibility | 6 | Needs the Shafafiya / eClaimLink schema and a live policy administration extract. |
| **D** — Financial and tariff integrity | 8 | Needs the DoH Mandatory Tariff, ADNIC's rate cards and the IR-DRG grouper. Recalculating a price without the price list is theatre. |
| **F** — Fraud, waste and abuse | 8 | Operates across claims, not on one claim. Needs a historical claim store and peer distributions. |
| **G** — Regulatory and standards compliance | 5 | Needs the DoH Claims and Adjudication Rules corpus and denial code lists. |
| **I** — Assurance and oversight | 6 | Needs a golden dataset and live auditor decision history before precision, calibration or drift can be measured rather than asserted. |
| **H05** — Provider Audit Compliance Score | 1 | A provider score computed on a handful of claims is noise, not a score. |

---

## How a claim moves through it

```
Tier 0 (deterministic, every claim, free)
   ↓
Risk gate  ──── low risk ────►  held, plus a sampling quota pulled through anyway
   ↓ earns review
Squads B / C / E  (concurrent, one call per agent, one uniform JSON contract)
   ↓
Squad H  (consolidate → surface disagreement → recommend disposition → draft the letter)
   ↓
A human accepts, amends or rejects every finding. Only then does anything have effect.
```

Every agent returns the same shape — result, severity, calibrated confidence,
exposure in AED, statement, rationale, citations, evidence references, recommended action,
PACS domain, model reference and trace id. That uniformity is what lets 28 heterogeneous
checks be consolidated, scored and exported by common machinery.

---

## The two knowledge modes

**Squads B and C — model memory.** The ICD-10, CPT and HCPCS code sets are licensed
products, so these agents reason from the model's own knowledge of coding and clinical
practice. Anything they cite is displayed to the auditor marked **unverified**, and the
agents are instructed to say "general coding practice" rather than invent a clause number.

**Squad E — grounded retrieval.** One full policy wording
(`knowledge/ADNIC-COMP-GOLD-2026.md`, ~5,000 words, 78 numbered clauses) is chunked on
clause boundaries and indexed with **BM25 in-process**. No external vector database, no
embedding service, no network call for retrieval. Three passes:

1. **Lexical** — the agent's retrieval hint, weighted twice, plus the claim text.
2. **Cross-references** — a retrieved clause that names another (`§1.10`) pulls it in. This
   is what lets the coverage agent find the *definitions* an exclusion depends on.
3. **Section siblings** — clauses qualify each other. A waiting period is meaningless
   without the waiver clause two lines below it.

The agent cites a locator; the application resolves that locator back to the real clause and
shows the auditor **the passage itself**, not the model's paraphrase. A locator that does
not resolve is downgraded to an unverified citation — the model cannot invent a clause
number into existence.

Both passes are load-bearing, not decoration: on the cosmetic-versus-reconstructive claim
the deciding definition arrives by cross-reference, and on the overseas-treatment claim the
deciding clause arrives by section expansion.

---

## Input requirements

The demonstrator ships with **15 synthetic claims**, each built to exercise specific agents,
including one deliberately clean control. To use your own, the canonical claim model is
nested, so the upload format is a **three-sheet Excel workbook** joined on `Claim ID`:

| Sheet | Grain | Notes |
|---|---|---|
| **Claims** | one row per claim | Header, encounter, facility, clinician, member surrogate, policy dates, money. The only mandatory sheet. |
| **Activities** | one row per billed line | Findings attach to `Line Ref`, which must be unique within a claim. |
| **Diagnoses** | one row per code | Exactly one row per claim must be `principal`. |

Also accepted: a single `.csv` (Claims sheet only — line-level agents will correctly abstain),
or `.json` in the canonical model.

Download the blank template, a full data dictionary, and the demonstration book exported in
the upload format from **Claims → Upload claims** in the app. The **Input requirements** tab
documents every column, its type, allowed values and an example.

**Two fields do most of the work.** `Clinical Notes` is what Squad C reads to judge
necessity, length of stay, indication and dosing — a one-line note produces
`insufficient_evidence`, not a finding. `Scheme Inception` is what every waiting-period
calculation runs from, not `Policy Start`.

**Do not upload direct identifiers.** The canonical model has no field for a patient name,
Emirates ID, passport number, date of birth, phone number or address, because the platform
does not need them and will not send them across a model boundary. Supply a surrogate member
key and an age in years; the application derives a five-year age band and discards the rest.
Columns whose names look like direct identifiers are flagged on upload.

---

## Surfaces

| Page | What it is for |
|---|---|
| **Scope and method** | What is built, what is not, and why. |
| **Claims** | The book under audit, a claim inspector, upload, and the full input contract. |
| **Agent fleet** | The catalogue, an Agent Studio for editing scope and instructions, and a **prompt inspector** that shows exactly what any agent is sent for any claim — including the clauses BM25 actually retrieved. |
| **Knowledge base** | A live retrieval tester over the same index the agents use, a clause browser, and the retrieval design. |
| **Run audit** | Scope, cost estimate before you spend anything, the risk gate, concurrency, and a deterministic-only mode that needs no key. |
| **Audit cockpit** | The prioritised queue across the book, plus per-agent activity. |
| **Claim review workbench** | Three panes: claim context, findings with evidence one click away, and the decision panel with live settlement arithmetic. Accept, amend, reject or escalate every finding. |
| **Export** | The findings register and the full audit record as `.xlsx`, `.csv` or `.json`. |

---

## Cost

28 agents × 1 claim ≈ 28 model calls ≈ 75k tokens. Three or four claims show every squad.
The Run page estimates tokens and cost before you commit, and reports actual usage after.
Turn on the risk gate to see the production economics: at a hundred thousand claims a month,
running 62 reasoning agents against every claim would be over six million invocations, which
is why the design triages rather than brute-forces.

---

## Layout

```
app.py                      Streamlit entry, navigation, session state
adnic/
  catalogue.py              the 28 agent specifications
  schema.py                 canonical claim model + the uniform agent output contract
  deterministic.py          Tier 0 checks and the risk gate
  retrieval.py              clause chunking and the three-pass BM25 retriever
  llm.py                    provider adapters, JSON extraction, cost estimation
  orchestrator.py           prompt assembly, concurrent execution, response parsing
  demo_data.py              the 15 demonstration claims
  ingest.py                 upload contract, validation, template generation
  theme.py                  the visual system
  views/                    one module per page
knowledge/
  ADNIC-COMP-GOLD-2026.md   the synthetic policy corpus
legacy_app.py               the original single-file demonstrator, preserved
```

---

## Disclaimers

All claims, members, providers and the policy wording are **synthetic**. The policy wording
is structurally realistic but is not a real insurance contract and must not be relied on for
any adjudication decision.

This is a **decision-support and screening tool**, not a substitute for professional
medical, coding or compliance review. It is a demonstrator, not the production platform:
there is no authentication, no audit log persistence, no de-identification service, no
evaluation harness and no PHI guard. Those are Phase 1 and 2 of the proposal.

MIT — see [LICENSE](LICENSE).
