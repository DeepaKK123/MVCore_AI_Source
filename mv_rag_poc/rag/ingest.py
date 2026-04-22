"""
rag/ingest.py
RAG corpus ingestion — accepts ALL files in mv_source regardless of extension.
MV files like ORD.PROCESS have .PROCESS as suffix — accepted by passing extensions=None.

Supports both full and incremental ingest:
  * ingest_corpus(...)                 — full rebuild (default)
  * ingest_corpus(..., incremental=True) — only re-embeds files whose mtime
    has changed since the last ingest. PDFs never change, so they are skipped
    entirely on incremental runs.
"""

import json
import os
from pathlib import Path
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from config import MV_SYNTAX_DIR, EMBED_MODEL


INGEST_META_NAME = ".ingest_meta.json"


def _load_text_files(directory: str, extensions) -> list:
    """Load text files. extensions=None accepts every file."""
    docs = []
    path = Path(directory)
    if not path.exists():
        return docs
    for f in path.rglob("*"):
        if not f.is_file():
            continue
        if extensions is None or f.suffix.lower() in extensions:
            try:
                docs.extend(TextLoader(str(f), encoding="utf-8").load())
            except Exception:
                try:
                    docs.extend(TextLoader(str(f), encoding="latin-1").load())
                except Exception as e:
                    print(f"  WARNING: Could not load {f}: {e}")
    return docs


def _load_pdf_files(directory: str) -> list:
    """Load all PDF files from a directory using PyPDFLoader."""
    docs = []
    path = Path(directory)
    if not path.exists():
        return docs
    for f in path.rglob("*.pdf"):
        try:
            pages = PyPDFLoader(str(f)).load()
            for p in pages:
                p.metadata["source_type"] = "mv_syntax"
            docs.extend(pages)
            print(f"  Loaded PDF: {f.name} ({len(pages)} pages)")
        except Exception as e:
            print(f"  WARNING: Could not load PDF {f.name}: {e}")
    return docs


def _scan_mtimes(directory: str, extensions=None) -> dict:
    """Return {absolute_path: mtime} for every file in directory matching extensions."""
    out: dict[str, float] = {}
    path = Path(directory)
    if not path.exists():
        return out
    for f in path.rglob("*"):
        if not f.is_file():
            continue
        if extensions is None or f.suffix.lower() in extensions:
            try:
                out[str(f.resolve())] = f.stat().st_mtime
            except OSError:
                pass
    return out


def _load_ingest_meta(chroma_path: str) -> dict:
    meta_path = os.path.join(chroma_path, INGEST_META_NAME)
    if not os.path.exists(meta_path):
        return {}
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_ingest_meta(chroma_path: str, meta: dict) -> None:
    os.makedirs(chroma_path, exist_ok=True)
    meta_path = os.path.join(chroma_path, INGEST_META_NAME)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def _chunk_docs(docs: list) -> list:
    """Split docs with the right chunker per source_type."""
    code_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\nSUBROUTINE ", "\nFUNCTION ", "\n$INSERT ", "\n* ", "\n!", "\n"],
    )
    syntax_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " "],
    )
    code_chunks  = code_splitter.split_documents(
        [d for d in docs if d.metadata.get("source_type") == "source_code"]
    )
    other_chunks = syntax_splitter.split_documents(
        [d for d in docs if d.metadata.get("source_type") != "source_code"]
    )
    return code_chunks + other_chunks


def ingest_corpus(
    source_dir: str,
    docs_dir: str,
    chroma_path: str = "./chroma_db",
    incremental: bool = False,
) -> Chroma:
    """
    Load, chunk, embed, and store into ChromaDB:
      • MV BASIC source files  (mv_source/)
      • Dict layout .txt files (documents/)
      • MV syntax PDF manuals  (documents/mv_syntax/)

    incremental=True: only re-embed files whose mtime changed since the last
    ingest. PDFs (mv_syntax) are skipped entirely on incremental runs.
    """
    embeddings = OllamaEmbeddings(model=EMBED_MODEL)

    # ── Scan mtimes for change detection ─────────────────────────────────────
    current_mtimes: dict[str, float] = {}
    current_mtimes.update(_scan_mtimes(source_dir, extensions=None))
    current_mtimes.update(_scan_mtimes(docs_dir, extensions=[".txt"]))
    current_mtimes.update(_scan_mtimes(MV_SYNTAX_DIR, extensions=[".pdf"]))

    prev_meta    = _load_ingest_meta(chroma_path) if incremental else {}
    prev_mtimes  = prev_meta.get("mtimes", {}) if isinstance(prev_meta, dict) else {}

    if incremental:
        changed = {
            p for p, mt in current_mtimes.items()
            if prev_mtimes.get(p) != mt
        }
        removed = set(prev_mtimes) - set(current_mtimes)

        if not changed and not removed:
            print("  Nothing changed — skipping ingest.")
            return Chroma(persist_directory=chroma_path, embedding_function=embeddings)

        print(f"  Incremental: {len(changed)} changed, {len(removed)} removed")

        # Open existing store
        vectorstore = Chroma(persist_directory=chroma_path, embedding_function=embeddings)

        # Delete old chunks for changed + removed files
        stale_sources = list(changed | removed)
        # Chroma's delete supports a where filter keyed on metadata. The source
        # field stored by TextLoader/PyPDFLoader is the absolute path.
        for src in stale_sources:
            try:
                vectorstore.delete(where={"source": src})
            except Exception as e:
                print(f"  WARNING: could not delete stale chunks for {src}: {e}")

        # Load only the changed files (skip PDFs unless they changed)
        docs = []
        for p in changed:
            pl = Path(p)
            low = pl.suffix.lower()
            try:
                if low == ".pdf":
                    pages = PyPDFLoader(str(pl)).load()
                    for page in pages:
                        page.metadata["source_type"] = "mv_syntax"
                    docs.extend(pages)
                elif low == ".txt" and str(pl.resolve()).startswith(str(Path(docs_dir).resolve())):
                    loaded = TextLoader(str(pl), encoding="utf-8").load()
                    for d in loaded:
                        d.metadata["source_type"] = "document"
                    docs.extend(loaded)
                else:
                    # Treat as MV source
                    try:
                        loaded = TextLoader(str(pl), encoding="utf-8").load()
                    except Exception:
                        loaded = TextLoader(str(pl), encoding="latin-1").load()
                    for d in loaded:
                        d.metadata["source_type"] = "source_code"
                    docs.extend(loaded)
            except Exception as e:
                print(f"  WARNING: Could not load {pl}: {e}")

        if docs:
            chunks = _chunk_docs(docs)
            print(f"  Embedding {len(chunks)} chunks for {len(docs)} changed doc(s)...")
            vectorstore.add_documents(chunks)

        _save_ingest_meta(chroma_path, {"mtimes": current_mtimes})
        print(f"  Incremental ingest complete. ChromaDB at {chroma_path}")
        return vectorstore

    # ── Full rebuild path ────────────────────────────────────────────────────
    docs = []

    source_docs = _load_text_files(source_dir, extensions=None)
    if source_docs:
        for d in source_docs:
            d.metadata["source_type"] = "source_code"
        print(f"  Loaded {len(source_docs)} MV BASIC source files")
        docs += source_docs
    else:
        print(f"  WARNING: No source files found in {source_dir}")

    txt_docs = _load_text_files(docs_dir, extensions=[".txt"])
    if txt_docs:
        for d in txt_docs:
            d.metadata["source_type"] = "document"
        print(f"  Loaded {len(txt_docs)} .txt documents")
        docs += txt_docs

    pdf_docs = _load_pdf_files(MV_SYNTAX_DIR)
    if pdf_docs:
        print(f"  Loaded {len(pdf_docs)} pages from MV syntax PDFs")
        docs += pdf_docs
    else:
        print(f"  WARNING: No PDFs found in {MV_SYNTAX_DIR}")

    if not docs:
        raise RuntimeError(
            "No documents loaded. Add MV BASIC files to mv_source/ "
            "and PDF syntax manuals to documents/mv_syntax/"
        )

    all_chunks = _chunk_docs(docs)
    code_count  = sum(1 for d in docs if d.metadata.get("source_type") == "source_code")
    print(f"  Split into {len(all_chunks)} total chunks "
          f"({code_count} source docs, {len(docs) - code_count} docs/syntax pages)")

    print(f"  Embedding with {EMBED_MODEL} — this may take several minutes for PDFs...")
    vectorstore = Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=chroma_path,
    )

    _save_ingest_meta(chroma_path, {"mtimes": current_mtimes})
    print(f"  ChromaDB persisted to {chroma_path}")
    return vectorstore
