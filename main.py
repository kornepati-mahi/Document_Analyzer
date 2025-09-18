import streamlit as st
import PyPDF2
import requests
import os
from dotenv import load_dotenv
import re
import time
from datetime import datetime
import json
import streamlit.components.v1 as components

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Page configuration
st.set_page_config(
    page_title="Bid Analyser Pro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .stDeployButton, .stToolbar, div[data-testid="stStatusWidget"], .stActionButton, footer, #MainMenu {
        display: none !important;
    }
    .main-header {
        text-align: center; padding: 2rem 0; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white; border-radius: 10px; margin-bottom: 2rem;
    }
    .summary-card {
        background: #ffffff; padding: 2rem; border-radius: 15px; border-left: 5px solid #667eea;
        margin: 1.5rem 0; box-shadow: 0 4px 6px rgba(0,0,0,0.1); font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .summary-card h4 {
        color: #333; margin: 1rem 0 0.5rem 0; font-size: 1.1rem; font-weight: 600;
    }
    .summary-card p, .summary-card li {
        color: #555; line-height: 1.6; margin-bottom: 0.5rem;
    }
    .summary-card ul {
        padding-left: 1.5rem; margin-bottom: 1rem;
    }
    .question-card, .answer-card {
        background: #ffffff; padding: 2rem; border-radius: 15px; margin: 1.5rem 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .question-card { border-left: 5px solid #007bff; }
    .answer-card { border-left: 5px solid #28a745; }
    .question-card h4 { color: #007bff; }
    .answer-card h4 { color: #28a745; }
    .question-card p, .answer-card p { color: #333; line-height: 1.6; }
    .upload-section {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 2rem;
        border-radius: 10px; text-align: center; margin: 1rem 0; color: white;
    }
    .error-card {
        background: #ffebee; padding: 1.5rem; border-radius: 10px;
        border-left: 4px solid #f44336; margin: 1rem 0; border: 1px solid #ffcdd2;
    }
</style>
""", unsafe_allow_html=True)


def split_text_into_chunks(text, chunk_size=2200, overlap=250):
    if not text or len(text.strip()) == 0:
        return []
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        start += chunk_size - overlap
    return chunks

def extract_text_from_pdf(pdf_file):
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page_num, page in enumerate(pdf_reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text += f"\n--- Page {page_num + 1} ---\n{page_text}\n"
            except Exception as e:
                st.warning(f"Error reading page {page_num + 1}: {str(e)}")
                continue
        if not text.strip():
            # Fallback: try pdfminer.six if available
            try:
                from io import BytesIO
                from pdfminer.high_level import extract_text as pdfminer_extract
                if hasattr(pdf_file, 'getvalue'):
                    pdf_bytes = pdf_file.getvalue()
                else:
                    pdf_bytes = pdf_file.read()
                text = pdfminer_extract(BytesIO(pdf_bytes)) or ""
            except Exception as _:
                st.error("No text could be extracted from the PDF. The PDF might be password-protected or contain only scanned images.")
                return None
        return text
    except Exception as e:
        st.error(f"Error reading PDF file: {str(e)}")
        return None

def format_summary_for_display(summary_text):
    if not summary_text or summary_text.startswith("Error"):
        return summary_text
    
    content_start_index = summary_text.find('**')
    if content_start_index != -1:
        summary_text = summary_text[content_start_index:]
    else:
        lines = summary_text.splitlines()
        for i, line in enumerate(lines):
            if "information" in line.lower() or "details" in line.lower():
                summary_text = "\n".join(lines[i+1:])
                break

    formatted = re.sub(r'\*\*(.*?)\*\*', r'<h4>\1</h4>', summary_text)
    lines = formatted.split('\n')
    formatted_lines = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            continue
            
        if line.startswith(('* ', '- ', '• ')):
            if not in_list:
                formatted_lines.append('<ul>')
                in_list = True
            
            if line.startswith('* '): line = line[2:]
            elif line.startswith('- '): line = line[2:]
            elif line.startswith('• '): line = line[2:]
            
            formatted_lines.append(f'<li>{line.strip()}</li>')
        else:
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            
            if ':' in line and not line.startswith('<h4>'):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    if value and value.lower() not in ["not mentioned", "not found", "not specified"]:
                        formatted_lines.append(f'<p><strong>{key}:</strong> {value}</p>')
                    else:
                        formatted_lines.append(f'<p><strong>{key}:</strong> <em>Not specified</em></p>')
                else:
                    formatted_lines.append(f'<p>{line}</p>')
            else:
                formatted_lines.append(f'<p>{line}</p>')
    
    if in_list:
        formatted_lines.append('</ul>')
    
    return ''.join(formatted_lines)


def format_answer_for_display(answer_text):
    if not answer_text or answer_text.startswith("Error"):
        return answer_text
    formatted = answer_text.strip()
    paragraphs = [p.strip() for p in formatted.split('\n') if p.strip()]
    return '<br><br>'.join(paragraphs)

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    return text.strip()

def ask_llm(question, context, max_retries=3):
    if not GROQ_API_KEY:
        return "Error: GROQ_API_KEY not found in environment variables."
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}

    # Build messages allowing optional context. Some callers (e.g., consolidation) may
    # send an instruction-only prompt without separate context.
    if context and context.strip():
        user_content = f"Document Content:\n{context}\n\nQuestion: {question}\n\nPlease provide a detailed and structured response based on the document content."
    else:
        user_content = question

    messages = [
        {"role": "system", "content": "You are an expert document analyst specializing in bid and tender documents. Provide clear, accurate, and structured responses. If information is not found, clearly state that."},
        {"role": "user", "content": user_content}
    ]

    data = {"model": ""llama-3.1-8b-instant", "messages": messages, "temperature": 0.3, "max_tokens": 1000}
    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.post(GROQ_API_URL, headers=headers, json=data, timeout=45)
            response.raise_for_status()
            response_data = response.json()
            if 'choices' in response_data and len(response_data['choices']) > 0:
                return response_data["choices"][0]["message"]["content"]
            else:
                return "Error: Invalid response format from API."
        except requests.exceptions.HTTPError as e:
            last_error = f"HTTP Error {response.status_code}: {str(e)}"
            if response.status_code == 429:
                time.sleep(min(2 ** attempt, 10))
                continue
            elif response.status_code == 401:
                return "Error: Invalid API key. Please check your GROQ_API_KEY."
            else:
                time.sleep(1)
                continue
        except Exception as e:
            last_error = f"Unexpected Error: {str(e)}"
            time.sleep(1)
            continue
    return f"Error after {max_retries} attempts: {last_error}"

def translate_text_with_llm(text_to_translate, target_language):
    if not GROQ_API_KEY:
        return "Error: GROQ_API_KEY not found. Cannot translate."
    prompt = f"""Translate the following English text to {target_language}. Provide ONLY the translated text, without any introductory phrases, explanations, or quotation marks. Text to translate:\n---\n{text_to_translate}\n---"""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    messages = [
        {"role": "system", "content": f"You are an expert translator. Your task is to translate English text into {target_language} accurately."},
        {"role": "user", "content": prompt}
    ]
    data = {"model": "llama3-8b-8192", "messages": messages, "temperature": 0.1, "max_tokens": 2000}
    try:
        response = requests.post(GROQ_API_URL, headers=headers, json=data, timeout=45)
        response.raise_for_status()
        response_data = response.json()
        if 'choices' in response_data and len(response_data['choices']) > 0:
            return response_data["choices"][0]["message"]["content"]
        else:
            return "Error: Could not get a valid translation from the API."
    except Exception as e:
        return f"Error during translation API call: {str(e)}"

def generate_comprehensive_summary(text_chunks):
    if not text_chunks:
        return "No content available for summarization."
    summary_prompt = """Analyze this bid/tender document and extract the following key information. If any information is not found, clearly state "Not mentioned" or "Not found":\n\n**BASIC INFORMATION:**\n- Tender Number/Reference:\n- Name of Work/Project:\n- Issuing Department/Organization:\n\n**FINANCIAL DETAILS:**\n- Estimated Contract Value:\n- EMD (Earnest Money Deposit):\n- EMD Exemption (if any):\n- Performance Security:\n\n**TIMELINE:**\n- Bid Submission Deadline:\n- Technical Bid Opening:\n- Contract Duration:\n\n**REQUIREMENTS:**\n- Key Eligibility Criteria:\n- Required Documents:\n- Technical Specifications (brief):\n- Payment Terms:\n\nProvide only the information that is clearly mentioned in the document."""
    all_summaries = []
    # If API key is missing, skip directly to heuristic summary
    if not GROQ_API_KEY:
        try:
            combined_text = "\n\n".join(text_chunks[:3])
            return heuristic_summary_from_text(combined_text)
        except Exception:
            return "Unable to generate summary due to processing errors."

    max_chunks = min(len(text_chunks), 6)
    with st.spinner("Analyzing document sections..."):
        progress_bar = st.progress(0)
        for i, chunk in enumerate(text_chunks[:max_chunks]):
            try:
                summary = ask_llm(summary_prompt, chunk)
                if not summary.startswith("Error"):
                    all_summaries.append(summary)
                progress_bar.progress((i + 1) / max_chunks)
                time.sleep(0.2)
            except Exception as e:
                st.warning(f"Error processing chunk {i+1}: {str(e)}")
                continue
    # Fallback: if all chunked requests failed, try a single-pass summary on the first
    # one or two chunks combined, so users still get a result.
    if not all_summaries:
        try:
            fallback_context = "\n\n".join(text_chunks[:2])
            fallback = ask_llm(summary_prompt, fallback_context)
            if not fallback.startswith("Error") and len(fallback.strip()) > 0:
                all_summaries.append(fallback)
        except Exception:
            pass
        # If still nothing, perform a lightweight heuristic extraction as a final safeguard
        if not all_summaries:
            try:
                combined_text = "\n\n".join(text_chunks[:3])
                heuristic_summary = heuristic_summary_from_text(combined_text)
                if heuristic_summary and len(heuristic_summary.strip()) > 0:
                    return heuristic_summary
            except Exception:
                pass
            return "Unable to generate summary due to processing errors."
    final_summary_prompt = f"""Based on the following analysis sections from the same document, create a single comprehensive summary by combining and deduplicating the information:\n\n{chr(10).join([f"Section {i+1}:\n{summary}\n" for i, summary in enumerate(all_summaries)])}\n\nProvide a final consolidated summary with the same structure, keeping only the most complete and accurate information for each field."""
    try:
        # Consolidation uses the instruction-only prompt without separate context.
        final_summary = ask_llm(final_summary_prompt, "")
        return final_summary if not final_summary.startswith("Error") else all_summaries[0]
    except:
        return all_summaries[0] if all_summaries else "Summary generation failed."

# ---------------- Heuristic (non-LLM) fallback summarizer ---------------- #
def _find_first(patterns, text, flags=re.IGNORECASE):
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            # Prefer the last captured group if any
            if match.groups():
                return next((g for g in match.groups() if g), match.group(0))
            return match.group(0)
    return None

def heuristic_summary_from_text(text):
    if not text:
        return "Unable to generate summary due to processing errors."
    snippet = text[:120000]

    # Currency/amount patterns
    amount_patterns = [
        r"(?:INR|Rs\.?|₹)\s?([\d,]+\.?\d*\s?(?:lakh|crore)?)",
        r"([\d,]+\.?\d*\s?(?:INR|Rs\.?|₹))",
        r"([\d,]+\.?\d*\s?(?:lakhs?|crores?))",
    ]

    # Date patterns
    date_patterns = [
        r"(\b\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4}\b)",
        r"(\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4}\b)",
        r"(\b\d{4}-\d{2}-\d{2}\b)",
    ]

    # Simple field extraction heuristics
    tender_no = _find_first([r"Tender\s*(?:No\.?|Number)\s*[:\-]\s*([^\n]+)", r"RFP\s*No\.?\s*[:\-]\s*([^\n]+)"], snippet)
    project_name = _find_first([r"Name of Work\s*[:\-]\s*([^\n]+)", r"Name of Project\s*[:\-]\s*([^\n]+)", r"Project\s*[:\-]\s*([^\n]+)"], snippet)
    org = _find_first([r"(?:Issuer|Issuing|Department|Organization|Authority)\s*[:\-]\s*([^\n]+)", r"Government of[^\n]+"], snippet)

    contract_value = _find_first([r"Estimated\s*(?:Cost|Contract Value)\s*[:\-]\s*([^\n]+)"] + amount_patterns, snippet)
    emd = _find_first([r"EMD\s*(?:Amount)?\s*[:\-]\s*([^\n]+)"] + amount_patterns, snippet)
    perf_sec = _find_first([r"Performance\s*Security\s*[:\-]\s*([^\n]+)"] + amount_patterns, snippet)

    # Deadlines/opening dates
    submission_deadline = _find_first([r"Bid Submission.*?[:\-]\s*([^\n]+)", r"Last Date.*?Submission.*?[:\-]\s*([^\n]+)"] + date_patterns, snippet)
    tech_opening = _find_first([r"Technical Bid Opening.*?[:\-]\s*([^\n]+)"] + date_patterns, snippet)
    duration = _find_first([r"Contract Duration\s*[:\-]\s*([^\n]+)", r"Completion Period\s*[:\-]\s*([^\n]+)"], snippet)

    # Eligibility / documents (extract short lines near keywords)
    def _collect_bullets(keyword):
        lines = []
        for m in re.finditer(rf"{keyword}[^\n]*\n((?:.*\n){0,8})", snippet, re.IGNORECASE):
            block = m.group(1)
            for ln in block.splitlines():
                if re.search(r"^\s*(?:[-*•]\s+|\d+\)\s+).{3,}", ln):
                    lines.append(re.sub(r"^\s*(?:[-*•]|\d+\))\s+", "", ln).strip())
        return list(dict.fromkeys(lines))[:6]

    eligibility = _collect_bullets("Eligibility|Qualif")
    req_docs = _collect_bullets("Document|Submission of|Upload the following")
    specs = _collect_bullets("Specification|Scope of Work|Technical")
    pay_terms = _collect_bullets("Payment Terms|Payment Schedule")

    def _fmt(value):
        return value if value else "Not mentioned"

    parts = []
    parts.append("**BASIC INFORMATION:**")
    parts.append(f"- Tender Number/Reference: {_fmt(tender_no)}")
    parts.append(f"- Name of Work/Project: {_fmt(project_name)}")
    parts.append(f"- Issuing Department/Organization: {_fmt(org)}")
    parts.append("")
    parts.append("**FINANCIAL DETAILS:**")
    parts.append(f"- Estimated Contract Value: {_fmt(contract_value)}")
    parts.append(f"- EMD (Earnest Money Deposit): {_fmt(emd)}")
    parts.append(f"- EMD Exemption (if any): Not mentioned")
    parts.append(f"- Performance Security: {_fmt(perf_sec)}")
    parts.append("")
    parts.append("**TIMELINE:**")
    parts.append(f"- Bid Submission Deadline: {_fmt(submission_deadline)}")
    parts.append(f"- Technical Bid Opening: {_fmt(tech_opening)}")
    parts.append(f"- Contract Duration: {_fmt(duration)}")
    parts.append("")
    parts.append("**REQUIREMENTS:**")
    parts.append("- Key Eligibility Criteria:")
    parts += [f"  - {item}" for item in (eligibility or ["Not mentioned"])[:6]]
    parts.append("- Required Documents:")
    parts += [f"  - {item}" for item in (req_docs or ["Not mentioned"])[:6]]
    parts.append("- Technical Specifications (brief):")
    parts += [f"  - {item}" for item in (specs or ["Not mentioned"])[:6]]
    parts.append(f"- Payment Terms: {_fmt('; '.join(pay_terms) if pay_terms else None)}")

    return "\n".join(parts)

def answer_question_from_chunks(question, text_chunks):
    if not text_chunks:
        return "No document content available to answer the question."
    relevant_answers = []
    with st.spinner("Searching through document..."):
        progress_bar = st.progress(0)
        for i, chunk in enumerate(text_chunks):
            try:
                answer = ask_llm(question, chunk)
                if (not answer.startswith("Error") and "not found" not in answer.lower() and "not mentioned" not in answer.lower() and len(answer.strip()) > 20):
                    relevant_answers.append(answer)
                progress_bar.progress((i + 1) / len(text_chunks))
                time.sleep(1.2)
            except Exception as e:
                st.warning(f"Error processing chunk {i+1}: {str(e)}")
                continue
    if not relevant_answers:
        return "No relevant information found in the document to answer your question."
    if len(relevant_answers) == 1:
        return relevant_answers[0]
    combined_prompt = f"Question: {question}\n\nMultiple relevant sections found:\n{chr(10).join([f'Section {i+1}: {answer}' for i, answer in enumerate(relevant_answers)])}\n\nProvide a comprehensive answer by combining the relevant information from all sections, removing duplicates and contradictions."
    try:
        final_answer = ask_llm(combined_prompt, "")
        return final_answer if not final_answer.startswith("Error") else relevant_answers[0]
    except:
        return relevant_answers[0]

def main():
    if 'qa_history' not in st.session_state:
        st.session_state.qa_history = []
    
    st.markdown("""<div class="main-header"><h1>📊 Bid Analyser Pro</h1><p>Advanced Document Analysis & Q&A System</p></div>""", unsafe_allow_html=True)

    with st.sidebar:
        st.header("🔧 Controls")
        
        st.subheader("📁 Upload Document")
        uploaded_file = st.file_uploader("Choose a PDF or TXT file", type=["pdf", "txt"], help="Upload your bid document for analysis")
        
        st.subheader("⚡ Quick Actions")
        if st.button("🔄 Clear Analysis", use_container_width=True):
            keys_to_clear = ["summary", "cleaned_text", "text_chunks", "user_question", "answer", "last_uploaded_file", "qa_history", "translated_text", "translated_lang"]
            for key in keys_to_clear:
                st.session_state.pop(key, None)
            st.rerun()

        # --- NEW DROPDOWN TRANSLATION WIDGET ---
        if "summary" in st.session_state and st.session_state.summary and not st.session_state.summary.startswith("Error"):
            st.subheader("🗣️ Translate Summary")

            # --- MODIFIED: EXPANDED DICTIONARY OF LANGUAGES ---
            LANGUAGES = {
                # Indian Languages
                "Assamese": "Assamese",
                "Bengali": "Bengali",
                "Bodo": "Bodo",
                "Dogri": "Dogri",
                "Hindi": "Hindi",
                "Kashmiri": "Kashmiri",
                "Konkani": "Konkani",
                "Maithili": "Maithili",
                "Manipuri": "Manipuri",
                "Nepali": "Nepali",
                "Odia": "odia",
                "Sanskrit": "Sanskrit",
                "Santali": "Santali",
                "Sindhi": "Sindhi",
                "Urdu": "urdu",
                "Bengali": "Bengali",
                "Telugu": "Telugu",
                "Marathi": "Marathi",
                "Tamil": "Tamil",
                "Kannada": "Kannada",
                "Malayalam": "Malayalam",
                "Punjabi": "Punjabi",
                "Gujarati": "Gujarati",
                # World Languages
                "English": "English",
                "Turkish": "Turkish",
                "Italian": "Italian",
                "Korean": "Korean",
                "Turkish": "Turkish",
                "Spanish": "Spanish",
                "French": "French",
                "German": "German",
                "Mandarin Chinese": "Mandarin Chinese",
                "Japanese": "Japanese",
                "Russian": "Russian",
                "Arabic": "Arabic",
                "Portuguese": "Portuguese",
                "Dutch": "Dutch",
                "Polish": "Polish",
                "Swedish": "Swedish",
                "Greek": "Greek",
                "Hebrew": "Hebrew",
                "Vietnamese": "Vietnamese",
                "Thai": "Thai",
                "Indonesian": "Indonesian",
                "Ukrainian": "Ukrainian",
                "Romanian": "Romanian",
                "Czech": "Czech",
                "Hungarian": "Hungarian",
                "Finnish": "Finnish", 
            }

            selected_language = st.selectbox(
                "Select a language:",
                options=list(LANGUAGES.keys())
            )

            if st.button("Translate", use_container_width=True, type="primary"):
                if selected_language:
                    with st.spinner(f"Translating to {selected_language}..."):
                        formal_language_name = LANGUAGES[selected_language]
                        translated_text = translate_text_with_llm(st.session_state.summary, formal_language_name)
                        st.session_state.translated_text = translated_text
                        st.session_state.translated_lang = selected_language
                        st.rerun()
        # --- END OF NEW WIDGET ---
            
        st.subheader("💡 Sample Questions")
        sample_questions = ["What is the tender deadline?", "What are the eligibility criteria?", "What is the contract value?"]
        for question in sample_questions:
            if st.button(question, use_container_width=True):
                st.session_state.user_question = question

    # Main content area
    uploaded_filename = uploaded_file.name if uploaded_file else None
    if st.session_state.get("last_uploaded_file") != uploaded_filename:
        st.session_state["last_uploaded_file"] = uploaded_filename
        keys_to_clear = ["summary", "cleaned_text", "text_chunks", "user_question", "answer", "translated_text", "translated_lang"]
        for key in keys_to_clear:
            st.session_state.pop(key, None)

    if not uploaded_file:
        st.markdown("""<div class="upload-section"><h2>📤 Upload Your Bid Document</h2><p>Drag and drop a PDF or TXT file to get started with the analysis</p><p><em>Supported formats: PDF, TXT • Max size: 200MB</em></p></div>""", unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1: st.markdown("### 🎯 Key Information Extraction\n- Tender Number & Details\n- Contract Value & EMD")
        with col2: st.markdown("### 🤖 AI-Powered Analysis\n- Intelligent Q&A System\n- Document Summarization")
        with col3: st.markdown("### 📊 Advanced Features\n- Error Handling & Retries\n- Progress Tracking")

    if uploaded_file and "cleaned_text" not in st.session_state:
        with st.spinner("🔄 Processing document..."):
            progress_bar = st.progress(0)
            try:
                if uploaded_file.type == "application/pdf":
                    raw_text = extract_text_from_pdf(uploaded_file)
                else:
                    raw_text = uploaded_file.getvalue().decode("utf-8", errors='replace')
                progress_bar.progress(25)
                
                if not raw_text: st.stop()

                cleaned_text = clean_text(raw_text)
                progress_bar.progress(50)
                
                if not cleaned_text or len(cleaned_text.strip()) < 100:
                    st.error("Document appears to be empty or too short for analysis."); st.stop()
                st.session_state.cleaned_text = cleaned_text
                
                text_chunks = split_text_into_chunks(cleaned_text)
                progress_bar.progress(75)
                
                if not text_chunks:
                    st.error("Unable to process document into analyzable chunks."); st.stop()
                st.session_state.text_chunks = text_chunks
                
                summary = generate_comprehensive_summary(text_chunks)
                st.session_state.summary = summary
                progress_bar.progress(100)
            except Exception as e:
                st.error(f"Error processing document: {str(e)}"); st.stop()
        
        st.success("✅ Document processed successfully!")
        st.rerun()

    if "cleaned_text" in st.session_state:
        st.subheader("📋 Document Analysis Summary")
        if st.session_state.summary.startswith("Error"):
            # Attempt heuristic summary immediately so users still get output
            heuristic = None
            try:
                heuristic = heuristic_summary_from_text(st.session_state.get("cleaned_text", ""))
            except Exception:
                heuristic = None
            if heuristic:
                formatted_summary = format_summary_for_display(heuristic)
                st.markdown(f'<div class="summary-card">{formatted_summary}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="error-card"><h4>⚠️ Summary Generation Error:</h4><p>{st.session_state.summary}</p></div>', unsafe_allow_html=True)
        else:
            formatted_summary = format_summary_for_display(st.session_state.summary)
            st.markdown(f'<div class="summary-card">{formatted_summary}</div>', unsafe_allow_html=True)

        if "translated_text" in st.session_state:
            st.subheader(f"✅ Translated Summary ({st.session_state.translated_lang})")
            st.markdown(f"""<style>.translated-card {{ border-left: 5px solid #28a745; }}</style><div class="summary-card translated-card"><p>{st.session_state.translated_text.replace(chr(10), '<br>')}</p></div>""", unsafe_allow_html=True)
        
        st.subheader("⬇️ Download Summaries")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 Download Original (English)",
                data=st.session_state.summary,
                file_name=f"bid_analysis_english_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )
        with col2:
            if "translated_text" in st.session_state and st.session_state.translated_text:
                st.download_button(
                    label=f"📥 Download Translated ({st.session_state.translated_lang})",
                    data=st.session_state.translated_text,
                    file_name=f"bid_analysis_{st.session_state.translated_lang.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
            else:
                # Offer raw extracted text download for debugging/backup
                st.download_button(
                    label="📥 Download Raw Extracted Text",
                    data=st.session_state.get("cleaned_text", ""),
                    file_name=f"raw_text_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
        
        st.subheader("🔍 Ask Questions About the Document")
        col1, col2 = st.columns([4, 1])
        user_question = col1.text_input("Type your question here:", value=st.session_state.get("user_question", ""), placeholder="e.g., What is the tender submission deadline?", key="question_input")
        ask_button = col2.button("🔍 Ask", use_container_width=True, type="primary")

        if (ask_button and user_question) or (user_question and user_question != st.session_state.get("last_question", "")):
            st.session_state.last_question = user_question
            if user_question.strip():
                answer = answer_question_from_chunks(user_question, st.session_state.get("text_chunks", []))
                st.session_state.qa_history.append((user_question, answer))
                st.markdown(f'<div class="question-card"><h4>Your Question:</h4><p>{user_question}</p></div>', unsafe_allow_html=True)
                if answer.startswith("Error"):
                    st.markdown(f'<div class="error-card"><h4>⚠️ Error:</h4><p>{answer}</p></div>', unsafe_allow_html=True)
                else:
                    formatted_answer = format_answer_for_display(answer)
                    st.markdown(f'<div class="answer-card"><h4>💡 Answer:</h4><p>{formatted_answer}</p></div>', unsafe_allow_html=True)

        if st.session_state.qa_history:
            with st.expander(f"📚 Q&A History ({len(st.session_state.qa_history)} questions)"):
                for i, (q, a) in enumerate(reversed(st.session_state.qa_history[-10:])):
                    st.markdown(f"**Q{len(st.session_state.qa_history)-i}:** {q}")
                    if a.startswith("Error"): st.error(f"**A:** {a}")
                    else: st.markdown(f"**A:** {a}")
                    st.markdown("---")

    st.markdown("---")
    st.markdown("""<div style="text-align: center; padding: 2rem; color: #666;"><p>🚀 Bid Analyser Pro v2.0</p></div>""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()

