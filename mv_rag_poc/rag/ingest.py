"""
rag/ingest.py
RAG corpus ingestion — accepts ALL files in mv_source regardless of extension.
MV files like ORD.PROCESS have .PROCESS as suffix — accepted by passing extensions=None.
"""

from pathlib import Path
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from config import MV_SYNTAX_DIR, EMBED_MODEL


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


def ingest_corpus(
    source_dir: str,
    docs_dir: str,
    chroma_path: str = "./chroma_db",
) -> Chroma:
    """
    Load, chunk, embed, and store into ChromaDB:
      • MV BASIC source files  (mv_source/)
      • Dict layout .txt files (documents/)
      • MV syntax PDF manuals  (documents/mv_syntax/)
    """
    embeddings = OllamaEmbeddings(model=EMBED_MODEL)
    docs = []

    # ── MV BASIC source files ─────────────────────────────────────────────────
    source_docs = _load_text_files(source_dir, extensions=None)
    if source_docs:
        for d in source_docs:
            d.metadata["source_type"] = "source_code"
        print(f"  Loaded {len(source_docs)} MV BASIC source files")
        docs += source_docs
    else:
        print(f"  WARNING: No source files found in {source_dir}")

    # ── Dict layout .txt files ────────────────────────────────────────────────
    txt_docs = _load_text_files(docs_dir, extensions=[".txt"])
    if txt_docs:
        for d in txt_docs:
            d.metadata["source_type"] = "document"
        print(f"  Loaded {len(txt_docs)} .txt documents")
        docs += txt_docs

    # ── MV syntax PDF manuals ─────────────────────────────────────────────────
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

    # ── Chunking ──────────────────────────────────────────────────────────────
    # Source code: split at subroutine boundaries, larger chunks
    code_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=["\nSUBROUTINE ", "\nFUNCTION ", "\n$INSERT ", "\n* ", "\n!", "\n"],
    )
    # Syntax docs: smaller chunks so syntax examples are retrieved precisely
    syntax_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " "],
    )

    code_chunks   = code_splitter.split_documents(
        [d for d in docs if d.metadata.get("source_type") == "source_code"]
    )
    other_chunks  = syntax_splitter.split_documents(
        [d for d in docs if d.metadata.get("source_type") != "source_code"]
    )

    all_chunks = code_chunks + other_chunks
    print(f"  Split into {len(all_chunks)} total chunks "
          f"({len(code_chunks)} code, {len(other_chunks)} docs/syntax)")

    print(f"  Embedding with {EMBED_MODEL} — this may take several minutes for PDFs...")
    vectorstore = Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=chroma_path,
    )

    print(f"  ChromaDB persisted to {chroma_path}")
    return vectorstore