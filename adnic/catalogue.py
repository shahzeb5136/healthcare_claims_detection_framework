"""
The agent fleet for the demonstrator.

The proposal specifies 62 agents across nine squads. This demonstrator builds
28 of them — the squads that can be shown honestly without ADNIC's licensed
code sets, tariff files, provider contracts or historical claim store:

    Squad B — Coding integrity ................ 10 agents  (knowledge: model memory)
    Squad C — Clinical appropriateness ......... 8 agents  (knowledge: model memory)
    Squad E — Policy, benefit and contract ..... 6 agents  (knowledge: in-app RAG)
    Squad H — Synthesis and explanation ........ 4 agents  (knowledge: upstream findings)

Deliberately out of scope for the demonstrator, and why:

    Squad A — Intake, eligibility ......... needs Shafafiya schema + policy admin extract
    Squad D — Financial and tariff ........ needs the DoH Mandatory Tariff + provider contracts
    Squad F — Fraud, waste and abuse ...... operates across claims; needs a historical store
    Squad G — Regulatory compliance ....... needs the DoH C&A Rules corpus
    Squad I — Assurance and oversight ..... needs a golden dataset and live decision history
    H05    — Provider Audit Compliance Score  needs claim volume to be statistically meaningful

KNOWLEDGE MODES
    model_memory  the agent reasons from the model's own knowledge of ICD-10,
                  CPT/HCPCS and clinical practice. Citations it produces are
                  labelled UNVERIFIED and are shown as such in the workbench.
                  In production these agents retrieve from licensed code sets.
    rag_policy    the agent retrieves clauses from the in-app policy corpus by
                  BM25 and must cite the clause it relied on. Citations are
                  grounded and the retrieved passage is shown to the auditor.
    upstream      the agent consumes the findings of the audit squads.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


FLEET_VERSION = "1.0.0"


@dataclass
class AgentSpec:
    agent_id: str
    name: str
    squad: str
    squad_name: str
    scope: str                 # the one question this agent answers
    instruction: str           # what goes into the system prompt
    knowledge_sources: str     # shown in the UI; production sources per the proposal
    knowledge_mode: str        # model_memory | rag_policy | upstream
    max_severity: str
    pacs_domain: str
    tier: int
    version: str = FLEET_VERSION
    enabled: bool = True
    retrieval_hint: str = ""   # seed terms for the RAG query on policy agents

    def copy(self) -> "AgentSpec":
        return replace(self)


SQUADS = {
    "B": {
        "name": "Coding integrity",
        "blurb": "The core of the medical audit function: is the claim coded to the record?",
        "consumer": "Medical auditor",
        "knowledge": "model_memory",
    },
    "C": {
        "name": "Clinical appropriateness and medical necessity",
        "blurb": "Was the care indicated, proportionate and safe on the evidence recorded?",
        "consumer": "Clinician and Medical Director",
        "knowledge": "model_memory",
    },
    "E": {
        "name": "Policy, benefit and contract adjudication",
        "blurb": "Does the member's policy actually cover this, on its own wording?",
        "consumer": "Medical auditor and claims adjudication",
        "knowledge": "rag_policy",
    },
    "H": {
        "name": "Synthesis, scoring and explanation",
        "blurb": "Consolidates the fleet's output into one reviewable decision.",
        "consumer": "The workbench",
        "knowledge": "upstream",
    },
}


# ==========================================================================
# SQUAD B — Coding integrity (10 agents)
# ==========================================================================

_SQUAD_B: list[AgentSpec] = [
    AgentSpec(
        agent_id="B01",
        name="ICD code validity and currency",
        squad="B",
        squad_name=SQUADS["B"]["name"],
        scope="Is every diagnosis code real, current, billable and specific enough?",
        instruction=(
            "Check every diagnosis code on the claim for: existence in ICD-10-CM or ICD-10-AM; "
            "validity on the date of service; billability (a category or header code billed as if "
            "it were a terminal code is a defect); and specificity (an unspecified code used where "
            "the clinical record documents a specific site, laterality, type or severity is a defect). "
            "Also flag codes that belong to the wrong edition for the encounter.\n"
            "Do NOT comment on procedures, pricing, necessity or benefits — other agents own those."
        ),
        knowledge_sources="ICD-10-CM / ICD-10-AM code sets and conventions; DoH coding manual",
        knowledge_mode="model_memory",
        max_severity="moderate",
        pacs_domain="coding_integrity",
        tier=1,
    ),
    AgentSpec(
        agent_id="B02",
        name="CPT and HCPCS validity and currency",
        squad="B",
        squad_name=SQUADS["B"]["name"],
        scope="Is every procedure, service and supply code real, current and correctly categorised?",
        instruction=(
            "Apply the same validity test to procedure, service and supply codes. Check existence in "
            "CPT or HCPCS Level II, currency on the date of service, whether the code's category "
            "matches the service actually described, and whether an unlisted or 'not otherwise "
            "classified' code has been used where a specific code exists for the described service.\n"
            "Do not evaluate whether the procedure was appropriate or bundled — B03 and B08 own those."
        ),
        knowledge_sources="CPT code set and guidelines; HCPCS Level II; DoH service code list",
        knowledge_mode="model_memory",
        max_severity="moderate",
        pacs_domain="coding_integrity",
        tier=1,
    ),
    AgentSpec(
        agent_id="B03",
        name="Diagnosis to procedure clinical coherence",
        squad="B",
        squad_name=SQUADS["B"]["name"],
        scope="Do the procedures billed plausibly follow from the diagnoses recorded?",
        instruction=(
            "This is the central consistency test. For each billed procedure ask whether at least one "
            "recorded diagnosis supports it, and for each significant diagnosis ask whether the "
            "treatment billed is consistent with it. Flag: procedures with no supporting diagnosis; "
            "diagnoses carrying no corresponding treatment where treatment would be expected; and "
            "combinations that are clinically incongruous.\n"
            "Judge coherence, not necessity — whether the service was *warranted* is C01's question."
        ),
        knowledge_sources="CPT and ICD clinical descriptors; specialty coding guidance",
        knowledge_mode="model_memory",
        max_severity="major",
        pacs_domain="coding_integrity",
        tier=2,
    ),
    AgentSpec(
        agent_id="B04",
        name="Diagnosis sequencing and principal diagnosis",
        squad="B",
        squad_name=SQUADS["B"]["name"],
        scope="Is the principal diagnosis correctly identified and sequenced?",
        instruction=(
            "Assess whether the diagnosis coded as principal is the condition that, after study, was "
            "chiefly responsible for the encounter, and whether the remaining diagnoses are sequenced "
            "consistently with the resources actually consumed. Incorrect sequencing is a common and "
            "material driver of DRG assignment and payment — where the encounter is inpatient or "
            "day case, say explicitly whether re-sequencing would be likely to change the DRG, and "
            "estimate the payment impact.\n"
            "For outpatient encounters with a single diagnosis, return not_applicable."
        ),
        knowledge_sources="ICD official coding and reporting guidelines; IR-DRG grouper logic",
        knowledge_mode="model_memory",
        max_severity="major",
        pacs_domain="coding_integrity",
        tier=2,
    ),
    AgentSpec(
        agent_id="B05",
        name="Laterality, site and anatomical consistency",
        squad="B",
        squad_name=SQUADS["B"]["name"],
        scope="Do laterality and anatomical site agree across diagnosis, procedure, modifier and narrative?",
        instruction=(
            "Cross-check laterality and anatomical site across every element of the claim: the "
            "diagnosis codes, the procedure codes, the laterality modifiers (RT, LT, 50 and the "
            "anatomical modifiers), and the clinical record. Flag a left-side diagnosis with a "
            "right-side procedure, bilateral billing where the record describes a unilateral "
            "intervention, and any site conflict between the operative note and the code.\n"
            "Where the claim contains no laterality-bearing codes, return not_applicable."
        ),
        knowledge_sources="ICD and CPT laterality conventions; modifier definitions",
        knowledge_mode="model_memory",
        max_severity="moderate",
        pacs_domain="coding_integrity",
        tier=1,
    ),
    AgentSpec(
        agent_id="B06",
        name="Age and gender code conflict",
        squad="B",
        squad_name=SQUADS["B"]["name"],
        scope="Is any code impossible or implausible for this member's age band or gender?",
        instruction=(
            "Detect codes that are impossible or highly implausible given the member's recorded age "
            "band and gender — obstetric or gynaecological codes on a male member, prostate codes on "
            "a female member, neonatal or perinatal codes on an adult, paediatric-only procedures on "
            "an elderly member, adult-dose administration on a young child.\n"
            "Distinguish impossible (critical to the claim's validity, severity moderate) from merely "
            "unusual (report as insufficient_evidence rather than manufacturing a finding)."
        ),
        knowledge_sources="ICD and CPT age and gender edits; DoH edit tables",
        knowledge_mode="model_memory",
        max_severity="moderate",
        pacs_domain="coding_integrity",
        tier=1,
    ),
    AgentSpec(
        agent_id="B07",
        name="Modifier appropriateness",
        squad="B",
        squad_name=SQUADS["B"]["name"],
        scope="Is every modifier correctly applied and supported by the documentation?",
        instruction=(
            "Evaluate each modifier on the claim for correct application and documentary support, "
            "with particular attention to the modifiers most often misused: 25 (significant, "
            "separately identifiable E/M on the same day as a procedure), 59 and the X{EPSU} family "
            "(distinct procedural service), 50 (bilateral), 76/77 (repeat procedure), 80/81/82 and AS "
            "(assistant surgeon), 52/53 (reduced or discontinued services), 22 (increased procedural "
            "service).\n"
            "For modifier 25 in particular, state whether the record documents an evaluation that is "
            "genuinely separate from the pre- and post-service work already included in the procedure. "
            "Where the claim carries no modifiers, return not_applicable."
        ),
        knowledge_sources="CPT modifier definitions and guidance; documentation in the attachments",
        knowledge_mode="model_memory",
        max_severity="major",
        pacs_domain="coding_integrity",
        tier=2,
    ),
    AgentSpec(
        agent_id="B08",
        name="Bundling and component billing",
        squad="B",
        squad_name=SQUADS["B"]["name"],
        scope="Was anything billed separately that belongs inside a more comprehensive procedure?",
        instruction=(
            "Identify services billed separately that should have been bundled: components of a more "
            "comprehensive procedure billed as if independent; services falling inside a global "
            "surgical period (0, 10 or 90 days depending on the procedure) that are not separately "
            "reportable; mutually exclusive procedure pairs billed together; and routine supplies, "
            "trays or standard post-operative care billed alongside the parent procedure.\n"
            "Where a global period is at issue, state the parent procedure, its global period, the "
            "date the parent was performed and the date of the disputed line. Quantify the exposure "
            "as the billed amount of the line that should not stand."
        ),
        knowledge_sources="Procedure-to-procedure edit logic; CPT surgical package definition",
        knowledge_mode="model_memory",
        max_severity="major",
        pacs_domain="coding_integrity",
        tier=2,
    ),
    AgentSpec(
        agent_id="B09",
        name="Upcoding and evaluation / management level",
        squad="B",
        squad_name=SQUADS["B"]["name"],
        scope="Is the level of service billed supported by the documented work?",
        instruction=(
            "Assess whether the level of service billed is supported by the documented history, "
            "examination and medical decision-making (or, where applicable, documented total time). "
            "Separately, assess whether the procedure billed is the most comprehensive member of its "
            "code family where the record describes a lesser service.\n"
            "Where you conclude a level is unsupported, name the level you consider supported and "
            "quantify the exposure as the difference between the two, not the whole line."
        ),
        knowledge_sources="E/M documentation guidelines; CPT descriptors; provider peer distributions",
        knowledge_mode="model_memory",
        max_severity="major",
        pacs_domain="coding_integrity",
        tier=2,
    ),
    AgentSpec(
        agent_id="B10",
        name="Dental, optical and ancillary code sets",
        squad="B",
        squad_name=SQUADS["B"]["name"],
        scope="Do dental, optical and ancillary lines pass the same tests under their own code sets?",
        instruction=(
            "Apply validity, coherence and bundling tests to dental and optical lines, which use "
            "different code sets (ADA/CDT-style dental codes, optical benefit item codes) and "
            "different clinical logic, and which are frequently under-audited. Check tooth-number and "
            "surface consistency on restorative work, whether a procedure is included in the fee for "
            "another on the same tooth or the same day, and whether optical items billed match what "
            "the refraction supports.\n"
            "Where the claim contains no dental, optical or ancillary lines, return not_applicable."
        ),
        knowledge_sources="Dental code set (ADA / USC&LS); optical benefit rules",
        knowledge_mode="model_memory",
        max_severity="moderate",
        pacs_domain="coding_integrity",
        tier=1,
    ),
]


# ==========================================================================
# SQUAD C — Clinical appropriateness and medical necessity (8 agents)
# ==========================================================================

_SQUAD_C: list[AgentSpec] = [
    AgentSpec(
        agent_id="C01",
        name="Medical necessity narrative",
        squad="C",
        squad_name=SQUADS["C"]["name"],
        scope="Does the clinical record establish that the service was necessary?",
        instruction=(
            "Assess whether the record establishes necessity: the presenting symptoms, the objective "
            "findings, what was tried before, and a stated indication that connects the two to the "
            "service delivered. Produce a reasoned statement of what is and is not evidenced, written "
            "for a clinician reader who will have to defend or overturn it.\n"
            "Be explicit about the difference between 'the record does not establish necessity' and "
            "'the service was unnecessary'. Where documentation is thin rather than contradictory, "
            "return insufficient_evidence with a precise statement of the document you would need."
        ),
        knowledge_sources="Clinical practice guidelines; DoH medical necessity criteria",
        knowledge_mode="model_memory",
        max_severity="major",
        pacs_domain="clinical_appropriateness",
        tier=2,
    ),
    AgentSpec(
        agent_id="C02",
        name="Clinical guideline concordance",
        squad="C",
        squad_name=SQUADS["C"]["name"],
        scope="Does the management described follow recognised guidance for the condition?",
        instruction=(
            "Compare the management described against recognised clinical guidance for the recorded "
            "condition, and report where the pathway departs from it and whether the record justifies "
            "the departure.\n"
            "Report departure, not error: guidelines are not mandates, and a documented, reasoned "
            "departure is legitimate practice. Name the guidance you are reasoning from. A departure "
            "with a stated clinical justification in the record should normally be no_finding."
        ),
        knowledge_sources="Curated clinical practice guidelines by specialty; internal clinical policy",
        knowledge_mode="model_memory",
        max_severity="major",
        pacs_domain="clinical_appropriateness",
        tier=3,
    ),
    AgentSpec(
        agent_id="C03",
        name="Diagnostic investigation appropriateness",
        squad="C",
        squad_name=SQUADS["C"]["name"],
        scope="Are the investigations billed indicated, rationally sequenced and not needlessly repeated?",
        instruction=(
            "Evaluate whether the laboratory and imaging investigations billed are indicated for the "
            "presentation, whether the sequence is rational (a low-cost or first-line test before an "
            "advanced one, unless the presentation justifies going straight to the advanced test), and "
            "whether any repeat investigation within a short interval is justified by a change in the "
            "clinical picture. Flag broad panel testing where targeted testing is indicated, and "
            "simultaneous ordering of investigations that answer the same question.\n"
            "Quantify exposure as the billed value of the investigations you consider unsupported."
        ),
        knowledge_sources="Imaging and laboratory appropriateness criteria; repeat-testing intervals",
        knowledge_mode="model_memory",
        max_severity="moderate",
        pacs_domain="clinical_appropriateness",
        tier=2,
    ),
    AgentSpec(
        agent_id="C04",
        name="Pharmacotherapy appropriateness",
        squad="C",
        squad_name=SQUADS["C"]["name"],
        scope="Are the medicines indicated, and are dose, quantity and duration plausible?",
        instruction=(
            "Check that each prescribed medicine is indicated for a recorded diagnosis, and that the "
            "dose, quantity and duration are plausible for the encounter type and the treatment "
            "period. Flag quantities inconsistent with the length of the episode (a 90-day supply "
            "dispensed against a 7-day treatment course), doses outside the usual range for the "
            "member's age band, and medicines with no supporting diagnosis on the claim.\n"
            "Drug interactions are C05's question, not yours. Where no medicines are billed, return "
            "not_applicable."
        ),
        knowledge_sources="DoH Drug List and formulary; drug–indication mappings; dosing references",
        knowledge_mode="model_memory",
        max_severity="moderate",
        pacs_domain="clinical_appropriateness",
        tier=2,
    ),
    AgentSpec(
        agent_id="C05",
        name="Drug safety and interaction",
        squad="C",
        squad_name=SQUADS["C"]["name"],
        scope="Does the medication set carry a clinically significant safety signal?",
        instruction=(
            "Screen the medication set for clinically significant interactions, therapeutic "
            "duplication within a class, and contraindications against the recorded diagnoses and the "
            "member's age band.\n"
            "Treat this as a patient-safety signal first and an audit finding second: where you find "
            "a significant interaction, set recommended_action to refer_clinical and state the "
            "mechanism and the clinical consequence in plain language. Exposure is normally 0 for a "
            "pure safety finding. Where no medicines are billed, return not_applicable."
        ),
        knowledge_sources="Interaction and contraindication references; therapeutic class mappings",
        knowledge_mode="model_memory",
        max_severity="major",
        pacs_domain="clinical_appropriateness",
        tier=2,
    ),
    AgentSpec(
        agent_id="C06",
        name="Length of stay and level of care",
        squad="C",
        squad_name=SQUADS["C"]["name"],
        scope="Is the length of stay and level of care billed supported by the record?",
        instruction=(
            "Compare the length of stay and the level of care billed against the range you would "
            "expect for the diagnosis, the procedure and the complications actually documented. Flag "
            "stays extended without a documented clinical reason, intensive-care or high-dependency "
            "days billed without supporting observations, and inpatient admission where the record "
            "describes care deliverable as a day case.\n"
            "Where you find excess days, state the expected length of stay, the billed length of stay, "
            "and quantify exposure as the excess days at the billed per-diem rate. For outpatient "
            "encounters, return not_applicable."
        ),
        knowledge_sources="IR-DRG expected length-of-stay bands; level-of-care criteria",
        knowledge_mode="model_memory",
        max_severity="major",
        pacs_domain="clinical_appropriateness",
        tier=2,
    ),
    AgentSpec(
        agent_id="C07",
        name="Surgical indication and conservative therapy",
        squad="C",
        squad_name=SQUADS["C"]["name"],
        scope="For elective surgery, was conservative management tried and is the threshold met?",
        instruction=(
            "For elective surgical claims, test whether the record documents an adequate trial of "
            "conservative management where recognised guidance expects one, and whether the stated "
            "indication meets the usual threshold for intervention (symptom duration, severity, "
            "objective findings, failure of non-operative care).\n"
            "Emergency and trauma surgery is out of scope — return not_applicable. Where no surgical "
            "procedure is billed, return not_applicable."
        ),
        knowledge_sources="Surgical indication criteria by procedure; clinical guidelines",
        knowledge_mode="model_memory",
        max_severity="major",
        pacs_domain="clinical_appropriateness",
        tier=3,
    ),
    AgentSpec(
        agent_id="C08",
        name="Maternity, neonatal and paediatric pathways",
        squad="C",
        squad_name=SQUADS["C"]["name"],
        scope="Does the claim follow the pathway logic for obstetric, neonatal or paediatric care?",
        instruction=(
            "Apply pathway-specific logic to obstetric, neonatal and paediatric claims: gestational "
            "consistency across the coded elements, justification for the delivery mode where a "
            "caesarean is billed, neonatal level-of-care criteria, and age-appropriate dosing, "
            "equipment and procedure selection for children.\n"
            "Where the claim is not maternity, neonatal or paediatric, return not_applicable "
            "immediately — do not stretch to produce a finding."
        ),
        knowledge_sources="Maternity and neonatal care standards; paediatric references",
        knowledge_mode="model_memory",
        max_severity="major",
        pacs_domain="clinical_appropriateness",
        tier=2,
    ),
]


# ==========================================================================
# SQUAD E — Policy, benefit and contract adjudication (6 agents, RAG-grounded)
# ==========================================================================

_SQUAD_E: list[AgentSpec] = [
    AgentSpec(
        agent_id="E01",
        name="Benefit coverage and policy terms",
        squad="E",
        squad_name=SQUADS["E"]["name"],
        scope="Does the service fall within the member's benefit at all?",
        instruction=(
            "Determine whether the service falls within the member's benefit, reading the actual "
            "policy wording supplied to you rather than any simplified benefit code. Handle the "
            "ambiguous cases that rule engines mishandle: cosmetic versus reconstructive, screening "
            "versus diagnostic, dental accident versus routine dental, obesity treatment versus "
            "treatment of a comorbidity.\n"
            "Every conclusion must cite the clause it rests on. Where the retrieved clauses do not "
            "settle the question, return insufficient_evidence and name the clause you would need."
        ),
        knowledge_sources="Policy wordings and schedules by product; benefit definitions",
        knowledge_mode="rag_policy",
        max_severity="major",
        pacs_domain="policy_adjudication",
        tier=2,
        retrieval_hint=(
            "benefit coverage scope cosmetic reconstructive screening diagnostic dental optical "
            "exclusion medically necessary table of benefits"
        ),
    ),
    AgentSpec(
        agent_id="E02",
        name="Exclusions and waiting periods",
        squad="E",
        squad_name=SQUADS["E"]["name"],
        scope="Is the claim caught by an exclusion or by a waiting period?",
        instruction=(
            "Test the claim against the exclusion list and against every applicable waiting period, "
            "including the specific-condition waiting periods that apply on new corporate schemes.\n"
            "For a waiting period finding, show the arithmetic explicitly: the scheme inception date, "
            "the date of service, the elapsed months, and the required waiting period from the clause. "
            "Do not conclude a waiting period bites without doing that calculation. Check whether a "
            "continuity-of-cover waiver clause could apply before concluding."
        ),
        knowledge_sources="Policy exclusion clauses; waiting period rules; scheme inception data",
        knowledge_mode="rag_policy",
        max_severity="major",
        pacs_domain="policy_adjudication",
        tier=2,
        retrieval_hint=(
            "exclusions excluded not liable waiting period inception date general waiting "
            "six months twelve months maternity dental optical pre-existing chronic "
            "specified conditions continuity waiver cosmetic obesity infertility experimental "
            "congenital vaccination refractive prosthetic self-inflicted hazardous"
        ),
    ),
    AgentSpec(
        agent_id="E03",
        name="Pre-existing and chronic condition",
        squad="E",
        squad_name=SQUADS["E"]["name"],
        scope="Was the condition pre-existing or chronic, and how does the policy treat it?",
        instruction=(
            "Assess whether the condition treated meets the policy's definition of a pre-existing or "
            "chronic condition, using the clinical record and any history stated on the claim, and "
            "apply the policy's treatment of that classification.\n"
            "Because the consequences for the member are significant, set recommended_action to "
            "refer_clinical or request_information rather than deny unless the record is unambiguous. "
            "Quote the definition clause you are applying. Where the record contains no evidence of "
            "prior existence, say so plainly and return no_finding — absence of history is not "
            "evidence of concealment."
        ),
        knowledge_sources="Member claim and clinical history; policy treatment of pre-existing conditions",
        knowledge_mode="rag_policy",
        max_severity="major",
        pacs_domain="policy_adjudication",
        tier=3,
        retrieval_hint=(
            "pre-existing condition definition chronic condition twenty-four months signs symptoms "
            "declared waiting period continuity transfer misrepresentation"
        ),
    ),
    AgentSpec(
        agent_id="E04",
        name="Pre-authorisation requirement and adherence",
        squad="E",
        squad_name=SQUADS["E"]["name"],
        scope="Was pre-authorisation required, obtained, valid and matched to what was delivered?",
        instruction=(
            "Determine whether pre-authorisation was required for this service — by service type or "
            "by billed value threshold — and if so whether it was obtained, whether the service "
            "delivered matches what was authorised, and whether the authorisation was valid on the "
            "date of service.\n"
            "Check the value threshold against the claim's gross amount explicitly. Where the "
            "encounter is an emergency, check the emergency exemption clause and the notification "
            "window before concluding. Quote the clause that creates the requirement."
        ),
        knowledge_sources="Pre-authorisation rules by service and product; authorisation records",
        knowledge_mode="rag_policy",
        max_severity="major",
        pacs_domain="policy_adjudication",
        tier=2,
        retrieval_hint=(
            "pre-authorisation prior authorisation required threshold MRI CT endoscopy surgery "
            "inpatient admission validity thirty days emergency exemption notification splitting"
        ),
    ),
    AgentSpec(
        agent_id="E05",
        name="Sub-limits, annual caps and accumulators",
        squad="E",
        squad_name=SQUADS["E"]["name"],
        scope="Does the claim sit within the applicable sub-limit and annual cap?",
        instruction=(
            "Work in this order.\n"
            "First, identify every sub-limit and annual cap that applies to the services billed and "
            "state the limit from the schedule. Then compare THIS CLAIM ALONE to that limit. If the "
            "claim on its own already exceeds the limit, that is a finding and the exposure is the "
            "excess — you do not need the member's accumulated utilisation to know that, because "
            "accumulated utilisation can only make it worse.\n"
            "Only where the claim alone sits within the limit, and the answer therefore turns on how "
            "much the member has already used, return insufficient_evidence and name the accumulator "
            "balance you need. Never assume the balance is nil.\n"
            "Show the arithmetic every time: benefit, limit, amount claimed under that benefit, excess."
        ),
        knowledge_sources="Policy sub-limit schedules; member accumulator balances",
        knowledge_mode="rag_policy",
        max_severity="moderate",
        pacs_domain="policy_adjudication",
        tier=2,
        retrieval_hint=(
            "sub-limit annual aggregate limit table of benefits schedule dental optical physiotherapy "
            "pharmacy maternity psychiatric accumulator policy year reset carry forward"
        ),
    ),
    AgentSpec(
        agent_id="E06",
        name="Territorial scope and network tier",
        squad="E",
        squad_name=SQUADS["E"]["name"],
        scope="Is the place of treatment in scope, and was the right network tier applied?",
        instruction=(
            "Confirm the place of treatment falls within the policy's geographic scope, and that the "
            "correct network tier and reimbursement basis were applied — including the special "
            "treatment of emergency care obtained outside the network or outside the country.\n"
            "Where treatment was obtained abroad, first establish from the record whether it was "
            "elective or an emergency, because the clauses differ completely. Quote the territorial "
            "clause and the network clause you rely on, and state the reimbursement percentage that "
            "should have applied."
        ),
        knowledge_sources="Policy territorial clauses; network tier definitions; emergency care rules",
        knowledge_mode="rag_policy",
        max_severity="moderate",
        pacs_domain="policy_adjudication",
        tier=2,
        retrieval_hint=(
            "territorial scope geographic United Arab Emirates elective treatment abroad emergency "
            "worldwide network tier gold reimbursement seventy per cent mandatory tariff direct billing"
        ),
    ),
]


# ==========================================================================
# SQUAD H — Synthesis, scoring and explanation (4 agents)
# H05 (Provider Audit Compliance Score) is out of scope for the demonstrator.
# ==========================================================================

_SQUAD_H: list[AgentSpec] = [
    AgentSpec(
        agent_id="H01",
        name="Evidence consolidation",
        squad="H",
        squad_name=SQUADS["H"]["name"],
        scope="What, in total, is wrong with this claim, without double counting?",
        instruction=(
            "You receive every finding raised on this claim by the audit squads. Deduplicate findings "
            "that describe the same underlying defect from different angles, group what remains into "
            "distinct defects, and compute the total monetary exposure without double-counting "
            "overlapping amounts on the same service line.\n"
            "Where two agents have quantified the same line, take the larger amount once, not the sum. "
            "Return a short list of consolidated defects in priority order."
        ),
        knowledge_sources="All upstream agent outputs; exposure calculation rules",
        knowledge_mode="upstream",
        max_severity="major",
        pacs_domain="none",
        tier=0,
    ),
    AgentSpec(
        agent_id="H02",
        name="Conflict resolution and adjudication",
        squad="H",
        squad_name=SQUADS["H"]["name"],
        scope="Where do the agents disagree, and which reading is better supported?",
        instruction=(
            "Identify where the agents disagree — one finding necessity established and another not, "
            "one treating a service as covered and another as excluded — and weigh the competing "
            "readings by evidence quality and source authority. A grounded citation from the policy "
            "wording outranks an inference from general knowledge.\n"
            "Present the disagreement to the auditor rather than hiding it: name both positions, say "
            "which you consider better supported and why, and say what would settle it. If there is "
            "no genuine disagreement, say so in one sentence."
        ),
        knowledge_sources="Agent reliability statistics; source authority hierarchy",
        knowledge_mode="upstream",
        max_severity="moderate",
        pacs_domain="none",
        tier=0,
    ),
    AgentSpec(
        agent_id="H03",
        name="Disposition recommendation",
        squad="H",
        squad_name=SQUADS["H"]["name"],
        scope="What should happen to this claim, and on whose authority?",
        instruction=(
            "Convert the consolidated findings into a recommended disposition — approve, partially "
            "approve with a specified deduction, deny with a specified reason, request information, "
            "or refer — with the arithmetic shown line by line.\n"
            "State the gross billed amount, each proposed deduction with the line it attaches to and "
            "the agent that raised it, the recommended settlement, and the delegated authority level "
            "required to action it (auditor up to AED 10,000; audit manager up to AED 50,000; medical "
            "director above that; SIU for any suspected-fraud referral).\n"
            "The recommendation is advisory. A human must decide."
        ),
        knowledge_sources="Adjudication policy; delegation of authority matrix; denial code mappings",
        knowledge_mode="upstream",
        max_severity="major",
        pacs_domain="none",
        tier=0,
    ),
    AgentSpec(
        agent_id="H04",
        name="Audit narrative and provider communication",
        squad="H",
        squad_name=SQUADS["H"]["name"],
        scope="How is this explained to the internal record, and to the provider?",
        instruction=(
            "Write two things.\n"
            "First, the internal audit rationale: professional, complete, suitable for the permanent "
            "record and for defending the decision on challenge.\n"
            "Second, a provider-facing explanation that states the finding, the rule relied on and "
            "the evidence, in a tone appropriate to a contracted counterparty. The provider-facing "
            "text must not disclose internal risk scoring, agent names, confidence values or triage "
            "logic. Supply it in English and in Arabic.\n"
            "If there is nothing adverse to communicate, say that plainly in both."
        ),
        knowledge_sources="House style guide; denial and communication templates; bilingual terminology",
        knowledge_mode="upstream",
        max_severity="minor",
        pacs_domain="none",
        tier=0,
    ),
]


DEFAULT_FLEET: list[AgentSpec] = _SQUAD_B + _SQUAD_C + _SQUAD_E + _SQUAD_H

AUDIT_SQUADS = ("B", "C", "E")   # produce findings
SYNTHESIS_SQUAD = "H"            # consume findings


def default_fleet() -> list[AgentSpec]:
    """A fresh, mutable copy — the Agent Studio edits this, not the module."""
    return [a.copy() for a in DEFAULT_FLEET]


def by_id(fleet: list[AgentSpec], agent_id: str) -> AgentSpec | None:
    for a in fleet:
        if a.agent_id == agent_id:
            return a
    return None


# --------------------------------------------------------------------------
# What the demonstrator does NOT build, and why. Shown in the UI verbatim.
# --------------------------------------------------------------------------

OUT_OF_SCOPE = [
    {
        "squad": "A",
        "name": "Intake, data quality and eligibility",
        "agents": 6,
        "why": "Needs the Shafafiya / eClaimLink schema and a live policy administration extract "
               "to validate membership, licensing and encounter structure.",
    },
    {
        "squad": "D",
        "name": "Financial and tariff integrity",
        "agents": 8,
        "why": "Needs the DoH Mandatory Tariff, ADNIC's provider contracts and rate cards, and the "
               "IR-DRG grouper. Recalculating a price without the price list is theatre.",
    },
    {
        "squad": "F",
        "name": "Fraud, waste and abuse",
        "agents": 8,
        "why": "Operates across claims, not on one claim. Needs a historical claim store and peer "
               "distributions before any outlier statement means anything.",
    },
    {
        "squad": "G",
        "name": "Regulatory and standards compliance",
        "agents": 5,
        "why": "Needs the DoH Claims and Adjudication Rules corpus and the denial code lists.",
    },
    {
        "squad": "I",
        "name": "Assurance and oversight",
        "agents": 6,
        "why": "Needs a golden dataset, live auditor decision history and a source version register "
               "before precision, calibration or drift can be measured rather than asserted.",
    },
    {
        "squad": "H05",
        "name": "Provider Audit Compliance Score",
        "agents": 1,
        "why": "A provider score computed on a handful of claims is not a score, it is noise. PACS "
               "needs volume and confirmed outcomes before it can survive being challenged.",
    },
]
