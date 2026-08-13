"""
Agentic Medical Claim Analysis — Streamlit App  (LEGACY DEMONSTRATOR)
=====================================================================

This is the original single-file demonstrator, preserved unchanged. The current
application is `app.py`; see README.md.

An open-source tool that runs multiple configurable "AI agents" over medical
claims data. Each agent inspects a claim (diagnosis, services, etc.) through a
different lens — diagnosis/service consistency, upcoding, service frequency, and
any custom checks you add — and writes its assessment into a new column.

Supports both OpenAI and a local Ollama model, so it works fully offline or in
the cloud.

Run locally with:
    streamlit run legacy_app.py
"""

import io
import time

import pandas as pd
import streamlit as st

# Optional imports — the app still loads if these aren't installed, and only
# complains when a user actually tries to use that backend.
try:
    import openai
except ImportError:  # pragma: no cover
    openai = None

try:
    import ollama
except ImportError:  # pragma: no cover
    ollama = None


# -----------------------------------------------------------------------------
# Page config & light styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Agentic Medical Claim Analysis",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 2.5rem; max-width: 1100px;}
      .agent-card {
        border: 1px solid rgba(128,128,128,.25);
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: .75rem;
        background: rgba(128,128,128,.04);
      }
      .stButton>button {border-radius: 8px; font-weight: 600;}
      div[data-testid="stMetricValue"] {font-size: 1.4rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Standard input format
# -----------------------------------------------------------------------------
# The app expects a spreadsheet with exactly these columns. "Input Details" is
# the free-text block each agent reads; the other columns give context.
REQUIRED_COLUMNS = [
    "Claim ID",
    "Input Details",
    "FacilityType",
    "Department",
    "Insurance Company",
]

# The recommended structure for the free-text "Input Details" cell.
INPUT_DETAILS_TEMPLATE = (
    "Patient Name: <name>\n"
    "Date of Service: <Month DD, YYYY>\n"
    "Provider: <clinic or hospital>\n"
    "Diagnosis: <diagnosis>\n"
    "Treatment: <short treatment summary>\n"
    "Claim Details:\n"
    "- Date of Service: <Month DD, YYYY>\n"
    "- Medical Procedures: <procedure 1, procedure 2, ...>\n"
    "- Total Claim Amount: $<amount>\n"
    "- Itemized Costs:\n"
    "  - <procedure>: $<amount>\n"
    "  - <procedure>: $<amount>\n"
    "Supporting Documentation:\n"
    "- <document 1>\n"
    "- <document 2>"
)


def build_template_df():
    """Return a 2-row example DataFrame in the standard format."""
    example_details = (
        "Patient Name: Jane Smith\n"
        "Date of Service: September 10, 2024\n"
        "Provider: Prestige Clinic\n"
        "Diagnosis: Chronic lower back pain\n"
        "Treatment: Multiple procedures on the same day\n"
        "Claim Details:\n"
        "- Date of Service: September 10, 2024\n"
        "- Medical Procedures: Spinal fusion surgery, MRI, and physical therapy\n"
        "- Total Claim Amount: $75,000\n"
        "- Itemized Costs:\n"
        "  - Spinal Fusion Surgery: $50,000\n"
        "  - MRI: $15,000\n"
        "  - Physical Therapy: $10,000\n"
        "Supporting Documentation:\n"
        "- MRI report\n"
        "- Surgery report"
    )
    example_details_2 = (
        "Patient Name: John Doe\n"
        "Date of Service: August 15, 2024\n"
        "Provider: Riverside Medical Center\n"
        "Diagnosis: Torn rotator cuff\n"
        "Treatment: Arthroscopic surgery and follow-up\n"
        "Claim Details:\n"
        "- Date of Service: August 15, 2024\n"
        "- Medical Procedures: Arthroscopic shoulder surgery, ultrasound\n"
        "- Total Claim Amount: $42,000\n"
        "- Itemized Costs:\n"
        "  - Shoulder Surgery: $35,000\n"
        "  - Ultrasound: $7,000\n"
        "Supporting Documentation:\n"
        "- Ultrasound report\n"
        "- Surgery report"
    )
    return pd.DataFrame(
        [
            ["CLM-001", example_details, "Hospital", "Orthopedics", "CompanyX"],
            ["CLM-002", example_details_2, "Hospital", "Radiology", "CompanyY"],
        ],
        columns=REQUIRED_COLUMNS,
    )


def template_excel_bytes():
    """Serialize the template DataFrame to an in-memory .xlsx file."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        build_template_df().to_excel(writer, index=False, sheet_name="Sheet1")
    buf.seek(0)
    return buf


def validate_format(dataframe):
    """Return (missing_columns, extra_columns, warnings) for an uploaded frame."""
    cols = list(dataframe.columns)
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    extra = [c for c in cols if c not in REQUIRED_COLUMNS]
    warnings = []
    if "Input Details" in cols:
        empties = int(dataframe["Input Details"].isna().sum())
        if empties:
            warnings.append(f"{empties} row(s) have an empty 'Input Details' cell.")
    return missing, extra, warnings


# -----------------------------------------------------------------------------
# Default agent prompts (ported from the original script)
# -----------------------------------------------------------------------------
DEFAULT_AGENTS = {
    "Diagnosis Service Match": (
        "You are an AI agent focused on the consistency between Diagnosis and "
        "Services Provided in a medical claim.\n"
        "Based *only* on the information given for this claim (Claim ID, "
        "Diagnosis, Services Provided), assess how well the Services align with "
        "what might typically be expected for the stated Diagnosis.\n"
        "Assign a score from 1 (Highly Consistent - Low Concern) to 10 (Highly "
        "Inconsistent - High Concern).\n"
        "Provide a single sentence explaining your reasoning, focusing *only* on "
        "the diagnosis-service relationship.\n"
        "Output Format:\nScore: [1-10]\nRationale: [Your one-sentence explanation]"
    ),
    "Upcoding Check": (
        "You are an AI agent specializing in identifying potential upcoding in "
        "medical claims.\n"
        "Analyze the provided Services. Do they seem excessively complex or "
        "comprehensive given the Diagnosis? Consider if simpler, less costly "
        "services might have been appropriate.\n"
        "Provide a brief assessment (1-2 sentences) indicating whether there's a "
        "low, medium, or high suspicion of upcoding based *only* on the Diagnosis "
        "and Services list. Explain your reasoning concisely.\n"
        "Output Format:\nUpcoding Suspicion: [Low/Medium/High]\n"
        "Reasoning: [Your brief explanation]"
    ),
    "Service Frequency Alert": (
        "You are an AI agent evaluating the frequency or duration of services "
        "provided for a given diagnosis.\n"
        "Based on the Diagnosis and Services Provided, does the *quantity* or "
        "*duration* (if implied) of services seem unusual or excessive for "
        "treating the stated diagnosis in a typical scenario? Focus solely on the "
        "volume/frequency aspect.\n"
        "State whether the frequency appears 'Normal' or 'Potentially Excessive'. "
        "Add a one-sentence justification.\n"
        "Output Format:\nFrequency Assessment: [Normal/Potentially Excessive]\n"
        "Justification: [Your one-sentence justification]"
    ),
}


# -----------------------------------------------------------------------------
# Session state initialisation
# -----------------------------------------------------------------------------
if "agents" not in st.session_state:
    # Copy so users can edit freely without touching the defaults
    st.session_state.agents = dict(DEFAULT_AGENTS)
if "results_df" not in st.session_state:
    st.session_state.results_df = None


# -----------------------------------------------------------------------------
# Model call
# -----------------------------------------------------------------------------
def chat_with_model(user_input, system_prompt, backend, model_name, openai_client=None):
    """Send a single prompt to the chosen backend and return the text response."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    try:
        if backend == "Ollama":
            if ollama is None:
                return "ERROR: The 'ollama' package is not installed on this server."
            response = ollama.chat(model=model_name, messages=messages)
            return response["message"]["content"]

        # OpenAI
        if openai_client is None:
            return "ERROR: OpenAI client not initialized. Add a valid API key."
        response = openai_client.chat.completions.create(
            model=model_name, messages=messages
        )
        return response.choices[0].message.content

    except Exception as e:  # noqa: BLE001 — surface any backend error into the cell
        return f"ERROR: AI agent call failed. Details: {e}"


# -----------------------------------------------------------------------------
# Sidebar — configuration
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuration")

    backend = st.radio(
        "AI backend",
        ["OpenAI", "Ollama"],
        help="OpenAI runs in the cloud (needs an API key). Ollama runs a local "
        "model on the same machine as this app.",
    )

    if backend == "OpenAI":
        # Prefer a secret if the deployer set one, otherwise ask the user.
        default_key = ""
        try:
            default_key = st.secrets.get("OPENAI_API_KEY", "")
        except Exception:  # pragma: no cover — no secrets file present
            default_key = ""

        api_key = st.text_input(
            "OpenAI API key",
            value=default_key,
            type="password",
            help="Your key is only held in memory for this session and never "
            "written to disk.",
        )
        model_name = st.text_input("Model", value="gpt-4o-mini")
    else:
        api_key = None
        model_name = st.text_input("Ollama model", value="llama3.1")
        st.caption("Make sure Ollama is running and the model is pulled locally.")

    st.divider()
    st.caption(
        "Open source · Bring your own key · No claim data is stored server-side."
    )


# -----------------------------------------------------------------------------
# Main — header
# -----------------------------------------------------------------------------
st.title("🩺 Agentic Medical Claim Analysis")
st.markdown(
    "Upload a spreadsheet of medical claims and let a panel of configurable AI "
    "agents review each one — flagging diagnosis/service mismatches, possible "
    "upcoding, unusual service frequency, and any custom checks you define."
)

tab_run, tab_agents, tab_help = st.tabs(["▶️ Run analysis", "🤖 Agents", "❓ Help"])


# -----------------------------------------------------------------------------
# Tab: Agents (view / edit / add / remove)
# -----------------------------------------------------------------------------
with tab_agents:
    st.subheader("Configure your agents")
    st.caption(
        "Each agent gets its own output column. Edit the prompts, remove ones you "
        "don't need, or add your own checks."
    )

    to_delete = None
    for name, prompt in list(st.session_state.agents.items()):
        with st.container():
            st.markdown('<div class="agent-card">', unsafe_allow_html=True)
            c1, c2 = st.columns([5, 1])
            with c1:
                new_name = st.text_input("Agent name", value=name, key=f"name_{name}")
            with c2:
                st.write("")
                st.write("")
                if st.button("🗑️ Remove", key=f"del_{name}"):
                    to_delete = name
            new_prompt = st.text_area(
                "System prompt", value=prompt, height=160, key=f"prompt_{name}"
            )
            # Persist edits (rename handled by rebuild below)
            if new_name != name:
                st.session_state.agents = {
                    (new_name if k == name else k): (
                        new_prompt if k == name else v
                    )
                    for k, v in st.session_state.agents.items()
                }
                st.rerun()
            else:
                st.session_state.agents[name] = new_prompt
            st.markdown("</div>", unsafe_allow_html=True)

    if to_delete is not None:
        del st.session_state.agents[to_delete]
        st.rerun()

    st.divider()
    with st.form("add_agent", clear_on_submit=True):
        st.markdown("**➕ Add a new agent**")
        add_name = st.text_input("New agent name", placeholder="e.g. Duplicate Billing Check")
        add_prompt = st.text_area(
            "New agent system prompt",
            placeholder="You are an AI agent that checks for...",
            height=120,
        )
        if st.form_submit_button("Add agent"):
            if add_name.strip() and add_prompt.strip():
                st.session_state.agents[add_name.strip()] = add_prompt.strip()
                st.success(f"Added agent: {add_name.strip()}")
                st.rerun()
            else:
                st.warning("Please provide both a name and a prompt.")

    if st.button("↩️ Reset to default agents"):
        st.session_state.agents = dict(DEFAULT_AGENTS)
        st.rerun()


# -----------------------------------------------------------------------------
# Tab: Run
# -----------------------------------------------------------------------------
with tab_run:
    st.subheader("1 · Upload your claims")

    # --- Format guidance up front ---
    with st.expander("📋 Required file format (read this first)", expanded=True):
        st.markdown(
            "Your file must be an **Excel (.xlsx)** or **CSV** with these five "
            "columns, spelled exactly as shown:"
        )
        st.table(
            pd.DataFrame(
                {
                    "Column": REQUIRED_COLUMNS,
                    "Required": ["Yes", "Yes", "Yes", "Yes", "Yes"],
                    "What it holds": [
                        "A unique identifier for each claim.",
                        "The main free-text claim block the agents read (see below).",
                        "e.g. Hospital, Clinic, Outpatient.",
                        "e.g. Radiology, Orthopedics.",
                        "Name of the insurer.",
                    ],
                }
            )
        )
        st.markdown(
            "**One row = one claim.** The `Input Details` cell should follow this "
            "structure (multi-line text inside a single cell):"
        )
        st.code(INPUT_DETAILS_TEMPLATE, language="text")
        st.download_button(
            "⬇️ Download blank template (.xlsx)",
            data=template_excel_bytes(),
            file_name="claims_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="A ready-to-fill spreadsheet with the correct columns and two "
            "example rows.",
        )

    uploaded = st.file_uploader(
        "Excel (.xlsx) or CSV file",
        type=["xlsx", "csv"],
        help="Must match the standard format above.",
    )

    df = None
    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith(".csv"):
                df = pd.read_csv(uploaded)
            else:
                df = pd.read_excel(uploaded, engine="openpyxl")
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read the file: {e}")
            df = None

        if df is not None:
            missing, extra, warnings = validate_format(df)
            if missing:
                st.error(
                    "❌ This file doesn't match the standard format. Missing "
                    f"required column(s): **{', '.join(missing)}**. "
                    "Download the template above and match the column names exactly."
                )
                df = None
            else:
                st.success(f"✅ Format looks good — loaded {len(df)} rows.")
                if extra:
                    st.info(
                        "Note: extra column(s) will be kept but ignored by the "
                        f"agents: {', '.join(extra)}."
                    )
                for w in warnings:
                    st.warning(f"⚠️ {w}")
                st.dataframe(df.head(10), use_container_width=True)

    if df is not None:
        # Standard format guarantees these columns exist.
        id_col = "Claim ID"
        details_col = "Input Details"

        active_agents = st.session_state.agents
        st.subheader("2 · Run")
        st.caption(
            f"{len(active_agents)} agent(s) × {len(df)} row(s) = "
            f"{len(active_agents) * len(df)} model calls."
        )

        ready = True
        if backend == "OpenAI" and not api_key:
            st.warning("Add your OpenAI API key in the sidebar to continue.")
            ready = False
        if not active_agents:
            st.warning("Add at least one agent in the Agents tab.")
            ready = False

        if st.button("🚀 Run analysis", type="primary", disabled=not ready):
            openai_client = None
            if backend == "OpenAI":
                if openai is None:
                    st.error("The 'openai' package isn't installed on this server.")
                    st.stop()
                try:
                    openai_client = openai.OpenAI(api_key=api_key)
                except Exception as e:  # noqa: BLE001
                    st.error(f"Could not initialise OpenAI client: {e}")
                    st.stop()

            result = df.copy()
            for agent_name in active_agents:
                col = agent_name.replace(" ", "_") + "_Response"
                if col not in result.columns:
                    result[col] = ""

            total = len(result) * len(active_agents)
            done = 0
            progress = st.progress(0.0, text="Starting…")
            log = st.empty()

            for idx, row in result.iterrows():
                claim_id = (
                    str(row[id_col])
                    if id_col in result.columns and pd.notna(row[id_col])
                    else f"Row_{idx + 1}"
                )
                details = str(row[details_col]) if pd.notna(row[details_col]) else ""
                if not details or details.lower() == "nan":
                    done += len(active_agents)
                    progress.progress(
                        done / total, text=f"Skipped empty row {idx + 1}"
                    )
                    continue

                user_prompt = f"Claim ID: {claim_id}\n{details}"

                for agent_name, system_prompt in active_agents.items():
                    log.info(f"Row {idx + 1} · {agent_name}…")
                    response = chat_with_model(
                        user_prompt,
                        system_prompt,
                        backend,
                        model_name,
                        openai_client,
                    )
                    col = agent_name.replace(" ", "_") + "_Response"
                    result.at[idx, col] = str(response).strip()
                    done += 1
                    progress.progress(min(done / total, 1.0))

            progress.progress(1.0, text="Done!")
            log.empty()
            st.session_state.results_df = result
            st.success("Analysis complete.")

    # Results (persist across reruns)
    if st.session_state.results_df is not None:
        st.subheader("3 · Results")
        result = st.session_state.results_df
        st.dataframe(result, use_container_width=True)

        # Excel download
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            result.to_excel(writer, index=False, sheet_name="Agentic Output")
        buf.seek(0)

        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "⬇️ Download Excel",
                data=buf,
                file_name="Claims - Agentic Output.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with d2:
            st.download_button(
                "⬇️ Download CSV",
                data=result.to_csv(index=False).encode("utf-8"),
                file_name="Claims - Agentic Output.csv",
                mime="text/csv",
            )


# -----------------------------------------------------------------------------
# Tab: Help
# -----------------------------------------------------------------------------
with tab_help:
    st.subheader("How it works")
    st.markdown(
        """
1. **Choose a backend** in the sidebar — OpenAI (cloud, needs a key) or Ollama
   (local model).
2. **Configure agents** in the *Agents* tab. Each agent is just a system prompt
   with a role; each one produces its own results column.
3. **Upload** a file that matches the standard format (below) and **run**.
4. **Download** the enriched spreadsheet.
        """
    )

    st.divider()
    st.subheader("📋 Data format standard")
    st.markdown(
        "Every uploaded file must have these five columns, named exactly as shown "
        "(one row per claim):"
    )
    st.table(
        pd.DataFrame(
            {
                "Column": REQUIRED_COLUMNS,
                "Description": [
                    "Unique identifier for the claim.",
                    "Free-text claim block the agents analyze.",
                    "Facility type, e.g. Hospital / Clinic.",
                    "Department, e.g. Radiology / Orthopedics.",
                    "Insurer name.",
                ],
            }
        )
    )
    st.markdown("Recommended structure for the **Input Details** cell:")
    st.code(INPUT_DETAILS_TEMPLATE, language="text")
    st.download_button(
        "⬇️ Download blank template (.xlsx)",
        data=template_excel_bytes(),
        file_name="claims_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="help_template",
    )
    st.markdown(
        """
**Tips**
- Column names are case-sensitive and must match exactly.
- Keep everything for one claim on a single row; multi-line text within the
  `Input Details` cell is fine (use Alt+Enter in Excel for line breaks).
- The app checks your file on upload and tells you if a required column is
  missing.
        """
    )

    st.divider()
    st.subheader("Privacy & disclaimer")
    st.markdown(
        """
**Privacy:** files are processed in memory for the session and are not stored on
the server. When using OpenAI, claim text is sent to OpenAI's API under their
terms. For fully local/offline use, choose the Ollama backend.

**Disclaimer:** this is a decision-support and screening tool, not a substitute
for professional medical, coding, or compliance review.
        """
    )
    st.divider()
    st.caption("MIT-licensed · Contributions welcome.")
