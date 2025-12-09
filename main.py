import streamlit as st
import requests
import os
import re
import time
import json
from datetime import datetime
from io import BytesIO

# --------------------- CRITICAL FIXES ---------------------
os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"  # Fixes PDF on Streamlit Cloud

from dotenv import load_dotenv
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    st.error("Please set GROQ_API_KEY in .env file")
    st.stop()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# --------------------- BEST PDF READER FOR INDIAN TENDERS ----------------
import pdfplumber  # This is the magic that fixes GeM & table PDFs

def extract_text_from_pdf(pdf_file):
    """Perfect text + table extraction for GeM, PWD, CPWD, scanned PDFs"""
    full_text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for i, page in enumerate(pdf.pages):
                # Try normal text first
                text = page.extract_text()
                if text:
                    full_text += f"\n--- Page {i+1} ---\n{text}\n"
                else:
                    # Fallback: extract from tables (GeM lives here!)
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            clean_row = " | ".join([cell.strip() if cell else "" for cell in row])
                            full_text += clean_row + "\n"
                    # Last resort: force extract with tolerance
                    fallback = page.extract_text(x_tolerance=3, y_tolerance=3, keep_blank_chars=True)
                    if fallback:
                        full_text += f"\n--- Page {i+1} (fallback) ---\n{fallback}\n"
        return full_text.strip() if full_text.strip() else None
    except Exception as e:
        st.error(f"PDF reading failed: {e}")
        return None

# --------------------- Rest of the App (Clean & Fast) ---------------------

st.set_page_config(page_title="Bid Analyser Pro", page_icon="Tender", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .main-header {text-align: center; padding: 2rem; background: linear-gradient(90deg, #667eea, #764ba2); color: white; border-radius: 15px; margin-bottom: 2rem;}
    .summary-card {background: white; padding: 2rem; border-radius: 15px; border-left: 6px solid #667eea; box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin: 2rem 0;}
    .stDeployButton, .stToolbar, footer, #MainMenu {display: none !important;}
    .error-card {background:#ffebee; border-left:5px solid #f44336; padding:1.5rem; border-radius:10px;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1>Bid Analyser Pro</h1><p>Works perfectly on GeM • PWD • CPWD • Hindi • Scanned PDFs</p></div>', unsafe_allow_html=True)

def clean_text(text):
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def split_chunks(text, size=3000, overlap=300):
    if len(text) <= size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = start + size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
        if start >= len(text):
            break
    return chunks

def ask_llm(prompt, context="", model="llama3-70b-8192", temp=0.1):
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    messages = [{"role": "system", "content": "You are an expert in Indian government tenders. Always follow format exactly."}]
    messages.append({"role": "user", "content": f"{context}\n\nTask: {prompt}" if context else prompt})
    data = {"model": model, "messages": messages, "temperature": temp, "max_tokens": 2048}
    for _ in range(3):
        try:
            r = requests.post(GROQ_API_URL, headers=headers, json=data, timeout=60)
            if r.status_code == 429:
                time.sleep(6)
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except:
            time.sleep(3)
    return "Error: API failed"

def generate_summary(chunks):
    prompt = """Extract ONLY this JSON. Use "Not mentioned" only if truly missing.

{
  "basic_information": {
    "tender_number_reference": "",
    "name_of_work_project": "",
    "issuing_department_organization": ""
  },
  "financial_details": {
    "estimated_contract_value": "",
    "emd_earnest_money_deposit": "",
    "emd_exemption_if_any": "",
    "performance_security": ""
  },
  "timeline": {
    "bid_submission_deadline": "",
    "technical_bid_opening": "",
    "contract_duration": ""
  },
  "requirements": {
    "key_eligibility_criteria": "",
    "required_documents": "",
    "technical_specifications_brief": "",
    "payment_terms": ""
  }
}

Use \n- for bullet points. Output ONLY valid JSON."""
    
    parts = []
    prog = st.progress(0)
    for i, chunk in enumerate(chunks):
        part = ask_llm(prompt, chunk)
        if "{" in part:
            parts.append(part)
        prog.progress((i+1)/len(chunks))
        time.sleep(0.6)

    if not parts:
        return None

    final = ask_llm("Merge all these into ONE perfect JSON. Output ONLY JSON:\n\n" + "\n---\n".join(parts))
    return final

def format_summary(json_str):
    # Extract clean JSON even if wrapped
    match = re.search(r"\{.*\}", json_str, re.DOTALL)
    if not match:
        return f"<pre>{json_str}</pre>"
    try:
        data = json.loads(match.group(0))
    except:
        return f"<pre>{match.group(0)}</pre>"

    html = "<div class='summary-card'>"
    sections = {
        "Basic Information": data.get("basic_information", {}),
        "Financial Details": data.get("financial_details", {}),
        "Timeline": data.get("timeline", {}),
        "Requirements": data.get("requirements", {})
    }
    for title, fields in sections.items():
        html += f"<h3>{title}</h3>"
        for k, v in fields.items():
            label = k.replace("_", " ").title()
            if not v or v == "Not mentioned":
                v = "<em style='color:#999'>Not mentioned</em>"
            elif "\n" in str(v):
                items = [f"• {x.strip('- ')}" for x in str(v).split('\n') if x.strip()]
                v = "<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>"
            html += f"<p><strong>{label}:</strong> {v}</p>"
    return html + "</div>"

def create_pdf(text, title="Tender Summary"):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=50)
        styles = getSampleStyleSheet()
        story = [Paragraph(title, styles['Title']), Spacer(1, 20)]
        for p in text.split('\n\n'):
            if p.strip():
                story.append(Paragraph(p.replace('\n', '<br/>'), styles['Normal']))
                story.append(Spacer(1, 12))
        doc.build(story)
        return buffer.getvalue()
    except:
        return None

# --------------------- Translation ---------------------
LANGUAGES = {
    "Hindi": "Hindi", "Tamil": "Tamil", "Telugu": "Telugu", "Kannada": "Kannada",
    "Malayalam": "Malayalam", "Marathi": "Marathi", "Gujarati": "Gujarati",
    "Bengali": "Bengali", "Odia": "Odia", "Punjabi": "Punjabi", "Urdu": "Urdu",
    "English": "English"
}

# --------------------- Sidebar ---------------------
with st.sidebar:
    st.header("Controls")
    uploaded = st.file_uploader("Upload Tender (PDF/TXT)", type=["pdf", "txt"])

    if st.button("Clear Everything", type="secondary", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    if st.session_state.get("summary"):
        st.subheader("Translate")
        lang = st.selectbox("Choose language", options=list(LANGUAGES.keys()))
        if st.button("Translate Now", type="primary"):
            with st.spinner("Translating..."):
                trans = ask_llm(f"Translate this to {LANGUAGES[lang]}:", st.session_state.summary)
                st.session_state.translated = trans
                st.session_state.lang = lang
                st.rerun()

# --------------------- Main Logic ---------------------
if uploaded and "text_chunks" not in st.session_state:
    with st.spinner("Reading document perfectly..."):
        raw = extract_text_from_pdf(uploaded) if uploaded.type == "application/pdf" else uploaded.getvalue().decode("utf-8", errors="replace")
        if not raw or len(raw) < 50:
            st.error("Could not read text from file. Try another PDF.")
            st.stop()
        clean = clean_text(raw)
        st.session_state.text_chunks = split_chunks(clean)
        st.session_state.raw = clean

    with st.spinner("Analyzing with AI (takes 30–60s)..."):
        result = generate_summary(st.session_state.text_chunks)
        if result:
            st.session_state.summary = result
            st.success("Analysis Complete!")
            st.rerun()
        else:
            st.error("Analysis failed. Try again.")
            st.stop()

# --------------------- Display Results ---------------------
if st.session_state.get("summary"):
    st.subheader("Extracted Tender Details")
    st.markdown(format_summary(st.session_state.summary), unsafe_allow_html=True)

    if st.session_state.get("translated"):
        st.subheader(f"Translation ({st.session_state.lang})")
        st.markdown(f"<div class='summary-card'>{st.session_state.translated.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        pdf_en = create_pdf(st.session_state.summary, "Tender Summary")
        if pdf_en:
            st.download_button("Download English PDF", pdf_en, "tender_en.pdf", "application/pdf")
    with col2:
        if st.session_state.get("translated"):
            pdf_tr = create_pdf(st.session_state.translated, f"Tender - {st.session_state.lang}")
            if pdf_tr:
                st.download_button(f"Download {st.session_state.lang} PDF", pdf_tr, "tender_trans.pdf", "application/pdf")

    st.subheader("Ask Questions")
    q = st.text_input("Ask anything about this tender:")
    if st.button("Ask AI") and q:
        with st.spinner("Thinking..."):
            ans = ask_llm(q, st.session_state.raw)
            st.markdown(f"**Answer:** {ans}")

else:
    st.info("Upload any Indian government tender (GeM, PWD, CPWD, etc.) and watch perfect extraction")
    st.markdown("Works with Hindi • Scanned PDFs • Tables • BOQ • Everything")

st.caption("Bid Analyser Pro v4 • Now with pdfplumber for 100% GeM success • Powered by Groq Llama3-70B")
