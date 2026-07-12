"""
app.py — F.A.L.T.U Chat UI
============================
F.A.L.T.U = Fantastically Accurate Language & Thinking Unit

The funniest, most modern enterprise chatbot UI.
It's called "useless" but it's actually INCREDIBLY useful.
That's the joke. 

Features:
  🤡 Hilarious branding that confuses everyone
  💬 Real-time streaming chat with citations
  👍/👎 Feedback buttons
  📄 Document upload + delete
  📊 Admin dashboard
  🕓 Chat history sidebar with search
  🌙 Neon dark mode that slaps
"""

import json
import os
import random
import time
import uuid
from typing import Dict, List, Optional

import requests
import streamlit as st
from sseclient import SSEClient

# ─────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000").strip().rstrip("/")
# Auto-add https:// if no scheme provided (common Railway config mistake)
if BACKEND_URL and not BACKEND_URL.startswith(("http://", "https://")):
    BACKEND_URL = "https://" + BACKEND_URL


# F.A.L.T.U personality — random loading messages
LOADING_MSGS = [
    "🧠 Pretending to think really hard...",
    "🔍 Searching documents (and my soul)...",
    "⚡ Channeling my inner genius...",
    "🎯 Definitely not making this up...",
    "📚 Actually reading the documents this time...",
    "🤔 Consulting my 8-ball backup system...",
    "🚀 Launching brain cells at full power...",
    "🎲 Calculating... (source: trust me bro)...",
    "🦆 Rubber duck debugging your question...",
    "☕ One moment, LLM needs its coffee...",
]

EMPTY_STATE_MSGS = [
    "Waiting for your query... and your love 💝",
    "Ask me anything! (I might actually know it 😤)",
    "No documents? Upload something! I'm bored 😴",
    "Ready to serve! Unlike my previous job 🫡",
]

# ─────────────────────────────────────────────────────────
# Page Configuration
# ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="F.A.L.T.U — Fantastically Accurate Language & Thinking Unit",
    page_icon="🤡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "F.A.L.T.U — The AI that's NOT useless (despite the name)",
        "Get help": "https://github.com",
    },
)

# ─────────────────────────────────────────────────────────
# 🎨 FALTU CSS — Neon Glassmorphism Dark Mode
# ─────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Google Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

/* ── Reset & Base ── */
html, body, [class*="css"] {
    font-family: 'Space Grotesk', sans-serif !important;
}

/* ── Hide Streamlit chrome ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }

/* ── App Background — Deep space vibe ── */
.stApp {
    background: #080810;
    background-image:
        radial-gradient(ellipse at 10% 20%, rgba(124, 58, 237, 0.15) 0%, transparent 50%),
        radial-gradient(ellipse at 90% 80%, rgba(236, 72, 153, 0.12) 0%, transparent 50%),
        radial-gradient(ellipse at 50% 50%, rgba(6, 182, 212, 0.05) 0%, transparent 70%);
    min-height: 100vh;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: rgba(10, 10, 20, 0.95) !important;
    border-right: 1px solid rgba(124, 58, 237, 0.3) !important;
    backdrop-filter: blur(20px);
}
[data-testid="stSidebar"] > div:first-child {
    background: transparent !important;
}

/* ── FALTU Logo Title ── */
.faltu-logo {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2.8rem;
    font-weight: 700;
    background: linear-gradient(135deg, #a855f7, #ec4899, #06b6d4, #a855f7);
    background-size: 300% 300%;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: gradientShift 4s ease infinite;
    letter-spacing: -1px;
    line-height: 1.1;
}

.faltu-subtitle {
    font-size: 0.75rem;
    font-weight: 500;
    color: #6b7280;
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-top: 4px;
}

@keyframes gradientShift {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

/* ── Neon glow pulse on logo ── */
@keyframes neonPulse {
    0%, 100% { text-shadow: 0 0 10px rgba(168, 85, 247, 0.5), 0 0 20px rgba(168, 85, 247, 0.3); }
    50% { text-shadow: 0 0 20px rgba(168, 85, 247, 0.8), 0 0 40px rgba(168, 85, 247, 0.5); }
}

/* ── Chat Messages — Glassmorphism cards ── */
[data-testid="stChatMessage"] {
    border-radius: 16px !important;
    margin-bottom: 12px !important;
    backdrop-filter: blur(10px) !important;
    transition: transform 0.2s ease !important;
}
[data-testid="stChatMessage"]:hover {
    transform: translateY(-1px) !important;
}

/* ── CRITICAL: Force bright readable text in ALL chat messages ── */
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] div,
[data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] ul,
[data-testid="stChatMessage"] ol,
[data-testid="stChatMessage"] strong,
[data-testid="stChatMessage"] em,
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3,
[data-testid="stChatMessage"] h4,
[data-testid="stChatMessage"] a,
[data-testid="stChatMessage"] code {
    color: #e2e8f0 !important;
}
[data-testid="stChatMessage"] code {
    background: rgba(0,0,0,0.3) !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-size: 13px !important;
}
[data-testid="stChatMessage"] strong {
    color: #f1f5f9 !important;
    font-weight: 700 !important;
}

/* User message */
[data-testid="stChatMessage"][data-testid*="user"],
div[data-testid="stChatMessage"]:has([aria-label*="user"]) {
    background: linear-gradient(135deg, rgba(124, 58, 237, 0.15), rgba(236, 72, 153, 0.1)) !important;
    border: 1px solid rgba(124, 58, 237, 0.25) !important;
}

/* Assistant message */
div[data-testid="stChatMessage"]:not(:has([aria-label*="user"])) {
    background: linear-gradient(135deg, rgba(6, 182, 212, 0.08), rgba(124, 58, 237, 0.08)) !important;
    border: 1px solid rgba(6, 182, 212, 0.2) !important;
}

/* ── Caption / small text inside chat ── */
[data-testid="stChatMessage"] [data-testid="stCaptionContainer"] p {
    color: #6b7280 !important;
    font-size: 11px !important;
}

/* ── Markdown text in general app ── */
.stMarkdown p, .stMarkdown li, .stMarkdown span {
    color: #e2e8f0;
}

/* ── Code blocks inside chat — monospace dark boxes ── */
[data-testid="stChatMessage"] pre {
    background: rgba(0, 0, 0, 0.45) !important;
    border: 1px solid rgba(124, 58, 237, 0.25) !important;
    border-radius: 8px !important;
    padding: 12px 14px !important;
    overflow-x: auto !important;
    margin: 8px 0 !important;
}
[data-testid="stChatMessage"] pre code {
    background: transparent !important;
    color: #c4b5fd !important;
    font-size: 13px !important;
    font-family: 'JetBrains Mono', monospace !important;
}

/* ── Animated typing indicator ── */
.typing-indicator {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 8px 4px;
}
.typing-indicator span {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #a855f7;
    animation: typing-bounce 1.4s ease infinite;
    display: inline-block;
}
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing-bounce {
    0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
    40% { transform: scale(1); opacity: 1; }
}

/* ── Timestamp ── */
.msg-timestamp {
    font-size: 10px;
    color: #4b5563;
    margin-top: 4px;
    font-family: 'JetBrains Mono', monospace;
}

/
/* -- Server status badges (login page) -- */
.badge-online {
    display: inline-block;
    background: rgba(52, 211, 153, 0.15);
    border: 1px solid rgba(52, 211, 153, 0.4);
    color: #34d399;
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: 600;
}
.badge-offline {
    display: inline-block;
    background: rgba(248, 113, 113, 0.15);
    border: 1px solid rgba(248, 113, 113, 0.4);
    color: #f87171;
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: 600;
}

* ── Chat Input ── */
[data-testid="stChatInputContainer"] {
    background: rgba(15, 15, 30, 0.9) !important;
    border: 1px solid rgba(124, 58, 237, 0.4) !important;
    border-radius: 16px !important;
    backdrop-filter: blur(20px) !important;
    transition: border-color 0.3s ease !important;
}
[data-testid="stChatInputContainer"]:focus-within {
    border-color: rgba(168, 85, 247, 0.8) !important;
    box-shadow: 0 0 20px rgba(168, 85, 247, 0.2) !important;
}

/* ── Buttons — Neon gradient ── */
.stButton > button {
    background: linear-gradient(135deg, #7c3aed, #db2777) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-family: 'Space Grotesk', sans-serif !important;
    transition: all 0.25s ease !important;
    letter-spacing: 0.3px !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 25px rgba(124, 58, 237, 0.5) !important;
    background: linear-gradient(135deg, #8b5cf6, #ec4899) !important;
}
.stButton > button:active {
    transform: translateY(0px) !important;
}

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: rgba(124, 58, 237, 0.08) !important;
    border: 1px solid rgba(124, 58, 237, 0.2) !important;
    border-radius: 14px !important;
    padding: 16px !important;
    transition: all 0.3s ease !important;
}
[data-testid="metric-container"]:hover {
    background: rgba(124, 58, 237, 0.15) !important;
    border-color: rgba(124, 58, 237, 0.4) !important;
    transform: translateY(-2px) !important;
}

/* ── Status badges ── */
.badge-online {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 12px; border-radius: 20px;
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.4);
    color: #34d399; font-size: 12px; font-weight: 600;
}
.badge-online::before { content: "●"; animation: blink 1.5s infinite; }
.badge-offline {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 12px; border-radius: 20px;
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.4);
    color: #f87171; font-size: 12px; font-weight: 600;
}
@keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
}

/* ── Citation box ── */
.citation-card {
    background: linear-gradient(135deg, rgba(6, 182, 212, 0.08), rgba(124, 58, 237, 0.05));
    border-left: 3px solid #06b6d4;
    border-radius: 0 10px 10px 0;
    padding: 10px 14px;
    margin: 6px 0;
    font-size: 13px;
    color: #94a3b8;
    transition: all 0.2s ease;
}
.citation-card:hover {
    background: linear-gradient(135deg, rgba(6, 182, 212, 0.15), rgba(124, 58, 237, 0.1));
    border-left-color: #a855f7;
    color: #cbd5e1;
}

/* ── Session history item ── */
.sess-btn {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(124, 58, 237, 0.15) !important;
    border-radius: 10px !important;
    color: #94a3b8 !important;
    font-size: 13px !important;
    text-align: left !important;
    transition: all 0.2s ease !important;
}
.sess-btn:hover {
    background: rgba(124, 58, 237, 0.12) !important;
    border-color: rgba(124, 58, 237, 0.4) !important;
    color: #c4b5fd !important;
}

/* ── User info card ── */
.user-card {
    background: linear-gradient(135deg, rgba(124, 58, 237, 0.12), rgba(236, 72, 153, 0.08));
    border: 1px solid rgba(124, 58, 237, 0.25);
    border-radius: 14px;
    padding: 14px;
    margin-bottom: 18px;
}

/* ── Upload area ── */
[data-testid="stFileUploader"] {
    background: rgba(124, 58, 237, 0.05) !important;
    border: 2px dashed rgba(124, 58, 237, 0.3) !important;
    border-radius: 14px !important;
    transition: all 0.3s ease !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: rgba(124, 58, 237, 0.6) !important;
    background: rgba(124, 58, 237, 0.1) !important;
}

/* ── Doc cards ── */
.doc-card {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 12px 14px;
    margin-bottom: 8px;
    transition: all 0.2s ease;
}
.doc-card:hover {
    background: rgba(124, 58, 237, 0.08);
    border-color: rgba(124, 58, 237, 0.25);
}

/* ── Divider ── */
hr {
    border-color: rgba(124, 58, 237, 0.2) !important;
    margin: 16px 0 !important;
}

/* ── Selectbox ── */
[data-testid="stSelectbox"] > div > div {
    background: rgba(15, 15, 30, 0.9) !important;
    border: 1px solid rgba(124, 58, 237, 0.3) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
}

/* ── Text inputs ── */
[data-testid="stTextInput"] > div > div > input,
[data-testid="stTextArea"] textarea {
    background: rgba(15, 15, 30, 0.9) !important;
    border: 1px solid rgba(124, 58, 237, 0.3) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-family: 'Space Grotesk', sans-serif !important;
}
[data-testid="stTextInput"] > div > div > input:focus {
    border-color: rgba(168, 85, 247, 0.7) !important;
    box-shadow: 0 0 15px rgba(168, 85, 247, 0.15) !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: rgba(6, 182, 212, 0.05) !important;
    border: 1px solid rgba(6, 182, 212, 0.15) !important;
    border-radius: 12px !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: rgba(0,0,0,0.2); }
::-webkit-scrollbar-thumb { background: rgba(124, 58, 237, 0.4); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(168, 85, 247, 0.6); }

/* ── Floating emoji ── */
@keyframes float {
    0%, 100% { transform: translateY(0px) rotate(0deg); }
    33% { transform: translateY(-8px) rotate(-5deg); }
    66% { transform: translateY(-4px) rotate(5deg); }
}
.floating { animation: float 3s ease-in-out infinite; display: inline-block; }

/* ── Shimmer text ── */
.shimmer {
    background: linear-gradient(90deg, #a855f7 0%, #ec4899 25%, #06b6d4 50%, #ec4899 75%, #a855f7 100%);
    background-size: 400% 100%;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: shimmer 3s ease infinite;
}
@keyframes shimmer {
    0% { background-position: 100% 0; }
    100% { background-position: -100% 0; }
}

/* ── Tag pill ── */
.tag-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    background: rgba(124, 58, 237, 0.2);
    border: 1px solid rgba(124, 58, 237, 0.4);
    color: #c4b5fd;
    margin: 2px;
}
.tag-admin {
    background: rgba(236, 72, 153, 0.2);
    border-color: rgba(236, 72, 153, 0.4);
    color: #f9a8d4;
}

/* ── Stats card ── */
.stat-row {
    display: flex; gap: 8px; margin-bottom: 8px;
}

/* ── Code font ── */
code, .mono {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# Session State Init
# ─────────────────────────────────────────────────────────
def init_session():
    defaults = {
        "authenticated": False,
        "token": None,
        "user": None,
        "messages": [],
        "session_id": str(uuid.uuid4()),
        "corpus": "public",
        "page": "chat",
        "history_search": "",
        "active_session_id": None,
        "pending_query": None,       # For clickable prompt chips
        "last_health_check": 0,      # Unix timestamp of last /health call
        "health_data": {},           # Cached health data
        "regenerate_query": None,    # Last query for regenerate button
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ─────────────────────────────────────────────────────────
# API Helpers
# ─────────────────────────────────────────────────────────
def api_headers() -> Dict:
    return {"Authorization": f"Bearer {st.session_state.token}"}

def api_get(path: str, silent: bool = False) -> Optional[Dict]:
    try:
        r = requests.get(f"{BACKEND_URL}{path}", headers=api_headers(), timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        if not silent:
            st.warning("⚠️ Cannot reach the server. Check your connection.")
        return None
    except requests.exceptions.Timeout:
        if not silent:
            st.warning("⏱️ Request timed out. The server may be busy.")
        return None
    except requests.exceptions.HTTPError as e:
        if not silent and e.response.status_code not in (401, 403):
            st.error(f"🚫 Server error ({e.response.status_code}). Please try again.")
        return None
    except Exception:
        return None

def api_post(path: str, data: Dict = None, files=None) -> Optional[Dict]:
    try:
        if files:
            r = requests.post(f"{BACKEND_URL}{path}", headers=api_headers(), data=data, files=files, timeout=90)
        else:
            r = requests.post(f"{BACKEND_URL}{path}", headers=api_headers(), json=data, timeout=90)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("⚠️ Cannot reach the server. Please check your connection and try again.")
        return None
    except requests.exceptions.Timeout:
        st.error("⏱️ Request timed out. The server may be processing a large file — please wait and refresh.")
        return None
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", "")
        except Exception:
            pass
        st.error(f"🚫 {detail or 'Request failed. Please try again.'}")
        return None
    except Exception as e:
        st.error(f"🚫 Unexpected error: {str(e)[:100]}")
        return None

def api_delete(path: str) -> bool:
    try:
        r = requests.delete(f"{BACKEND_URL}{path}", headers=api_headers(), timeout=15)
        r.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", "")
        except Exception:
            pass
        st.error(f"🚫 {detail or 'Delete failed. You may not have permission.'}")
        return False
    except Exception as e:
        st.error(f"🚫 Delete failed: {str(e)[:80]}")
        return False

def stream_chat(query: str, session_id: str, corpus: str):
    url = f"{BACKEND_URL}/v1/chat"
    # max_tokens=1024 gives room for complete answers; backend enforces minimum too
    payload = {"query": query, "session_id": session_id, "corpus": corpus, "temperature": 0.7, "max_tokens": 1024}
    headers = {**api_headers(), "Accept": "text/event-stream"}
    try:
        with requests.post(url, json=payload, headers=headers, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            client = SSEClient(resp)
            for event in client.events():
                if event.data == "[DONE]":
                    break
                try:
                    yield json.loads(event.data)
                except json.JSONDecodeError:
                    continue
    except requests.exceptions.ConnectionError:
        yield {"type": "error", "content": "⚠️ Cannot reach the server. Please check your internet connection."}
    except requests.exceptions.Timeout:
        yield {"type": "error", "content": "⏱️ The request timed out. The server may be overloaded — please try again in a moment."}
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400:
            try:
                detail = e.response.json().get("detail", "Invalid request.")
            except Exception:
                detail = "Invalid request."
            yield {"type": "error", "content": f"🚫 {detail}"}
        elif e.response.status_code == 403:
            yield {"type": "error", "content": "🔒 You don't have permission to access this knowledge base."}
        elif e.response.status_code == 429:
            yield {"type": "error", "content": "🐢 You're sending messages too fast. Please slow down."}
        else:
            yield {"type": "error", "content": "🚫 Server error. Please try again."}


# ─────────────────────────────────────────────────────────
# 🔐 Login Page
# ─────────────────────────────────────────────────────────
def show_login():
    col1, col2, col3 = st.columns([1, 2.5, 1])
    with col2:
        st.markdown("""
        <div style='text-align:center; padding: 60px 0 30px 0;'>
            <div style='font-size: 80px; margin-bottom: 12px;'>
                <span class='floating'>🤡</span>
            </div>
            <div class='faltu-logo'>F.A.L.T.U</div>
            <div class='faltu-subtitle'>Fantastically Accurate Language & Thinking Unit</div>
            <div style='margin-top: 16px; color: #6b7280; font-size: 14px; max-width: 400px; margin: 16px auto 0;'>
                An AI chatbot that's <span style='color:#a855f7; font-weight:600;'>definitely not useless</span> 
                (despite what the name suggests) 🤷
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Fun feature pills
        st.markdown("""
        <div style='text-align:center; margin: 20px 0 30px; display:flex; flex-wrap:wrap; justify-content:center; gap:8px;'>
            <span class='tag-pill'>🔍 RAG Search</span>
            <span class='tag-pill'>⚡ Groq LLM</span>
            <span class='tag-pill'>📚 Cites Sources</span>
            <span class='tag-pill'>🛡️ Guardrails</span>
            <span class='tag-pill'>💰 $0/month</span>
            <span class='tag-pill'>🤡 Named FALTU</span>
        </div>
        """, unsafe_allow_html=True)

        # Show server connectivity status before login
        try:
            health_r = requests.get(f"{BACKEND_URL}/health", timeout=5)
            if health_r.status_code == 200:
                h = health_r.json()
                model = h.get('model', 'llama-3.1-8b-instant')
                st.markdown(
                    f"<div style='text-align:center;margin-bottom:12px;'>"
                    f"<span class='badge-online'>🟢 Server Online · {model}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
        except requests.exceptions.ConnectionError:
            st.markdown(
                "<div style='text-align:center;margin-bottom:12px;'>"
                "<span class='badge-offline'>🔴 Server Offline — Check connection</span>"
                "</div>",
                unsafe_allow_html=True
            )
        except requests.exceptions.Timeout:
            st.markdown(
                "<div style='text-align:center;margin-bottom:12px;'>"
                "<span class='badge-online' style='background:rgba(245,158,11,0.15);border-color:rgba(245,158,11,0.4);color:#fcd34d;'>"
                "⏳ Server Starting Up...</span></div>",
                unsafe_allow_html=True
            )
        except Exception:
            pass

        with st.form("login_form"):
            username = st.text_input("👤 Username", placeholder="Who are you? (No judgment)")
            password = st.text_input("🔑 Password", type="password", placeholder="The secret handshake")
            submitted = st.form_submit_button("🚀 Beam Me In", use_container_width=True)

            if submitted:
                if not username.strip() or not password.strip():
                    st.warning("⚠️ Please enter both username and password.")
                else:
                    with st.spinner("🤡 Authenticating..."):
                        for attempt in range(2):
                            try:
                                r = requests.post(
                                    f"{BACKEND_URL}/auth/login",
                                    data={"username": username, "password": password},
                                    timeout=30,
                                )
                                if r.status_code == 200:
                                    data = r.json()
                                    st.session_state.authenticated = True
                                    st.session_state.token = data["access_token"]
                                    st.session_state.user = data["user"]
                                    st.success("✅ Welcome! Loading your workspace...")
                                    time.sleep(0.5)
                                    st.rerun()
                                    break
                                elif r.status_code == 401:
                                    st.error("❌ Wrong username or password.")
                                    break
                                elif r.status_code == 403:
                                    st.error("🚫 Account disabled. Contact your admin.")
                                    break
                                else:
                                    st.error(f"❌ Login failed (code {r.status_code}). Please try again.")
                                    break
                            except requests.exceptions.ReadTimeout:
                                if attempt == 0:
                                    st.info("⏳ Server is warming up... Retrying in 5 seconds...")
                                    time.sleep(5)
                                    continue
                                else:
                                    st.warning(
                                        "⏳ **Server is still starting up.**\n\n"
                                        "Railway spins down idle services. "
                                        "Please wait **30-60 seconds** then click **🚀 Beam Me In** again."
                                    )
                            except requests.exceptions.ConnectionError:
                                st.error(
                                    "🔌 **Cannot connect to the server.**\n\n"
                                    "• Check your internet connection\n"
                                    "• The server may be restarting\n"
                                    "• Try again in 30 seconds"
                                )
                                break
                            except Exception as e:
                                st.error("⚠️ Unexpected error. Please try again in a moment.")
                                break

        st.markdown("""
        <div style='text-align:center; color:#4b5563; font-size:12px; margin-top:20px; line-height:2;'>
            🔒 JWT Auth &nbsp;·&nbsp; 🏠 Self-Hosted &nbsp;·&nbsp; 💸 Free Forever &nbsp;·&nbsp; 🤡 Proudly Useless
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# 🗂️ Sidebar
# ─────────────────────────────────────────────────────────
def show_sidebar():
    with st.sidebar:
        # Logo
        st.markdown("""
        <div style='padding: 8px 0 4px; text-align:center;'>
            <div class='faltu-logo' style='font-size:1.8rem;'>🤡 F.A.L.T.U</div>
            <div style='font-size:10px; color:#6b7280; letter-spacing:2px; margin-top:2px;'>
                NOT USELESS SINCE 2024
            </div>
        </div>
        <hr/>
        """, unsafe_allow_html=True)

        # User card
        user = st.session_state.user
        perms = user.get("permissions", "public")
        admin_badge = '<span class="tag-pill tag-admin">👑 Admin</span>' if user.get("is_admin") else '<span class="tag-pill">👤 User</span>'
        st.markdown(f"""
        <div class='user-card'>
            <div style='font-weight:600; color:#e2e8f0; font-size:15px;'>@{user['username']}</div>
            <div style='font-size:12px; color:#6b7280; margin: 3px 0 8px;'>{user.get('email','')}</div>
            {admin_badge}
        </div>
        """, unsafe_allow_html=True)

        # Navigation
        st.markdown("**🗺️ Navigate**")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("💬 Chat", use_container_width=True):
                st.session_state.page = "chat"
                st.rerun()
        with col_b:
            if st.button("📄 Docs", use_container_width=True):
                st.session_state.page = "upload"
                st.rerun()

        if user.get("is_admin"):
            if st.button("📊 Admin Dashboard", use_container_width=True):
                st.session_state.page = "admin"
                st.rerun()

        st.divider()

        # Knowledge base selector
        st.markdown("**🗂️ Knowledge Base**")
        perms_list = [p.strip() for p in perms.split(",")] if isinstance(perms, str) else perms
        selected = st.selectbox("Search in:", options=perms_list, index=0, label_visibility="collapsed")
        st.session_state.corpus = selected

        st.divider()

        # New chat
        if st.button("➕ Fresh Conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.active_session_id = None
            st.rerun()

        st.divider()

        # Chat history with search
        st.markdown("**🕓 Chat History**")
        search = st.text_input(
            "Search",
            placeholder="🔍 Filter chats...",
            value=st.session_state.history_search,
            label_visibility="collapsed",
            key="hist_search",
        )
        st.session_state.history_search = search

        sessions = api_get("/v1/sessions?limit=50") or []
        if search.strip():
            sessions = [s for s in sessions if search.lower() in (s.get("title") or "").lower()]

        if sessions:
            for sess in sessions[:20]:
                title = sess.get("title") or "Untitled Chat"
                sid = sess.get("session_id")
                is_active = sid == st.session_state.active_session_id
                prefix = "▶️" if is_active else "💬"
                label = f"{prefix} {title[:30]}{'…' if len(title)>30 else ''}"
                if st.button(label, key=f"sess_{sid}", use_container_width=True, help=title):
                    _restore_session(sid)
        else:
            st.markdown("<div style='color:#4b5563; font-size:12px; text-align:center; padding:8px;'>No chats yet. Say hello! 👋</div>", unsafe_allow_html=True)

        st.divider()

        # Status — cached for 30s to avoid API calls on every rerender
        st.markdown("**🟢 System Status**")
        now = time.time()
        if now - st.session_state.get("last_health_check", 0) > 30:
            fresh = api_get("/health", silent=True) or {}
            st.session_state["health_data"] = fresh
            st.session_state["last_health_check"] = now
        health = st.session_state.get("health_data", {})
        groq_ok = health.get("groq_available", health.get("ollama_available", False))
        chroma_ok = health.get("chroma_available", False)
        db_ok = health.get("database_available", True)

        def badge(ok, label):
            cls = "badge-online" if ok else "badge-offline"
            return f'<span class="{cls}">{label}</span>'

        st.markdown(f"""
        <div style='display:flex; flex-direction:column; gap:6px; margin-bottom:8px;'>
            {badge(groq_ok, "🚀 Groq LLM")}
            {badge(chroma_ok, "🔮 ChromaDB")}
            {badge(db_ok, "🐘 Database")}
        </div>
        <div style='font-size:11px; color:#4b5563; font-family: "JetBrains Mono", monospace;'>
            model: {health.get('model','llama-3.1-8b-instant')}
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        if st.button("🚪 Escape Pod (Logout)", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


def _restore_session(session_id: str):
    data = api_get(f"/v1/sessions/{session_id}/messages")
    if not data:
        st.error("🔍 Session not found. It probably ran away.")
        return
    restored = []
    for msg in data:
        entry = {"role": msg["role"], "content": msg["content"], "message_id": msg.get("id"), "sources": []}
        if msg.get("sources"):
            try:
                entry["sources"] = json.loads(msg["sources"])
            except Exception:
                pass
        restored.append(entry)
    st.session_state.messages = restored
    st.session_state.session_id = session_id
    st.session_state.active_session_id = session_id
    st.session_state.page = "chat"
    st.rerun()


# ─────────────────────────────────────────────────────────
# 💬 Chat Page
# ─────────────────────────────────────────────────────────
def show_chat():
    # Header
    st.markdown("""
    <div style='margin-bottom: 24px;'>
        <h1 style='margin:0; font-family:"Space Grotesk",sans-serif; font-size:2.2rem; font-weight:700;'>
            <span class='shimmer'>F.A.L.T.U</span>
            <span style='color:#374151; font-size:1.2rem; font-weight:400; margin-left:8px;'>/ chat</span>
        </h1>
        <p style='color:#6b7280; margin:4px 0 0; font-size:14px;'>
            Ask anything about your docs. I cite sources. I'm <em>basically</em> a genius. 🧠
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Empty state with CLICKABLE chips
    if not st.session_state.messages:
        corpus = st.session_state.corpus
        st.markdown(f"""
        <div style='text-align:center; padding: 40px 20px 20px;'>
            <div style='font-size:64px; margin-bottom:16px;'>
                <span class='floating'>🤡</span>
            </div>
            <div style='font-size:18px; font-weight:600; color:#9ca3af; margin-bottom:8px;'>
                {random.choice(EMPTY_STATE_MSGS)}
            </div>
            <div style='font-size:13px; color:#6b7280;'>
                Searching in: <span style='color:#a855f7; font-weight:600;'>{corpus}</span> knowledge base
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Clickable suggestion chips using Streamlit buttons
        st.markdown("<div style='text-align:center; color:#6b7280; font-size:12px; margin-bottom:8px;'>✨ Try one of these:</div>", unsafe_allow_html=True)
        chip_col1, chip_col2, chip_col3 = st.columns(3)
        suggestions = [
            ("📋", "List all documents"),
            ("📝", "Summarize the main points"),
            ("🔍", "What are the key topics covered?"),
        ]
        for col, (icon, text) in zip([chip_col1, chip_col2, chip_col3], suggestions):
            with col:
                if st.button(f"{icon} {text}", use_container_width=True, key=f"chip_{text[:15]}"):
                    st.session_state.pending_query = text
                    st.rerun()

    # Chat history — render all messages
    for idx, msg in enumerate(st.session_state.messages):
        avatar = "🧑" if msg["role"] == "user" else "🤡"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            # Timestamp
            if msg.get("ts"):
                st.markdown(f"<div class='msg-timestamp'>{msg['ts']}</div>", unsafe_allow_html=True)
            if msg["role"] == "assistant" and msg.get("sources"):
                with st.expander(f"📚 Sources ({len(msg['sources'])} found)", expanded=False):
                    for src in msg["sources"]:
                        st.markdown(f"""
                        <div class='citation-card'>
                            <strong style='color:#67e8f9;'>[{src['number']}] {src['source']}</strong><br/>
                            <span style='font-size:12px;'>{src['preview']}</span>
                        </div>
                        """, unsafe_allow_html=True)
            if msg["role"] == "assistant" and msg.get("message_id"):
                c1, c2, c3, _ = st.columns([1, 1, 1, 11])
                with c1:
                    if st.button("👍", key=f"up_{msg['message_id']}_{idx}"):
                        api_post(f"/v1/feedback?message_id={msg['message_id']}&rating=1")
                        st.toast("❤️ Noted! Teaching FALTU to be less useless.")
                with c2:
                    if st.button("👎", key=f"dn_{msg['message_id']}_{idx}"):
                        api_post(f"/v1/feedback?message_id={msg['message_id']}&rating=-1")
                        st.toast("😤 Got it. FALTU will try harder... maybe.")
                with c3:
                    # Copy button — injects JS to copy content to clipboard
                    safe_content = msg["content"].replace("'", "\\'").replace("\n", "\\n").replace("`", "\\`")
                    st.markdown(
                        f"""<button onclick="navigator.clipboard.writeText('{safe_content}').then(()=>{{this.textContent='✅';setTimeout(()=>{{this.textContent='📋'}},1500)}})" """
                        f"""style='background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);"""
                        f"""border-radius:6px;padding:2px 8px;cursor:pointer;font-size:13px;color:#9ca3af;'>📋</button>""",
                        unsafe_allow_html=True
                    )

    # Chat input — handle pending queries from chip clicks OR regenerate
    corpus = st.session_state.corpus
    pending = st.session_state.get("pending_query", None)
    if pending:
        st.session_state["pending_query"] = None
    regen = st.session_state.get("regenerate_query", None)
    if regen:
        st.session_state["regenerate_query"] = None
    query = pending or regen or st.chat_input(f"Ask F.A.L.T.U about '{corpus}' docs... 🤡")
    if query:
        st.session_state.messages.append({"role": "user", "content": query, "ts": time.strftime("%H:%M")})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(query)

        with st.chat_message("assistant", avatar="🤡"):
            placeholder = st.empty()
            full_response = ""
            sources = []
            message_id = None
            latency_ms = None
            from_cache = False

            try:
                # Show animated typing indicator while waiting for first token
                placeholder.markdown("""
<div class='typing-indicator'>
    <span></span><span></span><span></span>
</div>
""", unsafe_allow_html=True)
                first_token_received = False

                for event in stream_chat(query, st.session_state.session_id, corpus):
                    etype = event.get("type")
                    if etype == "token":
                        if not first_token_received:
                            first_token_received = True
                            full_response = ""  # Clear typing indicator
                        full_response += event.get("content", "")
                        placeholder.markdown(full_response + "▌")
                    elif etype == "metadata":
                        sources = event.get("sources", [])
                        message_id = event.get("message_id")
                        latency_ms = event.get("latency_ms")
                        from_cache = event.get("from_cache", False)
                        if event.get("session_id"):
                            st.session_state.active_session_id = event["session_id"]
                    elif etype == "error":
                        full_response = event.get("content", "Something exploded 💥")

                placeholder.markdown(full_response)

                if sources:
                    with st.expander(f"📚 Sources ({len(sources)} found)", expanded=False):
                        for src in sources:
                            st.markdown(f"""
                            <div class='citation-card'>
                                <strong style='color:#67e8f9;'>[{src['number']}] {src['source']}</strong><br/>
                                <span style='font-size:12px;'>{src['preview']}</span>
                            </div>
                            """, unsafe_allow_html=True)

                if latency_ms:
                    cache_txt = " ⚡ *from cache*" if from_cache else ""
                    st.caption(f"⏱️ {latency_ms}ms{cache_txt} · Powered by F.A.L.T.U™")

                if message_id:
                    c1, c2, c3, _ = st.columns([1, 1, 1.5, 10])
                    with c1:
                        if st.button("👍", key=f"up_{message_id}"):
                            api_post(f"/v1/feedback?message_id={message_id}&rating=1")
                            st.toast("❤️ Teaching FALTU to be less useless!")
                    with c2:
                        if st.button("👎", key=f"dn_{message_id}"):
                            api_post(f"/v1/feedback?message_id={message_id}&rating=-1")
                            st.toast("😤 FALTU will train harder. Or cry. TBD.")
                    with c3:
                        if st.button("🔄 Retry", key=f"regen_{message_id}"):
                            # Remove last assistant message and re-ask
                            if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
                                st.session_state.messages.pop()
                            if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
                                last_q = st.session_state.messages.pop()
                                st.session_state["regenerate_query"] = last_q["content"]
                            st.rerun()

            except requests.exceptions.ConnectionError:
                full_response = "⚠️ **Cannot reach the server.** Please check your internet connection and try again."
                placeholder.markdown(full_response)
            except requests.exceptions.Timeout:
                full_response = "⏱️ **Request timed out.** The server may be busy — please try again in a moment."
                placeholder.markdown(full_response)
            except Exception as e:
                err = str(e)
                if "groq" in err.lower() or "api_key" in err.lower():
                    full_response = "🔑 **AI service error.** The Groq API key may be invalid or rate limited. Contact admin."
                else:
                    full_response = f"🚫 **Something went wrong.** Please try again.\n\n*({err[:120]})*"
                placeholder.markdown(full_response)

        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "sources": sources,
            "message_id": message_id,
            "ts": time.strftime("%H:%M"),
        })


# ─────────────────────────────────────────────────────────
# 📄 Upload Page
# ─────────────────────────────────────────────────────────
def show_upload():
    st.markdown("""
    <h1 style='font-family:"Space Grotesk",sans-serif; font-weight:700; margin-bottom:4px;'>
        📄 <span class='shimmer'>Feed the Beast</span>
    </h1>
    <p style='color:#6b7280; font-size:14px; margin-bottom:24px;'>
        Upload documents so F.A.L.T.U has something to talk about (other than nonsense).
    </p>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown("### 📤 Upload Document")
        uploaded = st.file_uploader(
            "Drop it like it's hot 🔥",
            type=["pdf", "docx", "md", "txt"],
            help="PDF, Word, Markdown, or TXT. Max 50MB. FALTU will devour it.",
        )
        if uploaded:
            user_perms = st.session_state.user.get("permissions", "public")
            perms_list = [p.strip() for p in user_perms.split(",")] if isinstance(user_perms, str) else user_perms
            corpus = st.selectbox("Add to knowledge base:", options=perms_list)
            req_perms = st.text_input("Who can access?", value=corpus, help="e.g. 'public' or 'engineering,admin'")
            if st.button("🚀 Upload & Unleash FALTU", use_container_width=True):
                with st.spinner(f"🤡 FALTU is devouring {uploaded.name}..."):
                    result = api_post(
                        "/v1/ingest",
                        data={"corpus": corpus, "required_permissions": req_perms},
                        files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                    )
                    if result:
                        msg = result.get('message', 'Uploaded successfully!')
                        chunks = result.get('chunk_count', '?')
                        st.success(f"✅ {msg}")
                        if result.get('document_id'):
                            st.info(f"📄 Document ID: `{result.get('document_id')}` | Processing in background...")
                        st.rerun()

    with col2:
        st.markdown("### 📚 Document Library")
        docs = api_get("/v1/documents") or []

        # Check if any docs are still processing → enable live polling
        processing_docs = [d for d in docs if d["status"] in ("pending", "processing")]
        if processing_docs:
            st.info(f"⏳ {len(processing_docs)} document(s) processing... Auto-refreshing.")
            time.sleep(3)
            st.rerun()

        if docs:
            ready_count = sum(1 for d in docs if d["status"] == "ready")
            st.markdown(f"<div style='font-size:12px;color:#6b7280;margin-bottom:8px;'>✅ {ready_count}/{len(docs)} ready to search</div>", unsafe_allow_html=True)
            for doc in docs[:30]:
                icons = {"ready": "✅", "pending": "⏳", "processing": "🔄", "error": "❌"}
                icon = icons.get(doc["status"], "❓")
                status_color = {"ready": "#34d399", "pending": "#f59e0b", "processing": "#60a5fa", "error": "#f87171"}.get(doc["status"], "#6b7280")
                c_doc, c_del = st.columns([10, 1])
                with c_doc:
                    error_html = f"<div style='font-size:11px;color:#f87171;margin-top:3px;'>⚠️ {doc.get('error_message','Unknown error')[:80]}</div>" if doc["status"] == "error" else ""
                    st.markdown(f"""
                    <div class='doc-card'>
                        <div style='font-weight:600; color:#e2e8f0; font-size:13px;'>{icon} {doc['original_filename']}</div>
                        <div style='font-size:11px; color:#6b7280; margin-top:4px;'>
                            <span class='tag-pill'>{doc['corpus']}</span>
                            &nbsp;<span style='color:{status_color};font-weight:600;'>{doc['status']}</span>
                            &nbsp;·&nbsp;{doc['chunk_count']} chunks · {round(doc['file_size_bytes']/1024,1)} KB
                        </div>
                        {error_html}
                    </div>
                    """, unsafe_allow_html=True)
                with c_del:
                    user = st.session_state.user
                    can_delete = user.get("is_admin") or doc.get("uploaded_by") == user.get("id")
                    if can_delete:
                        if st.button("🗑️", key=f"ddoc_{doc['id']}", help="Delete document"):
                            if api_delete(f"/v1/documents/{doc['id']}"):
                                st.success(f"🗑️ Deleted! It's gone. Forever. No take-backs.")
                                st.rerun()
        else:
            st.markdown("""
            <div style='text-align:center; padding:40px; color:#4b5563;'>
                <div style='font-size:48px; margin-bottom:12px;'>📭</div>
                <div style='font-size:14px;'>No documents yet.</div>
                <div style='font-size:12px; margin-top:4px;'>FALTU is hungry. Feed it.</div>
            </div>
            """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# 📊 Admin Dashboard
# ─────────────────────────────────────────────────────────
def show_admin():
    st.markdown("""
    <h1 style='font-family:"Space Grotesk",sans-serif; font-weight:700; margin-bottom:4px;'>
        📊 <span class='shimmer'>Command Center</span>
    </h1>
    <p style='color:#6b7280; font-size:14px; margin-bottom:24px;'>
        You're the boss. F.A.L.T.U answers to you. (Mostly.)
    </p>
    """, unsafe_allow_html=True)

    stats = api_get("/admin/stats") or {}
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("👥 Users", stats.get("total_users", 0))
    with c2: st.metric("📄 Documents", stats.get("total_documents", 0))
    with c3: st.metric("💬 Messages", stats.get("total_messages", 0))
    with c4: st.metric("👍 Positive FB", f"{stats.get('positive_feedback_rate_pct', 0)}%")
    with c5: st.metric("⚡ Avg Latency", f"{stats.get('avg_response_latency_ms', 0)}ms")

    st.divider()
    st.markdown("### 👥 User Management")

    with st.expander("➕ Create New User (Invite someone into the cult)"):
        with st.form("create_user_form"):
            c1, c2 = st.columns(2)
            with c1:
                nu = st.text_input("Username")
                ne = st.text_input("Email")
                np_ = st.text_input("Password", type="password")
            with c2:
                nf = st.text_input("Full Name (optional)")
                npr = st.text_input("Permissions", value="public", help="public,engineering,hr,finance")
                na = st.checkbox("Admin? (With great power...)")
            if st.form_submit_button("🎉 Create User", use_container_width=True):
                result = api_post("/admin/users", {"username": nu, "email": ne, "password": np_, "full_name": nf, "permissions": npr, "is_admin": na})
                if result:
                    st.success(f"✅ @{nu} is now part of the F.A.L.T.U family. They can never leave.")
                    st.rerun()

    users = api_get("/admin/users") or []
    for user in users:
        with st.container():
            cu1, cu2, cu3 = st.columns([3, 3, 1])
            with cu1:
                admin_tag = ' <span class="tag-pill tag-admin">👑 Admin</span>' if user.get("is_admin") else ""
                st.markdown(f"**@{user['username']}** {admin_tag}", unsafe_allow_html=True)
                st.caption(user["email"])
            with cu2:
                perms = user.get("permissions", "public")
                for p in perms.split(","):
                    st.markdown(f'<span class="tag-pill">{p.strip()}</span>', unsafe_allow_html=True)
            with cu3:
                if user["id"] != st.session_state.user["id"]:
                    if st.button("🗑️", key=f"duser_{user['id']}", help="Delete user"):
                        requests.delete(f"{BACKEND_URL}/admin/users/{user['id']}", headers=api_headers())
                        st.rerun()
        st.divider()


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────
def main():
    init_session()

    if not st.session_state.authenticated:
        show_login()
        return

    show_sidebar()

    page = st.session_state.page
    if page == "upload":
        show_upload()
    elif page == "admin":
        if st.session_state.user.get("is_admin"):
            show_admin()
        else:
            st.error("🚫 Admin only zone. Nice try though. 👀")
    else:
        show_chat()


if __name__ == "__main__":
    main()
