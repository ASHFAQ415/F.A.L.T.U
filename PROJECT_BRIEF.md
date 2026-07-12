# Project Brief: F.A.L.T.U RAG Chatbot

## One-Line Summary

F.A.L.T.U is a full-stack RAG chatbot that lets authenticated users upload documents and ask questions against those documents with cited, streaming AI answers.

## Problem It Solves

Organizations often have knowledge spread across PDFs, Word files, Markdown files, and text documents. Searching manually is slow, and normal chatbots may answer from general model knowledge instead of internal source material. This project solves that by grounding answers in uploaded documents.

## How It Works

1. A user logs in through the Streamlit frontend.
2. The user uploads documents into a selected knowledge base, called a corpus.
3. The FastAPI backend extracts text from the document.
4. The text is split into chunks.
5. Each chunk is embedded with a local sentence-transformers model.
6. The embeddings are stored in ChromaDB.
7. When the user asks a question, the backend retrieves relevant chunks using vector search and BM25 keyword search.
8. The best chunks are used as context for a Groq LLM.
9. The answer streams back to the UI with source citations.
10. The conversation is saved for later history.

## Main Components

| Component | Purpose |
| --- | --- |
| Streamlit frontend | Login, chat UI, document upload, admin dashboard |
| FastAPI backend | API, auth, ingestion, retrieval, LLM orchestration |
| SQLModel database | Users, documents, chat history, feedback |
| ChromaDB | Vector storage for document chunks |
| sentence-transformers | Local text embeddings |
| rank-bm25 | Keyword retrieval |
| Groq API | LLM response generation |
| Prometheus and Grafana | Local metrics and dashboards |

## Core Features

- JWT-based login
- Admin-created users
- Corpus-based permissions
- Document upload and processing
- PDF, DOCX, Markdown, and TXT support
- Hybrid retrieval
- Reranking
- Streaming chat responses
- Source citations
- Chat history
- Feedback collection
- Health checks and metrics

## Target Users

- Teams that want a private chatbot over internal documents.
- Developers learning how to build a production-style RAG system.
- Small organizations that want a low-cost document Q&A assistant.

## Example Usage

1. Admin logs in.
2. Admin uploads company policy documents to the `public` corpus.
3. Admin creates users and assigns permissions.
4. A user selects the `public` corpus.
5. The user asks: `What is the leave policy?`
6. The chatbot retrieves the relevant policy chunks and responds with citations.

## Technical Highlights

- Uses Groq for fast hosted inference.
- Uses local CPU embeddings to avoid embedding API costs.
- Uses ChromaDB as a persistent vector database.
- Combines semantic and keyword search for better retrieval quality.
- Supports local development through Docker Compose.
- Includes deployment files for Railway.

## Current Caveats

- Some comments in the source still reference Ollama, but the actual LLM client is Groq.
- Some existing source comments have encoding artifacts.
- The OAuth token URL used by FastAPI docs may need correction from `/api/auth/login` to `/auth/login`.
