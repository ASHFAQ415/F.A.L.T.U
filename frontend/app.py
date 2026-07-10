"""
app.py — Streamlit Chat UI
============================
The user-facing interface for the Enterprise RAG Chatbot.

Features:
  🔐 Login / logout (JWT auth)
  💬 Real-time streaming chat with citations
  👍/👎 Feedback buttons on each response
  📄 Document upload panel + delete button
  📊 Admin stats dashboard (admin only)
  🕓 Chat session history sidebar with search/filter
  🌙 Dark mode by default
"""

import json
import os
import time
import uuid
from typing import Dict, List, Optional

import requests
import streamlit as st
from sseclient import SSEClient

# ─────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# ─────────────────────────────────────────────────────────
# Page Configuration
# ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Enterprise RAG Chatbot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "Enterprise RAG Chatbot — 100% Free & Self-Hosted",
    },
)

# ─────────────────────────────────────────────────────────
# Custom CSS — Dark Mode, Premium Look
# ─────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Import Google Font ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Base styles ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Hide default Streamlit elements ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }

/* ── App background ── */
.stApp {
    background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%);
    min-height: 100vh;
}

/* ── Sidebar styling ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
    border-right: 1px solid #30363d;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    border-radius: 12px;
    margin-bottom: 8px;
    border: 1px solid rgba(255,255,255,0.05);
}

/* ── Input box ── */
[data-testid="stChatInputContainer"] {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 4px;
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #667eea, #764ba2);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.3s ease;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
}

/* ── Session history item ── */
.session-item {
    background: rgba(255,255,255,0.03);
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 8px 12px;
    margin-bottom: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
    font-size: 13px;
    color: #c9d1d9;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.session-item:hover {
    background: rgba(102, 126, 234, 0.1);
    border-color: #667eea;
}
.session-item.active {
    background: rgba(102, 126, 234, 0.15);
    border-color: #667eea;
    color: #a5b4fc;
}

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 16px;
}

/* ── Status badge ── */
.status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
}
.status-online { background: #1a4731; color: #34d399; border: 1px solid #34d399; }
.status-offline { background: #4c1d1d; color: #f87171; border: 1px solid #f87171; }

/* ── Citation box ── */
.citation-box {
    background: rgba(102, 126, 234, 0.1);
    border-left: 3px solid #667eea;
    border-radius: 0 8px 8px 0;
    padding: 8px 12px;
    margin: 4px 0;
    font-size: 13px;
    color: #a0aec0;
}

/* ── Heading gradient ── */
.gradient-text {
    background: linear-gradient(135deg, #667eea, #764ba2, #f093fb);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 700;
}

/* ── Upload area ── */
[data-testid="stFileUploader"] {
    background: rgba(255,255,255,0.03);
    border: 2px dashed #30363d;
    border-radius: 12px;
    padding: 20px;
}

/* ── Doc card ── */
.doc-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 10px;
    margin-bottom: 8px;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# Session State Initialization
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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ─────────────────────────────────────────────────────────
# API Helper Functions
# ─────────────────────────────────────────────────────────
def api_headers() -> Dict:
    """Return auth headers for API calls."""
    return {"Authorization": f"Bearer {st.session_state.token}"}


def api_get(path: str) -> Optional[Dict]:
    """Make an authenticated GET request to the backend."""
    try:
        r = requests.get(f"{BACKEND_URL}{path}", headers=api_headers(), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def api_post(path: str, data: Dict = None, files=None) -> Optional[Dict]:
    """Make an authenticated POST request to the backend."""
    try:
        if files:
            r = requests.post(
                f"{BACKEND_URL}{path}",
                headers=api_headers(),
                data=data,
                files=files,
                timeout=60,
            )
        else:
            r = requests.post(
                f"{BACKEND_URL}{path}",
                headers=api_headers(),
                json=data,
                timeout=60,
            )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_delete(path: str) -> bool:
    """Make an authenticated DELETE request to the backend."""
    try:
        r = requests.delete(f"{BACKEND_URL}{path}", headers=api_headers(), timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        st.error(f"Delete error: {e}")
        return False


def stream_chat(query: str, session_id: str, corpus: str):
    """
    Stream a chat response from the backend via Server-Sent Events.
    Yields tokens and finally the metadata.
    """
    url = f"{BACKEND_URL}/v1/chat"
    payload = {
        "query": query,
        "session_id": session_id,
        "corpus": corpus,
        "temperature": 0.7,
        "max_tokens": 512,
    }
    headers = {**api_headers(), "Accept": "text/event-stream"}

    with requests.post(url, json=payload, headers=headers, stream=True, timeout=120) as response:
        response.raise_for_status()
        client = SSEClient(response)
        for event in client.events():
            if event.data == "[DONE]":
                break
            try:
                data = json.loads(event.data)
                yield data
            except json.JSONDecodeError:
                continue


# ─────────────────────────────────────────────────────────
# Login Page
# ─────────────────────────────────────────────────────────
def show_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style='text-align: center; padding: 40px 0 20px 0;'>
            <div style='font-size: 64px; margin-bottom: 16px;'>🤖</div>
            <h1 class='gradient-text' style='font-size: 2.5rem; margin: 0;'>Enterprise RAG</h1>
            <p style='color: #8b949e; font-size: 1.1rem; margin-top: 8px;'>
                AI-powered knowledge assistant · 100% free · self-hosted
            </p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            st.markdown("### 🔐 Sign In")
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Sign In →", use_container_width=True)

            if submitted:
                with st.spinner("Signing in..."):
                    try:
                        r = requests.post(
                            f"{BACKEND_URL}/auth/login",
                            data={"username": username, "password": password},
                            timeout=10,
                        )
                        if r.status_code == 200:
                            data = r.json()
                            st.session_state.authenticated = True
                            st.session_state.token = data["access_token"]
                            st.session_state.user = data["user"]
                            st.success("✅ Signed in successfully!")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("❌ Invalid username or password.")
                    except Exception as e:
                        st.error(f"⚠️ Cannot connect to backend. Make sure all services are running.\n\n`{e}`")

        st.markdown("""
        <div style='text-align: center; color: #6e7681; font-size: 13px; margin-top: 20px;'>
            🔒 Secured with JWT authentication &nbsp;·&nbsp; 
            🏠 All data stays on your server &nbsp;·&nbsp; 
            💰 Zero cost
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# Sidebar — Navigation + Chat History
# ─────────────────────────────────────────────────────────
def show_sidebar():
    with st.sidebar:
        # ── User Info ──────────────────────────────────────
        user = st.session_state.user
        st.markdown(f"""
        <div style='padding: 12px; background: rgba(255,255,255,0.05); border-radius: 10px; margin-bottom: 16px;'>
            <div style='font-weight: 600; color: #e6edf3;'>👤 {user['username']}</div>
            <div style='font-size: 12px; color: #8b949e;'>{user['email']}</div>
            {'<span class="status-badge" style="background:#1a2940;color:#667eea;border:1px solid #667eea;font-size:11px;">Admin</span>' if user.get('is_admin') else ''}
        </div>
        """, unsafe_allow_html=True)

        # ── Navigation ─────────────────────────────────────
        st.markdown("### 🗺️ Navigation")
        if st.button("💬 Chat", use_container_width=True):
            st.session_state.page = "chat"
        if st.button("📄 Upload Documents", use_container_width=True):
            st.session_state.page = "upload"
        if user.get("is_admin"):
            if st.button("📊 Admin Dashboard", use_container_width=True):
                st.session_state.page = "admin"

        st.divider()

        # ── Corpus Selector ────────────────────────────────
        st.markdown("### 🗂️ Knowledge Base")
        permissions = user.get("permissions", ["public"])
        if isinstance(permissions, str):
            permissions = [p.strip() for p in permissions.split(",")]
        selected_corpus = st.selectbox("Search in:", options=permissions, index=0)
        st.session_state.corpus = selected_corpus

        st.divider()

        # ── New Chat ───────────────────────────────────────
        if st.button("➕ New Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.active_session_id = None
            st.rerun()

        st.divider()

        # ── Chat History with Search ───────────────────────
        st.markdown("### 🕓 Chat History")
        search_query = st.text_input(
            "🔍 Search sessions",
            value=st.session_state.history_search,
            placeholder="Filter by topic...",
            key="history_search_input",
            label_visibility="collapsed",
        )
        st.session_state.history_search = search_query

        sessions = api_get("/v1/sessions?limit=50")
        if sessions:
            # Filter by search query
            if search_query.strip():
                q = search_query.strip().lower()
                sessions = [s for s in sessions if q in (s.get("title") or "").lower()]

            if sessions:
                for sess in sessions[:20]:
                    title = sess.get("title") or "Untitled Chat"
                    sess_id = sess.get("session_id")
                    is_active = sess_id == st.session_state.active_session_id
                    icon = "💬" if not is_active else "▶️"

                    if st.button(
                        f"{icon} {title[:35]}{'…' if len(title) > 35 else ''}",
                        key=f"sess_{sess_id}",
                        use_container_width=True,
                        help=f"Restore session: {title}",
                    ):
                        _restore_session(sess_id)
            else:
                st.caption("No sessions match your search.")
        else:
            st.caption("No previous chats yet.")

        st.divider()

        # ── System Status ──────────────────────────────────
        st.markdown("### 🟢 System Status")
        health = api_get("/health")
        if health:
            groq_ok = health.get("groq_available", health.get("ollama_available", False))
            chroma_ok = health.get("chroma_available", False)
            db_ok = health.get("database_available", False)
            st.markdown(
                f"Groq LLM: {'<span class=\"status-badge status-online\">Online</span>' if groq_ok else '<span class=\"status-badge status-offline\">Offline</span>'}",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"ChromaDB: {'<span class=\"status-badge status-online\">Online</span>' if chroma_ok else '<span class=\"status-badge status-offline\">Offline</span>'}",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"Database: {'<span class=\"status-badge status-online\">Online</span>' if db_ok else '<span class=\"status-badge status-offline\">Offline</span>'}",
                unsafe_allow_html=True,
            )
            st.caption(f"Model: `{health.get('model', 'llama-3.1-8b-instant')}`")
        else:
            st.warning("⚠️ Backend unreachable")

        st.divider()

        # ── Logout ─────────────────────────────────────────
        if st.button("🚪 Sign Out", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def _restore_session(session_id: str):
    """Load a previous chat session from the backend into the current view."""
    messages_data = api_get(f"/v1/sessions/{session_id}/messages")
    if messages_data is None:
        st.error("Could not load session.")
        return

    restored = []
    for msg in messages_data:
        entry = {
            "role": msg["role"],
            "content": msg["content"],
            "message_id": msg.get("id"),
            "sources": [],
        }
        # Parse sources JSON string if present
        if msg.get("sources"):
            try:
                entry["sources"] = json.loads(msg["sources"])
            except (json.JSONDecodeError, TypeError):
                pass
        restored.append(entry)

    st.session_state.messages = restored
    st.session_state.session_id = session_id
    st.session_state.active_session_id = session_id
    st.session_state.page = "chat"
    st.rerun()


# ─────────────────────────────────────────────────────────
# Chat Page
# ─────────────────────────────────────────────────────────
def show_chat():
    st.markdown("""
    <h1 style='margin-bottom: 4px;'>
        🤖 <span class='gradient-text'>Enterprise RAG Chatbot</span>
    </h1>
    <p style='color: #8b949e; margin-top: 0;'>
        Ask me anything about your documents. I cite my sources.
    </p>
    """, unsafe_allow_html=True)

    # ── Display chat history ────────────────────────────────
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

            if msg["role"] == "assistant" and msg.get("sources"):
                with st.expander("📚 View Sources", expanded=False):
                    for source in msg["sources"]:
                        st.markdown(f"""
                        <div class='citation-box'>
                            <strong>[{source['number']}] {source['source']}</strong><br/>
                            <em>{source['preview']}</em>
                        </div>
                        """, unsafe_allow_html=True)

            # Feedback buttons
            if msg["role"] == "assistant" and msg.get("message_id"):
                col_f1, col_f2, col_space = st.columns([1, 1, 10])
                with col_f1:
                    if st.button("👍", key=f"up_{msg['message_id']}"):
                        api_post(f"/v1/feedback?message_id={msg['message_id']}&rating=1")
                        st.toast("Thanks for the feedback! 🎉")
                with col_f2:
                    if st.button("👎", key=f"down_{msg['message_id']}"):
                        api_post(f"/v1/feedback?message_id={msg['message_id']}&rating=-1")
                        st.toast("Thanks! We'll use this to improve.")

    # ── Chat Input ─────────────────────────────────────────
    corpus = st.session_state.corpus
    if query := st.chat_input(f"Ask about '{corpus}' documents..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(query)

        # Stream response
        with st.chat_message("assistant", avatar="🤖"):
            response_placeholder = st.empty()
            full_response = ""
            sources = []
            message_id = None
            latency_ms = None
            from_cache = False

            try:
                with st.spinner("🔍 Searching knowledge base..."):
                    first_token = True

                for event in stream_chat(query, st.session_state.session_id, corpus):
                    event_type = event.get("type")

                    if event_type == "token":
                        if first_token:
                            first_token = False
                        full_response += event.get("content", "")
                        response_placeholder.markdown(full_response + "▌")

                    elif event_type == "metadata":
                        sources = event.get("sources", [])
                        message_id = event.get("message_id")
                        latency_ms = event.get("latency_ms")
                        from_cache = event.get("from_cache", False)
                        # Update active session for history highlighting
                        if event.get("session_id"):
                            st.session_state.active_session_id = event["session_id"]

                    elif event_type == "error":
                        full_response = event.get("content", "An error occurred.")

                response_placeholder.markdown(full_response)

                # Show sources
                if sources:
                    with st.expander("📚 View Sources", expanded=False):
                        for source in sources:
                            st.markdown(f"""
                            <div class='citation-box'>
                                <strong>[{source['number']}] {source['source']}</strong><br/>
                                <em>{source['preview']}</em>
                            </div>
                            """, unsafe_allow_html=True)

                # Show latency info
                if latency_ms:
                    cache_badge = " ⚡ cached" if from_cache else ""
                    st.caption(f"⏱️ Response time: {latency_ms}ms{cache_badge}")

                # Feedback
                if message_id:
                    col_f1, col_f2, col_space = st.columns([1, 1, 10])
                    with col_f1:
                        if st.button("👍", key=f"up_{message_id}"):
                            api_post(f"/v1/feedback?message_id={message_id}&rating=1")
                            st.toast("Thanks! 🎉")
                    with col_f2:
                        if st.button("👎", key=f"down_{message_id}"):
                            api_post(f"/v1/feedback?message_id={message_id}&rating=-1")
                            st.toast("Thanks for the feedback!")

            except Exception as e:
                full_response = f"⚠️ Error: {str(e)}\n\nMake sure the backend is running and Groq API key is configured."
                response_placeholder.markdown(full_response)

        # Save to session state
        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "sources": sources,
            "message_id": message_id,
        })


# ─────────────────────────────────────────────────────────
# Document Upload Page
# ─────────────────────────────────────────────────────────
def show_upload():
    st.markdown("""
    <h1 class='gradient-text'>📄 Document Upload</h1>
    <p style='color: #8b949e;'>Upload PDF, Word, Markdown, or text files to the knowledge base.</p>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown("### 📤 Upload New Document")
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["pdf", "docx", "md", "txt"],
            help="Supported formats: PDF, Word (.docx), Markdown (.md), Plain text (.txt)",
        )

        if uploaded_file:
            corpus = st.selectbox(
                "Add to knowledge base:",
                options=st.session_state.user.get("permissions", ["public"]),
            )
            required_permissions = st.text_input(
                "Who can access this document?",
                value=corpus,
                help="Comma-separated, e.g. 'public' or 'engineering,admin'",
            )

            if st.button("📥 Upload & Ingest", use_container_width=True):
                with st.spinner(f"Uploading {uploaded_file.name}..."):
                    result = api_post(
                        "/v1/ingest",
                        data={"corpus": corpus, "required_permissions": required_permissions},
                        files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)},
                    )
                    if result:
                        st.success(f"✅ {result.get('message', 'Document uploaded!')}")
                        st.info(f"Document ID: `{result.get('document_id')}` · Status: `{result.get('status')}`")
                        st.rerun()

    with col2:
        st.markdown("### 📚 Knowledge Base")
        docs = api_get("/v1/documents")
        if docs:
            for doc in docs[:30]:
                status_icon = {"ready": "✅", "pending": "⏳", "processing": "🔄", "error": "❌"}.get(doc["status"], "❓")
                col_doc, col_del = st.columns([9, 1])
                with col_doc:
                    st.markdown(f"""
                    <div class='doc-card'>
                        <strong>{status_icon} {doc['original_filename']}</strong><br/>
                        <small style='color: #8b949e;'>
                            Corpus: {doc['corpus']} ·
                            Chunks: {doc['chunk_count']} ·
                            {round(doc['file_size_bytes'] / 1024, 1)} KB
                        </small>
                    </div>
                    """, unsafe_allow_html=True)
                with col_del:
                    # Show delete button — admins always, others only for their own uploads
                    user = st.session_state.user
                    can_delete = user.get("is_admin") or doc.get("uploaded_by") == user.get("id")
                    if can_delete:
                        if st.button("🗑️", key=f"del_doc_{doc['id']}", help=f"Delete {doc['original_filename']}"):
                            if api_delete(f"/v1/documents/{doc['id']}"):
                                st.success(f"Deleted '{doc['original_filename']}'")
                                st.rerun()
        else:
            st.info("📭 No documents ingested yet. Upload your first document!")


# ─────────────────────────────────────────────────────────
# Admin Dashboard Page
# ─────────────────────────────────────────────────────────
def show_admin():
    st.markdown("""
    <h1 class='gradient-text'>📊 Admin Dashboard</h1>
    <p style='color: #8b949e;'>System overview and user management.</p>
    """, unsafe_allow_html=True)

    stats = api_get("/admin/stats")
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("👥 Total Users", stats.get("total_users", 0))
        with col2:
            st.metric("📄 Documents", stats.get("total_documents", 0))
        with col3:
            st.metric("💬 Messages", stats.get("total_messages", 0))
        with col4:
            st.metric("👍 Feedback Rate", f"{stats.get('positive_feedback_rate_pct', 0)}%")

        st.metric("⚡ Avg Response Time", f"{stats.get('avg_response_latency_ms', 0)}ms")

    st.divider()
    st.markdown("### 👥 User Management")

    # Create user form
    with st.expander("➕ Create New User"):
        with st.form("create_user"):
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("Username")
                new_email = st.text_input("Email")
                new_password = st.text_input("Password", type="password")
            with col2:
                new_fullname = st.text_input("Full Name (optional)")
                new_permissions = st.text_input("Permissions", value="public",
                                                 help="Comma-separated: public,engineering,hr")
                new_is_admin = st.checkbox("Is Admin?")

            if st.form_submit_button("Create User", use_container_width=True):
                result = api_post("/admin/users", {
                    "username": new_username,
                    "email": new_email,
                    "password": new_password,
                    "full_name": new_fullname,
                    "permissions": new_permissions,
                    "is_admin": new_is_admin,
                })
                if result:
                    st.success(f"✅ User '{new_username}' created!")
                    st.rerun()

    # User list
    users = api_get("/admin/users")
    if users:
        for user in users:
            with st.container():
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"**{user['username']}** — {user['email']}")
                with col2:
                    st.caption(f"Permissions: {user['permissions']}")
                with col3:
                    if user["id"] != st.session_state.user["id"]:
                        if st.button("🗑️", key=f"del_{user['id']}", help="Delete user"):
                            requests.delete(
                                f"{BACKEND_URL}/admin/users/{user['id']}",
                                headers=api_headers(),
                            )
                            st.rerun()


# ─────────────────────────────────────────────────────────
# Main App
# ─────────────────────────────────────────────────────────
def main():
    init_session()

    if not st.session_state.authenticated:
        show_login()
        return

    show_sidebar()

    page = st.session_state.page
    if page == "chat":
        show_chat()
    elif page == "upload":
        show_upload()
    elif page == "admin":
        if st.session_state.user.get("is_admin"):
            show_admin()
        else:
            st.error("🚫 You don't have admin access.")
    else:
        show_chat()


if __name__ == "__main__":
    main()
