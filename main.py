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
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os
        import platform
        # Optional imports for Arabic/Urdu shaping
        try:
            import arabic_reshaper as _arabic_reshaper
            from bidi.algorithm import get_display as _bidi_get_display
        except Exception:
            _arabic_reshaper = None
            _bidi_get_display = None

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        
        # Comprehensive font registration for maximum language support
        unicode_fonts = []
        system = platform.system()
        
        # Extended font paths for comprehensive Unicode support
        font_candidates = {
            "Windows": [
                # Primary Unicode fonts
                ("NotoSans", "C:/Windows/Fonts/NotoSans-Regular.ttf"),
                ("ArialUnicode", "C:/Windows/Fonts/ARIALUNI.TTF"),
                ("Nirmala", "C:/Windows/Fonts/Nirmala.ttf"),
                ("NirmalaUI", "C:/Windows/Fonts/NirmalaUI.ttf"),
                ("Arial", "C:/Windows/Fonts/arial.ttf"),
                ("Calibri", "C:/Windows/Fonts/calibri.ttf"),
                ("Tahoma", "C:/Windows/Fonts/tahoma.ttf"),
                ("Segoe", "C:/Windows/Fonts/segoeui.ttf"),
                ("Verdana", "C:/Windows/Fonts/verdana.ttf"),
                # CJK and Asian language fonts
                ("MingLiU", "C:/Windows/Fonts/mingliu.ttc"),
                ("SimSun", "C:/Windows/Fonts/simsun.ttc"),
                ("SimHei", "C:/Windows/Fonts/simhei.ttf"),
                ("MicrosoftYaHei", "C:/Windows/Fonts/msyh.ttc"),
                ("Malgun", "C:/Windows/Fonts/malgun.ttf"),
                ("Meiryo", "C:/Windows/Fonts/meiryo.ttc"),
                ("MSJhengHei", "C:/Windows/Fonts/msjh.ttc"),
                ("Gulim", "C:/Windows/Fonts/gulim.ttc"),
                ("Batang", "C:/Windows/Fonts/batang.ttc"),
                # Indian language fonts
                ("Mangal", "C:/Windows/Fonts/mangal.ttf"),
                ("Latha", "C:/Windows/Fonts/latha.ttf"),
                ("Shruti", "C:/Windows/Fonts/shruti.ttf"),
                ("Tunga", "C:/Windows/Fonts/tunga.ttf"),
                ("Raavi", "C:/Windows/Fonts/raavi.ttf"),
                ("Kartika", "C:/Windows/Fonts/kartika.ttf"),
                # Arabic/Urdu capable system fonts
                ("TraditionalArabic", "C:/Windows/Fonts/trado.ttf"),
                ("Arial", "C:/Windows/Fonts/arial.ttf"),
                # Thai
                ("LeelawadeeUI", "C:/Windows/Fonts/LeelawUI.ttf"),
                ("AngsanaUPC", "C:/Windows/Fonts/angsau.ttf"),
            ],
            "Darwin": [
                ("Arial", "/System/Library/Fonts/Arial.ttf"),
                ("ArialUnicode", "/Library/Fonts/Arial Unicode MS.ttf"),
                ("Helvetica", "/System/Library/Fonts/Helvetica.ttc"),
                ("AppleGothic", "/System/Library/Fonts/AppleSDGothicNeo.ttc"),
                ("PingFang", "/System/Library/Fonts/PingFang.ttc"),
                ("Hiragino", "/System/Library/Fonts/Hiragino Sans GB.ttc"),
                ("NotoSans", "/Library/Fonts/NotoSans-Regular.ttf"),
            ],
            "Linux": [
                ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                ("Liberation", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
                ("NotoSans", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
                ("NotoSansCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
                ("Ubuntu", "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"),
                ("FreeSans", "/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
            ]
        }
        
        # Register all available Unicode fonts
        registered_fonts = []
        platform_fonts = font_candidates.get(system, font_candidates["Linux"])
        
        for font_name, font_path in platform_fonts:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    registered_fonts.append(font_name)
                except Exception as e:
                    continue
        
        # Select the best available font (prioritize broad Unicode coverage) and auto-download fallback
        primary_font = "Helvetica"  # Fallback until we find better
        for preferred in [
            "Nirmala", "NirmalaUI",  # Wide Indic coverage on Windows 10+
            "ArialUnicode",           # Very broad coverage when present
            "NotoSans",               # If installed locally
            "DejaVuSans", "Tahoma",  # Good general unicode support
            "Liberation", "Arial"
        ]:
            if preferred in registered_fonts:
                primary_font = preferred
                break

        # If none of the good fonts are available, download NotoSans as an embedded fallback
        if primary_font == "Helvetica":
            try:
                import requests as _requests
                fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".fonts")
                os.makedirs(fonts_dir, exist_ok=True)
                noto_path = os.path.join(fonts_dir, "NotoSans-Regular.ttf")
                if not os.path.exists(noto_path):
                    # Stable source for Noto Sans Regular
                    url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
                    resp = _requests.get(url, timeout=20)
                    if resp.status_code == 200:
                        with open(noto_path, "wb") as f:
                            f.write(resp.content)
                if os.path.exists(noto_path):
                    pdfmetrics.registerFont(TTFont("NotoSansFallback", noto_path))
                    primary_font = "NotoSansFallback"
            except Exception:
                # If download fails, continue with Helvetica; text may show missing glyphs
                pass

        # Ensure an Arabic/Urdu font is available for RTL if needed
        arabic_font = None
        for preferred in ["TraditionalArabic", "ArialUnicode", "Tahoma", "NotoSansFallback", "Arial"]:
            if preferred in registered_fonts or preferred == "NotoSansFallback":
                arabic_font = preferred
                break
        if arabic_font is None:
            try:
                import requests as _requests
                fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".fonts")
                os.makedirs(fonts_dir, exist_ok=True)
                noto_urdu_path = os.path.join(fonts_dir, "NotoNastaliqUrdu-Regular.ttf")
                if not os.path.exists(noto_urdu_path):
                    url = "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoNastaliqUrdu/NotoNastaliqUrdu-Regular.ttf"
                    resp = _requests.get(url, timeout=20)
                    if resp.status_code == 200:
                        with open(noto_urdu_path, "wb") as f:
                            f.write(resp.content)
                if os.path.exists(noto_urdu_path):
                    pdfmetrics.registerFont(TTFont("NotoNastaliqUrdu", noto_urdu_path))
                    arabic_font = "NotoNastaliqUrdu"
            except Exception:
                pass

        # Helper to download/register a font (used for Indic and CJK fallbacks on Linux)
        def ensure_font_registered(font_key, urls):
            try:
                if font_key in registered_fonts:
                    return font_key
                fonts_dir_local = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".fonts")
                os.makedirs(fonts_dir_local, exist_ok=True)
                # accept either .ttf or .otf
                ttf_path = os.path.join(fonts_dir_local, f"{font_key}.ttf")
                otf_path = os.path.join(fonts_dir_local, f"{font_key}.otf")
                target_path = ttf_path if os.path.exists(ttf_path) else (otf_path if os.path.exists(otf_path) else None)
                if target_path is None:
                    import requests as _requests
                    for u in urls:
                        try:
                            r = _requests.get(u, timeout=20)
                            if r.status_code == 200 and r.content:
                                # choose extension from url
                                if u.lower().endswith('.otf'):
                                    target_path = otf_path
                                else:
                                    target_path = ttf_path
                                with open(target_path, "wb") as f:
                                    f.write(r.content)
                                break
                        except Exception:
                            continue
                if os.path.exists(target_path):
                    pdfmetrics.registerFont(TTFont(font_key, target_path))
                    # Ensure ReportLab can resolve family mapping (normal/bold/italic)
                    try:
                        pdfmetrics.registerFontFamily(font_key, normal=font_key, bold=font_key, italic=font_key, boldItalic=font_key)
                    except Exception:
                        pass
                    registered_fonts.append(font_key)
                    return font_key
            except Exception:
                pass
            return None
        
        # Create styles with the best Unicode font
        styles = getSampleStyleSheet()
        
        normal_style = ParagraphStyle(
            'UnicodeNormal',
            parent=styles['Normal'],
            fontName=primary_font,
            fontSize=10,
            leading=14,
            spaceAfter=6,
            wordWrap='LTR'  # Left-to-right for most languages
        )
        
        heading_style = ParagraphStyle(
            'UnicodeHeading',
            parent=styles['Heading1'],
            fontName=primary_font,
            fontSize=16,
            leading=20,
            spaceAfter=12,
            wordWrap='LTR'
        )
        
        # Support for RTL languages if needed
        rtl_style = ParagraphStyle(
            'UnicodeRTL',
            parent=normal_style,
            alignment=2,  # Right alignment for RTL
            wordWrap='RTL'
        )
        if arabic_font:
            rtl_style.fontName = arabic_font

        story = []
        story.append(Paragraph(title, heading_style))
        story.append(Spacer(1, 0.25 * inch))

        # Enhanced text processing for Unicode
        # Ensure proper encoding for all Unicode characters
        if isinstance(text, str):
            # Already a string, good to go
            pass
        else:
            # If it's bytes, decode it properly
            text = text.decode('utf-8')
            
        paragraphs = [p.strip() for p in text.replace('\r', '').split('\n\n') if p.strip()]
        if not paragraphs:
            paragraphs = [text]

        # Cache styles by font to avoid re-creating styles for every paragraph
        style_for_font = {primary_font: normal_style}

        # Helper to choose a font given text content
        def select_font_for_text(sample_text):
            # Ranges for scripts
            has_hangul = re.search(r'[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF]', sample_text)
            has_hiragana_katakana = re.search(r'[\u3040-\u309F\u30A0-\u30FF]', sample_text)
            has_cjk = re.search(r'[\u4E00-\u9FFF]', sample_text)
            has_thai = re.search(r'[\u0E00-\u0E7F]', sample_text)
            has_greek = re.search(r'[\u0370-\u03FF]', sample_text)
            has_cyrillic = re.search(r'[\u0400-\u04FF]', sample_text)
            has_hebrew = re.search(r'[\u0590-\u05FF]', sample_text)
            has_devanagari = re.search(r'[\u0900-\u097F]', sample_text)
            has_bengali = re.search(r'[\u0980-\u09FF]', sample_text)
            has_gurmukhi = re.search(r'[\u0A00-\u0A7F]', sample_text)
            has_gujarati = re.search(r'[\u0A80-\u0AFF]', sample_text)
            has_odia = re.search(r'[\u0B00-\u0B7F]', sample_text)
            has_tamil = re.search(r'[\u0B80-\u0BFF]', sample_text)
            has_telugu = re.search(r'[\u0C00-\u0C7F]', sample_text)
            has_kannada = re.search(r'[\u0C80-\u0CFF]', sample_text)
            has_malayalam = re.search(r'[\u0D00-\u0D7F]', sample_text)

            # Korean
            if has_hangul:
                for candidate in ["Malgun", "Gulim", "Batang", "Meiryo", "NotoSansFallback", primary_font]:
                    if candidate in registered_fonts or candidate == "NotoSansFallback":
                        return candidate
            # Japanese
            if has_hiragana_katakana:
                for candidate in ["NotoSansJP", "Meiryo", "MSJhengHei", "SimSun", "NotoSansFallback", primary_font]:
                    # Already registered system font
                    if candidate in registered_fonts:
                        return candidate
                    # Try to ensure downloadable Noto font
                    if candidate == "NotoSansJP":
                        ensured = ensure_font_registered("NotoSansJP", [
                            "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansJP-Regular.otf"
                        ])
                        if ensured:
                            return ensured
                        else:
                            continue
                    # Fallback generic
                    if candidate == "NotoSansFallback":
                        return candidate
            # Chinese (Han)
            if has_cjk:
                for candidate in ["MicrosoftYaHei", "SimHei", "SimSun", "MSJhengHei", "Meiryo", "NotoSansSC", "NotoSansFallback", primary_font]:
                    if candidate in registered_fonts or candidate in ["NotoSansSC", "NotoSansFallback"]:
                        if candidate == "NotoSansSC" and candidate not in registered_fonts:
                            ensured = ensure_font_registered("NotoSansSC", [
                                "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otf"
                            ])
                            if ensured:
                                return ensured
                        return candidate
            # Thai
            if has_thai:
                for candidate in ["LeelawadeeUI", "AngsanaUPC", "Tahoma", "NotoSansThai", "NotoSansFallback", primary_font]:
                    if candidate in registered_fonts or candidate in ["NotoSansThai", "NotoSansFallback"]:
                        if candidate == "NotoSansThai" and candidate not in registered_fonts:
                            ensured = ensure_font_registered("NotoSansThai", [
                                "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansThai/NotoSansThai-Regular.ttf"
                            ])
                            if ensured:
                                return ensured
                        return candidate
            # Greek
            if has_greek:
                for candidate in ["Segoe", "ArialUnicode", "Arial", "NotoSansGreek", "NotoSansFallback", primary_font]:
                    if candidate in registered_fonts or candidate in ["NotoSansGreek", "NotoSansFallback"]:
                        if candidate == "NotoSansGreek" and candidate not in registered_fonts:
                            ensured = ensure_font_registered("NotoSansGreek", [
                                "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansGreek/NotoSansGreek-Regular.ttf"
                            ])
                            if ensured:
                                return ensured
                        return candidate
            # Cyrillic (Russian, Ukrainian, etc.)
            if has_cyrillic:
                for candidate in ["Segoe", "ArialUnicode", "Arial", "NotoSansCyrillic", "NotoSansFallback", primary_font]:
                    if candidate in registered_fonts or candidate in ["NotoSansCyrillic", "NotoSansFallback"]:
                        if candidate == "NotoSansCyrillic" and candidate not in registered_fonts:
                            ensured = ensure_font_registered("NotoSansCyrillic", [
                                "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansCyrillic/NotoSansCyrillic-Regular.ttf"
                            ])
                            if ensured:
                                return ensured
                        return candidate

            # Hebrew (RTL distinct from Arabic)
            if has_hebrew:
                for candidate in ["ArialUnicode", "Arial", "NotoSansHebrew", "NotoSansFallback", primary_font]:
                    if candidate in registered_fonts or candidate in ["NotoSansHebrew", "NotoSansFallback"]:
                        if candidate == "NotoSansHebrew" and candidate not in registered_fonts:
                            ensured = ensure_font_registered("NotoSansHebrew", [
                                "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansHebrew/NotoSansHebrew-Regular.ttf"
                            ])
                            if ensured:
                                return ensured
                        return candidate
            # Indic scripts (download Noto variants if not available)
            if has_devanagari:
                for candidate in ["Nirmala", "Mangal", "NotoSansDevanagari"]:
                    if candidate in registered_fonts:
                        return candidate
                ensured = ensure_font_registered("NotoSansDevanagari", [
                    "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf"
                ])
                if ensured:
                    return ensured
            if has_bengali:
                for candidate in ["Nirmala", "NirmalaUI", "Vrinda", "NotoSansBengali"]:
                    if candidate in registered_fonts:
                        return candidate
                ensured = ensure_font_registered("NotoSansBengali", [
                    "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansBengali/NotoSansBengali-Regular.ttf"
                ])
                if ensured:
                    return ensured
            if has_gurmukhi:
                for candidate in ["Nirmala", "NirmalaUI", "Raavi", "NotoSansGurmukhi"]:
                    if candidate in registered_fonts:
                        return candidate
                ensured = ensure_font_registered("NotoSansGurmukhi", [
                    "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansGurmukhi/NotoSansGurmukhi-Regular.ttf"
                ])
                if ensured:
                    return ensured
            if has_gujarati:
                for candidate in ["Nirmala", "NirmalaUI", "Shruti", "NotoSansGujarati"]:
                    if candidate in registered_fonts:
                        return candidate
                ensured = ensure_font_registered("NotoSansGujarati", [
                    "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansGujarati/NotoSansGujarati-Regular.ttf"
                ])
                if ensured:
                    return ensured
            if has_odia:
                for candidate in ["Nirmala", "NirmalaUI", "Kalinga", "Kartika", "NotoSansOriya", "NotoSansOdia"]:
                    if candidate in registered_fonts:
                        return candidate
                ensured = ensure_font_registered("NotoSansOriya", [
                    "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansOriya/NotoSansOriya-Regular.ttf",
                    "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansOdia/NotoSansOdia-Regular.ttf"
                ]) or ensure_font_registered("NotoSansOdia", [
                    "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansOdia/NotoSansOdia-Regular.ttf"
                ])
                if ensured:
                    return ensured
            if has_tamil:
                for candidate in ["Nirmala", "NirmalaUI", "Latha", "NotoSansTamil"]:
                    if candidate in registered_fonts:
                        return candidate
                ensured = ensure_font_registered("NotoSansTamil", [
                    "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansTamil/NotoSansTamil-Regular.ttf"
                ])
                if ensured:
                    return ensured
            if has_telugu:
                for candidate in ["Nirmala", "NirmalaUI", "Gautami", "NotoSansTelugu"]:
                    if candidate in registered_fonts:
                        return candidate
                ensured = ensure_font_registered("NotoSansTelugu", [
                    "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansTelugu/NotoSansTelugu-Regular.ttf"
                ])
                if ensured:
                    return ensured
            if has_kannada:
                for candidate in ["Nirmala", "NirmalaUI", "Tunga", "NotoSansKannada"]:
                    if candidate in registered_fonts:
                        return candidate
                ensured = ensure_font_registered("NotoSansKannada", [
                    "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansKannada/NotoSansKannada-Regular.ttf"
                ])
                if ensured:
                    return ensured
            if has_malayalam:
                for candidate in ["Nirmala", "NirmalaUI", "Kartika", "NotoSansMalayalam"]:
                    if candidate in registered_fonts:
                        return candidate
                ensured = ensure_font_registered("NotoSansMalayalam", [
                    "https://github.com/googlefonts/noto-fonts/raw/main/unhinted/ttf/NotoSansMalayalam/NotoSansMalayalam-Regular.ttf"
                ])
                if ensured:
                    return ensured
            return primary_font

        # Helper: escape minimal HTML entities for Paragraph input
        def html_escape(value: str) -> str:
            return value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        # Helper: split non-RTL text into font-specific spans so mixed scripts render in one paragraph
        script_patterns = [
            ("hangul", r"[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF]"),
            ("hiragana_katakana", r"[\u3040-\u309F\u30A0-\u30FF]"),
            ("cjk", r"[\u4E00-\u9FFF]"),
            ("thai", r"[\u0E00-\u0E7F]"),
            ("greek", r"[\u0370-\u03FF]"),
            ("cyrillic", r"[\u0400-\u04FF]"),
            ("hebrew", r"[\u0590-\u05FF]"),
            ("arabic", r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"),
            ("devanagari", r"[\u0900-\u097F]"),
            ("bengali", r"[\u0980-\u09FF]"),
            ("gurmukhi", r"[\u0A00-\u0A7F]"),
            ("gujarati", r"[\u0A80-\u0AFF]"),
            ("odia", r"[\u0B00-\u0B7F]"),
            ("tamil", r"[\u0B80-\u0BFF]"),
            ("telugu", r"[\u0C00-\u0C7F]"),
            ("kannada", r"[\u0C80-\u0CFF]"),
            ("malayalam", r"[\u0D00-\u0D7F]")
        ]

        combined_re = re.compile("|".join(f"(?P<{name}>{pat})" for name, pat in script_patterns))

        def segment_with_fonts(non_rtl_text: str) -> str:
            # Walk text and wrap each script run with an explicit font so ReportLab renders all glyphs
            result_parts = []
            current_chunk = []
            current_font = None

            def flush():
                if current_chunk:
                    text_chunk = html_escape("".join(current_chunk)).replace('\n', '<br/>')
                    if current_font:
                        # ReportLab expects the 'face' attribute on <font>
                        result_parts.append(f"<font face=\"{current_font}\">{text_chunk}</font>")
                    else:
                        result_parts.append(text_chunk)
                    current_chunk.clear()

            for ch in non_rtl_text:
                match = combined_re.match(ch)
                if match:
                    # Choose font based on detected script for this char
                    font_for_char = select_font_for_text(ch)
                    if font_for_char != current_font:
                        flush()
                        current_font = font_for_char
                else:
                    # Default to primary font for Latin/punctuation
                    if current_font != primary_font:
                        flush()
                        current_font = primary_font
                current_chunk.append(ch)
            flush()
            return "".join(result_parts)

        # Process each paragraph with Unicode-aware handling
        for para in paragraphs:
            if not para.strip():
                continue
                
            # Detect RTL languages (Arabic, Hebrew, Urdu, etc.) first on raw paragraph
            rtl_chars = re.findall(r'[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', para)

            if rtl_chars and len(rtl_chars) > max(1, int(len(para) * 0.2)):
                # Apply shaping + bidi reordering for Arabic-script languages
                shaped = para
                try:
                    if _arabic_reshaper and _bidi_get_display:
                        shaped = _bidi_get_display(_arabic_reshaper.reshape(para))
                except Exception:
                    pass
                # Minimal HTML escaping after shaping
                safe_para = html_escape(shaped).replace('\n', '<br/>')
                story.append(Paragraph(safe_para, rtl_style))
            else:
                # Build a mixed-font paragraph so multi-language strings render correctly
                mixed = segment_with_fonts(para)
                para_style = style_for_font.get(primary_font)
                if para_style is None:
                    para_style = ParagraphStyle(
                        f'Unicode-{primary_font}',
                        parent=normal_style,
                        fontName=primary_font
                    )
                    style_for_font[primary_font] = para_style
                story.append(Paragraph(mixed, para_style))
            
            story.append(Spacer(1, 0.15 * inch))

        doc.build(story)
        pdf_data = buffer.getvalue()
        buffer.close()
        
        return pdf_data
        
    except Exception as e:
        # Enhanced error reporting for debugging
        error_msg = f"PDF creation error: {str(e)}"
        print(error_msg)
        return None

def ask_llm(question, context, max_retries=3):
    if not GROQ_API_KEY:
        return "Error: GROQ_API_KEY not found in environment variables."
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    # Allow prompt-only calls when context is empty
    if context and context.strip():
        user_content = f"Document Content:\n{context}\n\nQuestion: {question}\n\nPlease provide a detailed and structured response based on the document content."
    else:
        user_content = f"{question}"
    messages = [
        {"role": "system", "content": "You are an expert document analyst specializing in bid and tender documents. Provide clear, accurate, and structured responses based on the document content. If information is not found, clearly state that."},
        {"role": "user", "content": user_content}
    ]
    data = {"model": "llama-3.1-8b-instant", "messages": messages, "temperature": 0.3, "max_tokens": 1000}
    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.post(GROQ_API_URL, headers=headers, json=data, timeout=30)
            if response.status_code >= 400:
                try:
                    err_json = response.json()
                    return f"Error: {response.status_code} - {err_json.get('error', {}).get('message') or err_json}"
                except Exception:
                    return f"Error: {response.status_code} - {response.text}"
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

    def _call_api(chunk_text, attempt_limit=6):
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        prompt = f"""Translate the following English text to {target_language}. Provide ONLY the translated text, without any introductory phrases, explanations, or quotation marks. Text to translate:\n---\n{chunk_text}\n---"""
        messages = [
            {"role": "system", "content": f"You are an expert translator. Your task is to translate English text into {target_language} accurately."},
            {"role": "user", "content": prompt}
        ]
        data = {"model": "llama-3.1-8b-instant", "messages": messages, "temperature": 0.0, "max_tokens": 1800}
        last_err = None
        for attempt in range(attempt_limit):
            try:
                resp = requests.post(GROQ_API_URL, headers=headers, json=data, timeout=60)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    try:
                        wait_s = float(retry_after) if retry_after else min(1.5 * (2 ** attempt), 15)
                    except Exception:
                        wait_s = min(1.5 * (2 ** attempt), 15)
                    time.sleep(wait_s)
                    continue
                if resp.status_code >= 400:
                    try:
                        j = resp.json()
                        last_err = f"{resp.status_code} - {j.get('error', {}).get('message') or j}"
                    except Exception:
                        last_err = f"{resp.status_code} - {resp.text}"
                    time.sleep(min(1.5 * (2 ** attempt), 10))
                    continue
                resp.raise_for_status()
                j = resp.json()
                if 'choices' in j and len(j['choices']) > 0:
                    return j['choices'][0]['message']['content']
                last_err = "Invalid response format"
            except Exception as e:
                last_err = str(e)
                time.sleep(min(1.5 * (2 ** attempt), 10))
                continue
        return f"Error during translation API call: {last_err}"

    if not text_to_translate:
        return ""
    # Chunk long text to reduce tokens-per-minute usage
    max_chunk_chars = 1400
    if len(text_to_translate) <= max_chunk_chars:
        return _call_api(text_to_translate)

    # Split on paragraph boundaries and group to stay within limit
    parts = []
    current = []
    current_len = 0
    for para in [p.strip() for p in text_to_translate.replace('\r', '').split('\n\n')]:
        if not para:
            continue
        add_len = len(para) + 2
        if current_len + add_len > max_chunk_chars and current:
            parts.append('\n\n'.join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += add_len
    if current:
        parts.append('\n\n'.join(current))

    translated_chunks = []
    for chunk in parts:
        translated = _call_api(chunk)
        if translated.startswith("Error"):
            return translated
        translated_chunks.append(translated.strip())
        time.sleep(0.4)
    return '\n\n'.join(translated_chunks)

def generate_comprehensive_summary(text_chunks):
    if not text_chunks:
        return "No content available for summarization."
    summary_prompt = """Analyze this bid/tender document and extract the following key information. If any information is not found, clearly state "Not mentioned" or "Not found":\n\n**BASIC INFORMATION:**\n- Tender Number/Reference:\n- Name of Work/Project:\n- Issuing Department/Organization:\n\n**FINANCIAL DETAILS:**\n- Estimated Contract Value:\n- EMD (Earnest Money Deposit):\n- EMD Exemption (if any):\n- Performance Security:\n\n**TIMELINE:**\n- Bid Submission Deadline:\n- Technical Bid Opening:\n- Contract Duration:\n\n**REQUIREMENTS:**\n- Key Eligibility Criteria:\n- Required Documents:\n- Technical Specifications (brief):\n- Payment Terms:\n\nProvide only the information that is clearly mentioned in the document."""
    all_summaries = []
    with st.spinner("Analyzing document sections..."):
        progress_bar = st.progress(0)
        for i, chunk in enumerate(text_chunks):
            try:
                summary = ask_llm(summary_prompt, chunk)
                if not summary.startswith("Error"):
                    all_summaries.append(summary)
                progress_bar.progress((i + 1) / len(text_chunks))
                time.sleep(1.2)
            except Exception as e:
                st.warning(f"Error processing chunk {i+1}: {str(e)}")
                continue
    if not all_summaries:
        return "Unable to generate summary due to processing errors."
    final_summary_prompt = "Create a single comprehensive summary by combining and deduplicating the information below. Keep the same structure and keep only the most complete and accurate information for each field."
    consolidation_context = chr(10).join([f"Section {i+1}:\n{summary}\n" for i, summary in enumerate(all_summaries)])
    try:
        final_summary = ask_llm(final_summary_prompt, consolidation_context)
        return final_summary if not final_summary.startswith("Error") else all_summaries[0]
    except:
        return all_summaries[0] if all_summaries else "Summary generation failed."

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
    combined_prompt = "Provide a comprehensive answer by combining the relevant information from the provided sections, removing duplicates and contradictions."
    combined_context = f"Question: {question}\n\n" + chr(10).join([f"Section {i+1}: {answer}" for i, answer in enumerate(relevant_answers)])
    try:
        final_answer = ask_llm(combined_prompt, combined_context)
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
            pdf_data = create_pdf_bytes(st.session_state.summary, "Bid Analysis Summary (English)")
            if pdf_data:
                st.download_button(
                    label="📥 Download Original Summary as PDF",
                    data=pdf_data,
                    file_name=f"bid_analysis_original_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            else:
                st.error("PDF generation is unavailable. Ensure 'reportlab' is installed on the server.")
        with col2:
            if "translated_text" in st.session_state and st.session_state.translated_text:
                # PDF for translated summary
                translated_pdf = create_pdf_bytes(
                    st.session_state.translated_text,
                    f"Bid Analysis Summary ({st.session_state.translated_lang})"
                )
                if translated_pdf:
                    st.download_button(
                        label=f"📥 Download Translated ({st.session_state.translated_lang}) as PDF",
                        data=translated_pdf,
                        file_name=f"bid_analysis_{st.session_state.translated_lang.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                # TXT for translated summary
                translated_txt = st.session_state.translated_text.encode('utf-8')
                st.download_button(
                    label=f"📥 Download Translated ({st.session_state.translated_lang}) as TXT",
                    data=translated_txt,
                    file_name=f"bid_analysis_{st.session_state.translated_lang.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
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


