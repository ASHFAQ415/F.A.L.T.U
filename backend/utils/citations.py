"""
utils/citations.py — Citation Builder
=======================================
Formats retrieved chunks into clean citation references
that are shown below the chatbot's answer.

Example output:
  [1] employee_handbook.pdf (page 12)
  [2] onboarding_guide.md
"""

from typing import Dict, List


def build_citations(chunks: List[Dict]) -> List[Dict]:
    """
    Build a clean citation list from retrieved chunks.
    
    Args:
        chunks: List of chunk dicts from the retriever/reranker
        
    Returns:
        List of citation dicts with number, source, and preview
    """
    seen_sources = set()
    citations = []

    for i, chunk in enumerate(chunks):
        source = chunk.get("source", "Unknown Source")

        # Deduplicate — don't show the same source twice
        if source in seen_sources:
            continue
        seen_sources.add(source)

        citation = {
            "number": len(citations) + 1,
            "source": source,
            "preview": chunk["text"][:150] + "..." if len(chunk["text"]) > 150 else chunk["text"],
            "score": round(chunk.get("rerank_score", chunk.get("rrf_score", 0.0)), 3),
        }
        citations.append(citation)

    return citations


def format_citations_as_markdown(citations: List[Dict]) -> str:
    """Format citations as a markdown list for display."""
    if not citations:
        return ""

    lines = ["\n\n---\n**📚 Sources:**"]
    for c in citations:
        lines.append(f"- [{c['number']}] **{c['source']}** — *{c['preview']}*")
    return "\n".join(lines)
