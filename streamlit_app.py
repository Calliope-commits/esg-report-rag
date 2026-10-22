import asyncio
import json
import os
import time
from pathlib import Path

import inngest
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="DocuMind", page_icon="📄", layout="centered")


@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    return inngest.Inngest(app_id="rag_app", is_production=False)


def save_uploaded_pdf(file) -> Path:
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_path.write_bytes(file.getbuffer())
    return file_path


async def send_rag_ingest_event(pdf_path: Path) -> None:
    client = get_inngest_client()
    await client.send(
        inngest.Event(
            name="rag/ingest_pdf",
            data={"pdf_path": str(pdf_path.resolve()), "source_id": pdf_path.name},
        )
    )


async def send_rag_query_event(question: str, top_k: int) -> str:
    client = get_inngest_client()
    result = await client.send(
        inngest.Event(name="rag/query_pdf_ai", data={"question": question, "top_k": top_k})
    )
    return result[0]


def _inngest_api_base() -> str:
    # Local dev server default; configurable via env
    return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")


def fetch_runs(event_id: str) -> list[dict]:
    resp = requests.get(f"{_inngest_api_base()}/events/{event_id}/runs")
    resp.raise_for_status()
    return resp.json().get("data", [])


def wait_for_run_output(event_id: str, timeout_s: float = 300.0, poll_interval_s: float = 1.0) -> dict:
    start = time.time()
    last_status = None
    while True:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status
            if status in ("Completed", "Succeeded", "Success", "Finished"):
                output = run.get("output")
                if isinstance(output, str):
                    output = json.loads(output)  # Output may be returned as a JSON string
                if output:
                    return output
                # Run marked complete but output not stored yet: keep polling
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Function run {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Timed out waiting for run output (last status: {last_status})")
        time.sleep(poll_interval_s)


# ---------- Header ----------
st.title("DocuMind — Ask your documents")
st.caption("Upload reports, policies or manuals and get sourced answers in seconds.")

# ---------- Ingestion ----------
st.header("📄 Add documents to your knowledge base")

# Remember ingested files so Streamlit reruns don't re-trigger ingestion
if "ingested_files" not in st.session_state:
    st.session_state.ingested_files = set()

uploaded = st.file_uploader("Choose a PDF", type=["pdf"], accept_multiple_files=False)

if uploaded is not None:
    if uploaded.name not in st.session_state.ingested_files:
        with st.spinner("Uploading and triggering ingestion..."):
            path = save_uploaded_pdf(uploaded)
            asyncio.run(send_rag_ingest_event(path))
        st.session_state.ingested_files.add(uploaded.name)
    st.success(f"Ingestion triggered for: {uploaded.name}")

st.divider()

# ---------- Question ----------
st.header("💬 What would you like to know?")

with st.form("rag_query_form"):
    question = st.text_input("Your question")
    with st.expander("Advanced settings"):
        top_k = st.number_input("Number of passages to search", min_value=1, max_value=20, value=5, step=1)
    submitted = st.form_submit_button("Ask")

if submitted and question.strip():
    with st.spinner("Searching your documents and generating an answer..."):
        event_id = asyncio.run(send_rag_query_event(question.strip(), int(top_k)))
        output = wait_for_run_output(event_id)

    answer = output.get("answer", "")
    sources = output.get("sources", [])

    st.subheader("Answer")
    st.write(answer or "(No answer)")
    if sources:
        st.caption("Sources")
        for s in sources:
            st.write(f"- {s}")

    # Debug: raw output received from Inngest (remove once everything works)
    with st.expander("Debug"):
        st.write("Event ID:", event_id)
        st.json(output)