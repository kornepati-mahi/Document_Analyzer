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
from io import BytesIO

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


def split_text_into_chunks(text, chunk_size=3000, overlap=300):
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
    """Extract text from PDF with enhanced Unicode support."""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page_num, page in enumerate(pdf_reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    # Preserve Unicode characters during extraction
                    text += f"\n--- Page {page_num + 1} ---\n{page_text}\n"
            except Exception as e:
                st.warning(f"Error reading page {page_num + 1}: {str(e)}")
                continue
        
        if not text.strip():
            st.error("No text could be extracted from the PDF. The PDF might be password-protected or contain only images.")
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
    # Remove only control characters, but preserve Unicode text
    # Remove control characters but keep Unicode characters for non-Latin scripts
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def create_pdf_bytes(text, title="Bid Analysis Summary"):
    """Create a PDF with comprehensive Unicode support for all languages."""
    if not text:
        text = ""
    try:
        # Lazy import so the app still runs if reportlab isn't installed
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.units import inch
        from reportlab.lib import utils
