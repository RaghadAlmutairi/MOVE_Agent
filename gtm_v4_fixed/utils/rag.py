# -*- coding: utf-8 -*-
"""Structure-preserving hybrid RAG over a LOCAL document collection.

Import-safe: heavy deps (fitz/faiss/langchain) are imported lazily and the index
is built ONCE on first use (lazy singleton), not at import time. Drop the
organisation's PDFs into RAG_DOCS_FOLDER (default ./rag_docs).

Public API:
    rag_sources(subject, market="", max_docs=6) -> List[source-dicts]
    retrieve(query, top_parents=None)           -> List[Document]
    build_index(folder=None)                    -> bool (True if ready)
"""
import os
import re
import glob
from typing import List, Dict, Any, Tuple, Optional


class _RagConfig:
    RAW_FOLDER = os.getenv("RAG_DOCS_FOLDER", "./rag_docs")

    CHUNK_TARGET_TOKENS = 350
    CHUNK_MAX_TOKENS    = 512
    CHUNK_MIN_TOKENS    = 60
    MIN_PAGE_CHARS      = 30

    SLIDE_MAX_TOKENS_PER_PAGE = 450
    SLIDE_MIN_BLOCKS          = 5
    SPARSE_MAX_TOKENS         = 80

    DENSE_K      = 8
    BM25_K       = 8
    DENSE_WEIGHT = 0.6
    BM25_WEIGHT  = 0.4
    TOP_PARENTS  = 4

    EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "text-embedding-3-small")

CFG = _RagConfig()

# Lazily built index state (singleton).
_STATE: Dict[str, Any] = {"ready": False, "parents": None, "hybrid": None,
                          "vectorstore": None, "bm25": None, "error": None}

_enc = None


def _encoder():
    global _enc
    if _enc is None:
        import tiktoken
        _enc = tiktoken.get_encoding("cl100k_base")
    return _enc


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text or ""))


# ---------------------------------------------------------------- extraction
def extract_page_blocks(page) -> Tuple[List[str], str]:
    """Extract text blocks in column-aware reading order."""
    blocks = page.get_text("blocks")
    sorted_blocks = sorted(blocks, key=lambda b: (round(b[0] / 50) * 50, b[1]))
    block_texts = []
    for b in sorted_blocks:
        if b[6] != 0:          # 0 = text block; skip image blocks
            continue
        t = re.sub(r"[ \t]+", " ", b[4]).strip()
        if t:
            block_texts.append(t)
    return block_texts, "\n\n".join(block_texts)


def classify_page(block_texts: List[str], page_tokens: int) -> str:
    if page_tokens <= CFG.SPARSE_MAX_TOKENS:
        return "sparse"
    if (page_tokens <= CFG.SLIDE_MAX_TOKENS_PER_PAGE
            and len(block_texts) >= CFG.SLIDE_MIN_BLOCKS):
        return "slide"
    return "text"


def load_pdfs(folder: str) -> list:
    """Load every PDF page as a Document with layout-aware text + a page_type tag."""
    import fitz  # PyMuPDF
    from langchain_core.documents import Document

    docs = []
    pdf_paths = sorted(glob.glob(os.path.join(folder, "*.pdf")))
    if not pdf_paths:
        print(f"      [rag] no PDF files in {folder}")
        return docs

    for path in pdf_paths:
        fname = os.path.basename(path)
        try:
            pdf = fitz.open(path)
        except Exception as e:
            print(f"      [rag] could not open {fname}: {e}")
            continue
        for i, page in enumerate(pdf):
            block_texts, page_text = extract_page_blocks(page)
            n_tokens = count_tokens(page_text)
            page_type = classify_page(block_texts, n_tokens)
            if len(page_text) < CFG.MIN_PAGE_CHARS:
                continue
            docs.append(Document(
                page_content=page_text,
                metadata={"source": fname, "page": i + 1, "path": path,
                          "page_type": page_type, "n_blocks": len(block_texts),
                          "n_tokens": n_tokens},
            ))
        pdf.close()
    print(f"      [rag] loaded {len(docs)} page-documents from {len(pdf_paths)} PDF(s)")
    return docs


# ---------------------------------------------------------------- chunking
SECTION_PATTERN = re.compile(
    r"^[ \t]*(#{1,4}\s+.{2,80}"                                # markdown headers
    r"|(?:Heading|Problem|Solution|Method(?:ology)?|Result(?:s)?|Objective|Overview"
    r"|Tech\s*(?:Tools?|Stack)|Tools(?:\s+used)?|Technologies|Business\s+Value"
    r"|Challenges?|Introduction|Background|Conclusion|Summary|Approach"
    r"|Key\s+(?:Findings|Takeaways|Results)|Impact|Outcome[s]?)\s*[:：]?"
    r"|[A-Z][A-Z &/-]{4,60})[ \t]*$",
    re.MULTILINE,
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def split_by_sections(text: str) -> List[Tuple[str, str]]:
    matches = list(SECTION_PATTERN.finditer(text))
    if not matches:
        return [("body", text.strip())]
    sections = []
    if matches[0].start() > 0:
        head = text[:matches[0].start()].strip()
        if head:
            sections.append(("intro", head))
    for i, m in enumerate(matches):
        name = m.group(1).strip().lstrip("#").strip().rstrip(":：").lower()[:60]
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((name, body))
    return sections or [("body", text.strip())]


def merge_small_sections(sections: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    merged, buffer_name, buffer_text = [], None, ""
    for name, body in sections:
        if buffer_text:
            name = f"{buffer_name} + {name}"[:60]
            body = f"{buffer_text}\n\n{body}"
            buffer_name, buffer_text = None, ""
        if count_tokens(body) < CFG.CHUNK_MIN_TOKENS:
            buffer_name, buffer_text = name, body
        else:
            merged.append((name, body))
    if buffer_text:
        if merged:
            last_name, last_body = merged[-1]
            merged[-1] = (last_name, f"{last_body}\n\n{buffer_text}")
        else:
            merged.append((buffer_name, buffer_text))
    return merged


def split_oversized(name: str, body: str) -> List[Tuple[str, str]]:
    if count_tokens(body) <= CFG.CHUNK_MAX_TOKENS:
        return [(name, body)]
    units = [p.strip() for p in body.split("\n\n") if p.strip()]
    if len(units) <= 1:
        units = [s.strip() for s in SENTENCE_SPLIT.split(body) if s.strip()]
    if len(units) <= 1:
        return [(name, body)]
    parts, current = [], ""
    for u in units:
        candidate = f"{current}\n\n{u}".strip() if current else u
        if count_tokens(candidate) > CFG.CHUNK_TARGET_TOKENS and current:
            parts.append(current)
            current = u
        else:
            current = candidate
    if current:
        parts.append(current)
    return [(f"{name} ({i+1}/{len(parts)})" if len(parts) > 1 else name, p)
            for i, p in enumerate(parts)]


def chunk_text_page(text: str) -> List[Tuple[str, str]]:
    sections = merge_small_sections(split_by_sections(text))
    out = []
    for name, body in sections:
        out.extend(split_oversized(name, body))
    return out


def chunk_slide_page(text: str) -> List[Tuple[str, str]]:
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    if not blocks:
        return [("slide", text)]
    chunks, current = [], ""
    for b in blocks:
        candidate = f"{current}\n\n{b}".strip() if current else b
        if count_tokens(candidate) > CFG.CHUNK_TARGET_TOKENS and current:
            chunks.append(current)
            current = b
        else:
            current = candidate
    if current:
        chunks.append(current)
    return [(f"slide part {i+1}" if len(chunks) > 1 else "slide", c)
            for i, c in enumerate(chunks)]


def build_chunks(raw_docs: list):
    """Build the parent store and child chunks for the whole corpus."""
    from langchain_core.documents import Document
    parent_docs: Dict[str, Any] = {}
    child_chunks: list = []
    for doc in raw_docs:
        meta = doc.metadata
        parent_id = f"{meta['source']}::p{meta['page']}"
        page_type = meta["page_type"]
        first_line = next((l.strip() for l in doc.page_content.split("\n") if l.strip()), "")
        title = first_line[:90] or f"Untitled {parent_id}"
        parent_docs[parent_id] = Document(
            page_content=doc.page_content,
            metadata={**meta, "parent_id": parent_id, "title": title})
        if page_type == "slide":
            sections = chunk_slide_page(doc.page_content)
        elif page_type == "sparse":
            sections = [("sparse page", doc.page_content)]
        else:
            sections = chunk_text_page(doc.page_content)
        for sec_name, sec_text in sections:
            breadcrumb = f"Document: {title} | Section: {sec_name}"
            child_chunks.append(Document(
                page_content=f"{breadcrumb}\n\n{sec_text}",
                metadata={"parent_id": parent_id, "title": title, "section": sec_name,
                          "source": meta["source"], "page": meta["page"],
                          "page_type": page_type}))
    return parent_docs, child_chunks


# ---------------------------------------------------------------- index + retrieval
def build_index(folder: Optional[str] = None) -> bool:
    """Build the hybrid (FAISS + BM25) index ONCE. Returns True if ready."""
    if _STATE["ready"]:
        return True
    if _STATE["error"]:                 # already tried and failed; don't loop
        return False
    folder = folder or CFG.RAW_FOLDER
    try:
        from langchain_openai import OpenAIEmbeddings
        from langchain_community.vectorstores import FAISS
        from langchain_community.retrievers import BM25Retriever
        try:
            from langchain.retrievers import EnsembleRetriever
        except ImportError:
            from langchain_classic.retrievers import EnsembleRetriever
    except Exception as e:
        _STATE["error"] = f"RAG dependencies missing ({e})"
        print(f"      [rag] {_STATE['error']} - install rag extras (see requirements.txt)")
        return False

    raw = load_pdfs(folder)
    if not raw:
        _STATE["error"] = f"no usable PDFs in {folder}"
        return False
    parents, children = build_chunks(raw)
    if not children:
        _STATE["error"] = "no chunks produced"
        return False

    emb = OpenAIEmbeddings(model=CFG.EMBED_MODEL)
    vs = FAISS.from_documents(children, emb)
    dense = vs.as_retriever(search_kwargs={"k": CFG.DENSE_K})
    bm25 = BM25Retriever.from_documents(children)
    bm25.k = CFG.BM25_K
    hybrid = EnsembleRetriever(retrievers=[dense, bm25],
                               weights=[CFG.DENSE_WEIGHT, CFG.BM25_WEIGHT])
    _STATE.update(ready=True, parents=parents, hybrid=hybrid,
                  vectorstore=vs, bm25=bm25, error=None)
    print(f"      [rag] index ready: {len(parents)} parents / {len(children)} chunks "
          f"from {folder}")
    return True


def retrieve(query: str, top_parents: Optional[int] = None) -> list:
    """Hybrid retrieval -> parent expansion. Returns full parent Documents."""
    if not build_index():
        return []
    top_parents = top_parents or CFG.TOP_PARENTS
    fused = _STATE["hybrid"].invoke(query)
    seen, parents = set(), []
    for doc in fused:
        pid = doc.metadata.get("parent_id")
        if pid and pid not in seen and pid in _STATE["parents"]:
            seen.add(pid)
            parents.append(_STATE["parents"][pid])
        if len(parents) >= top_parents:
            break
    return parents


def rag_sources(subject: str, market: str = "", max_docs: int = 6) -> List[Dict[str, Any]]:
    """Faceted retrieval over the internal collection, mapped to the agent's
    source-dict shape. Returns [] when the index is unavailable (no PDFs / deps)."""
    if not build_index():
        return []
    subj = (subject or market or "").strip()
    queries = [
        f"{subj} overview company services capabilities",
        f"{subj} case studies projects clients results",
        f"{subj} products offerings pricing",
        f"{subj} competitors market positioning differentiators",
    ]
    seen, out = set(), []
    for q in queries:
        for p in retrieve(q, top_parents=CFG.TOP_PARENTS):
            pid = p.metadata.get("parent_id")
            if pid in seen:
                continue
            seen.add(pid)
            src = p.metadata.get("source", "internal-doc")
            page = p.metadata.get("page", "")
            out.append({
                "title": p.metadata.get("title") or src,
                "url": f"doc://{src}#p{page}",
                "domain": src,
                "snippet": (p.page_content or "")[:300],
                "raw": (p.page_content or "")[:1800],
                "official": True,
            })
            if len(out) >= max_docs:
                break
        if len(out) >= max_docs:
            break
    return out
