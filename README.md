# 🩺 Agentic Medical Claim Analysis

An open-source [Streamlit](https://streamlit.io) app that runs a panel of
configurable **AI agents** over a spreadsheet of medical claims. Each agent
reviews every claim through a different lens — diagnosis/service consistency,
possible upcoding, unusual service frequency, or any custom check you define —
and writes its assessment into its own column. Download the enriched results as
Excel or CSV.

Works with **OpenAI** (cloud) or a **local Ollama model** (fully offline).

## Features

- Upload `.xlsx` or `.csv`, map your own columns.
- Add, edit, remove, and reset agents through the UI — no code changes needed.
- Bring-your-own-key: the OpenAI key stays in session memory and is never written to disk.
- One-click Excel / CSV download of results.
- Live progress bar and per-agent status.
- Runs offline with Ollama for sensitive data.

## Quick start

```bash
git clone <your-repo-url>
cd agentic_claims
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL Streamlit prints (usually http://localhost:8501).

A `sample_claims.xlsx` file is included so you can try it immediately.

## Using OpenAI

Choose **OpenAI** in the sidebar and paste your API key. To pre-fill a key for a
deployment, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
and add your key — users can still override it in the UI.

## Using Ollama (local, offline)

1. Install [Ollama](https://ollama.com) and start it.
2. Pull a model, e.g. `ollama pull llama3.1`.
3. Choose **Ollama** in the sidebar and enter the model name.

## Input format (standard)

Files must be `.xlsx` or `.csv` with **one row per claim** and these five columns,
named exactly:

| Column | Description |
|---|---|
| `Claim ID` | Unique identifier for the claim |
| `Input Details` | Free-text claim block the agents analyze |
| `FacilityType` | e.g. Hospital, Clinic |
| `Department` | e.g. Radiology, Orthopedics |
| `Insurance Company` | Insurer name |

The `Input Details` cell should follow this structure (multi-line text in one cell):

```
Patient Name: <name>
Date of Service: <Month DD, YYYY>
Provider: <clinic or hospital>
Diagnosis: <diagnosis>
Treatment: <short treatment summary>
Claim Details:
- Date of Service: <Month DD, YYYY>
- Medical Procedures: <procedure 1, procedure 2, ...>
- Total Claim Amount: $<amount>
- Itemized Costs:
  - <procedure>: $<amount>
Supporting Documentation:
- <document>
```

The app validates uploads against this format and offers a **blank template**
download in-app (also see `sample_claims.xlsx`). Column names are case-sensitive.

## Deploying

Deploy free on [Streamlit Community Cloud](https://streamlit.io/cloud): push this
repo to GitHub and point Streamlit Cloud at `app.py`. Other options include
Hugging Face Spaces, Render, or any container host.

## Privacy & disclaimer

Files are processed in memory for the session and are not stored server-side.
With the OpenAI backend, claim text is sent to OpenAI under their terms; use the
Ollama backend for fully local processing.

This is a **screening / decision-support tool**, not a substitute for
professional medical, coding, or compliance review.

## License

MIT — see [LICENSE](LICENSE). Contributions welcome.
