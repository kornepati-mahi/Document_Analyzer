import streamlit as st
import PyPDF2
import requests
import os
import re
import time
import json
from datetime import datetime
from io import BytesIO

# ======================== FIX 1: Headless fix for Streamlit Cloud ========================
os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"

# ======================== Load API Key ========================
from dotenv import load_dotenv
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    st.error("Please set GROQ_API_KEY in .env file or environment variables.")
    st.stop()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ======================== Page Config & Styling ========================
st.set_page_config(page_title="Bid Analyser Pro", page_icon="Tender", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .main-header {text-align: center; padding: 2rem 0; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                  color: white; border-radius: 12px; margin-bottom: 2rem;}
    .summary-card {background: white; padding: 2rem; border-radius: 15px; border-left: 6px solid #667eea;
                   box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin: 1.5rem 0;}
    .question-card {border-left: 5px solid #007bff;}
    .answer-card {border-left: 5px solid #28a745;}
    .error-card {background:#ffebee; border-left:4px solid #f44336; padding:1.5rem; border-radius:10px;}
    .stDeployButton, .stToolbar, footer, #MainMenu {display: none !important;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1>Bid Analyser Pro</h1><p>Extracts Tender Details • Q&A • Translate • Download PDF</p></div>', unsafe_allow_html=True)

# ======================== Helper Functions ========================
def extract_text_from_pdf(pdf_file):
    try:
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text += f"\n--- Page {i+1} ---\n{page_text}\n"
        return text if text.strip() else None
    except Exception as e:
        st.error(f"PDF reading error: {e}")
        return None

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def split_text_into_chunks(text, chunk_size=3000, overlap=300):
    if len(text) <= chunk_size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
        if start >= len(text):
            break
    return chunks

def ask_llm(prompt, context="", model="llama3-70b-8192", temperature=0.2):
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    messages = [{"role": "system", "content": "You are an expert in Indian government tenders. Always follow instructions exactly."}]
    if context:
        messages.append({"role": "user", "content": f"Document:\n{context}\n\nTask:\n{prompt}"})
    else:
        messages.append({"role": "user", "content": prompt})

    data = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": 2048}

    for _ in range(3):
        try:
            r = requests.post(GROQ_API_URL, headers=headers, json=data, timeout=60)
            if r.status_code == 429:
                time.sleep(5)
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except:
            time.sleep(2)
    return "Error: API call failed after retries."

def generate_summary(text_chunks):
    prompt = """Extract tender details in this exact JSON format. Use "Not mentioned" if info is missing.
Output ONLY valid JSON, no markdown, no extra text.

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
}"""

    summaries = []
    progress = st.progress(0)
    for i, chunk in enumerate(text_chunks):
        part = ask_llm(prompt, chunk, model="llama3-70b-8192")
        if part and "{" in part:
            summaries.append(part)
        progress.progress((i+1)/len(text_chunks))
        time.sleep(0.6)

    if not summaries:
        return None

    # Final merge
    final_prompt = "Merge all these JSONs into ONE perfect JSON. Keep best values. Use \\n- for bullets. Output ONLY JSON:"
    merged = ask_llm(final_prompt + "\n\n" + "\n---\n".join(summaries), model="llama3-70b-8192")
    return merged

def format_summary_display(raw_json):
    # Extract JSON even if wrapped in ```
    json_str = re.search(r"\{.*\}", raw_json, re.DOTALL)
    if json_str:
        json_str = json_str.group(0)
    else:
        json_str = raw_json

    try:
        data = json.loads(json_str)
    except:
        return f"<pre>{raw_json}</pre>"

    html = "<div class='summary-card'>"
    sections = {
        "Basic Information": data['basic_information']",
        "Financial Details": data['financial_details'],
        "Timeline": data['timeline'],
        "Requirements": data['requirements']
    }

    for title, items in sections.items():
        html += f"<h3>{title}</h3>"
        for key, val in items.items():
            title_key = key.replace("_", " ").title()
            if not val or val == "Not mentioned":
                val = "<em style='color:#888'>Not mentioned</em>"
            elif "\n" in val:
                lines = [f"• {line.strip('- ')}" for line in val.split('\n') if line.strip()]
                val = "<ul>" + "".join(f"<li>{line}</li>" for line in lines) + "</ul>"
            html += f"<p><strong>{title_key}:</strong> {val}</p>"
        html += "<hr>"
    return html + "</div>"

def create_pdf(text, title="Bid Summary"):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=50)
        styles = getSampleStyleSheet()
        story = [Paragraph(title, styles['Title']), Spacer(1, 20)]

        for para in text.split('\n\n'):
            if para.strip():
                story.append(Paragraph(para.replace('\n', '<br/>'), styles['Normal']))
                story.append(Spacer(1, 12))
        doc.build(story)
        return buffer.getvalue()
    except:
        return None

# ======================== Translation ========================
LANGUAGES = {
    "Hindi": "Hindi", "Tamil": "Tamil", "Telugu": "Telugu", "Kannada": "Kannada",
    "Malayalam": "Malayalam", "Marathi": "Marathi", "Gujarati": "Gujarati",
    "Punjabi (Gurmukhi)": "Punjabi", "Bengali": "Bengali", "Odia": "Odia",
    "Urdu": "Urdu", "English": "English", "Arabic": "Arabic"
}

def translate_text(text, lang):
    prompt = f"Translate this English text to {lang}. Keep formatting. Output only translation:"
    return ask_llm(prompt, text, model="llama3-70b-8192", temperature=0)

# ======================== Main App ========================
with st.sidebar:
    st.header("Controls")
    uploaded_file = st.file_uploader("Upload Tender PDF/TXT", type=["pdf", "txt"])

    if st.button("Clear All Data", use_container_width=True, type="secondary"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    if st.session_state.get("summary"):
        st.subheader("Translate Summary")
        lang = st.selectbox("Language", options=list(LANGUAGES.keys()))
        if st.button("Translate Now", type="primary", use_container_width=True):
            with st.spinner("Translating..."):
                translated = translate_text(st.session_state.summary, LANGUAGES[lang])
                st.session_state.translated = translated
                st.session_state.trans_lang = lang
                st.rerun()

# ======================== Process Upload ========================
if uploaded_file and "text_chunks" not in st.session_state:
    with st.spinner("Reading document..."):
        if uploaded_file.type == "application/pdf":
            raw = extract_text_from_pdf(uploaded_file)
        else:
            raw = uploaded_file.getvalue().decode("utf-8", errors="replace")

        if not raw or len(raw) < 100:
            st.error("Could not read document or it's empty.")
            st.stop()

        cleaned = clean_text(raw)
        st.session_state.text_chunks = split_text_into_chunks(cleaned)
        st.session_state.raw_text = cleaned

    with st.spinner("Analyzing tender with AI... (30-60 seconds)"):
        summary_json = generate_summary(st.session_state.text_chunks)
        if summary_json:
            st.session_state.summary = summary_json
            st.success("Analysis Complete!")
            st.rerun()
        else:
            st.error("Failed to analyze. Try again.")
            st.stop()

# ======================== Display Results ========================
if st.session_state.get("summary", None):
    st.subheader("Extracted Tender Summary")
    st.markdown(format_summary_display(st.session_state.summary), unsafe_allow_html=True)

    # Translation
    if st.session_state.get("translated"):
        st.subheader(f"Translated ({st.session_state.trans_lang})")
        st.markdown(f"<div class='summary-card'>{st.session_state.translated.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)

    # Downloads
    col1, col2 = st.columns(2)
    with col1:
        pdf = create_pdf(st.session_state.summary, "Tender Summary - English")
        if pdf:
            st.download_button("Download Summary PDF (English)", pdf, "tender_summary.pdf", "application/pdf")
    with col2:
        if st.session_state.get("translated"):
            pdf2 = create_pdf(st.session_state.translated, f"Tender Summary - {st.session_state.trans_lang}")
            if pdf2:
                st.download_button(f"Download PDF ({st.session_state.trans_lang})", pdf2, "tender_translated.pdf", "application/pdf")

    # Q&A
    st.subheader("Ask Anything About This Tender")
    question = st.text_input("Your question:", placeholder="e.g., What is the EMD amount?")
    if st.button("Ask", type="primary") and question:
        with st.spinner("Searching document..."):
            answer = ask_llm(question, st.session_state.raw_text, model="llama3-70b-8192")
            st.markdown(f"**Answer:** {answer}")

else:
    st.info("Upload a tender document (PDF/TXT) to begin analysis.")
    st.markdown("""
    ### Features
    - Extracts all key tender fields accurately  
    - Works with English, Hindi, Regional language PDFs  
    - Translate summary to 12+ Indian languages  
    - Download beautiful PDFs  
    - Ask questions in plain English
    """)

st.markdown("---")
st.caption("Bid Analyser Pro v3.0 • Powered by Groq Llama3-70B • Made with ❤️ for Indian Tenders")
