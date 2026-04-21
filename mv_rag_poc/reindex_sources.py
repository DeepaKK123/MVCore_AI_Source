"""
reindex_sources.py
Clears and rebuilds the ChromaDB vector store from scratch.
Ensures ALL subroutines in mv_source are indexed with correct metadata.

Usage:
    python reindex_sources.py
"""

import os
import shutil

from langchain_text_splitters import RecursiveCharacterTextSplitter   # ✅ fixed
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

# ── Config ─────────────────────────────────────────────────────────────────────
CHROMA_PATH      = "./chroma_db"
SOURCE_FILE_PATH = "mv_source"

# For MV BASIC — keep chunks large so subroutine context is preserved
TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=200,
    separators=["\nSUBROUTINE ", "\nFUNCTION ", "\n\n", "\n", " "],
)


def load_all_sources(source_path: str) -> list[Document]:
    """
    Load ALL files from mv_source folder as LangChain Documents.
    Sets 'source' metadata to the UPPERCASE filename for reliable matching.
    """
    docs = []
    if not os.path.isdir(source_path):
        print(f"✗ Source path not found: {source_path}")
        return docs

    files = [
        f for f in os.listdir(source_path)
        if os.path.isfile(os.path.join(source_path, f))
    ]

    print(f"  Found {len(files)} source files:")
    for fname in sorted(files):
        fpath = os.path.join(source_path, fname)
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()

            if not content:
                print(f"  ⚠ EMPTY: {fname} — skipping")
                continue

            # Split into chunks
            chunks = TEXT_SPLITTER.create_documents(
                texts=[content],
                metadatas=[{
                    "source":    fname.upper(),  # ← KEY: uppercase for matching
                    "filename":  fname,
                    "filepath":  fpath,
                    "file_type": "mv_basic_source",
                }]
            )

            print(f"  ✓ {fname:<30} → {len(chunks)} chunk(s)  ({len(content)} chars)")
            docs.extend(chunks)

        except Exception as e:
            print(f"  ✗ ERROR reading {fname}: {e}")

    return docs


def rebuild_chroma(docs: list[Document], chroma_path: str) -> Chroma:
    """
    Delete existing ChromaDB and rebuild from scratch.
    """
    # Backup and delete old DB
    if os.path.exists(chroma_path):
        backup = chroma_path + "_backup"
        if os.path.exists(backup):
            shutil.rmtree(backup)
        shutil.copytree(chroma_path, backup)
        shutil.rmtree(chroma_path)
        print(f"  Old ChromaDB deleted (backup saved at {backup})")

    print(f"  Building new ChromaDB with {len(docs)} chunks ...")
    embeddings = OllamaEmbeddings(model="nomic-embed-text")

    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=chroma_path,
    )

    print(f"  ✓ ChromaDB rebuilt at: {chroma_path}")
    return vectorstore


def verify_index(vectorstore: Chroma, source_path: str):
    """
    Verify all source files have chunks in the new index.
    """
    print()
    print("=" * 60)
    print("VERIFICATION — Chunks per subroutine")
    print("=" * 60)

    collection = vectorstore._collection
    all_docs   = collection.get(include=["metadatas"])

    files = sorted([
        f.upper()
        for f in os.listdir(source_path)
        if os.path.isfile(os.path.join(source_path, f))
    ])

    all_ok = True
    for fname in files:
        count = sum(
            1 for m in all_docs["metadatas"]
            if fname in m.get("source", "").upper()
        )
        status = f"✓ {count} chunk(s)" if count > 0 else "✗ STILL MISSING"
        if count == 0:
            all_ok = False
        print(f"  {fname:<30} {status}")

    print()
    if all_ok:
        print("✅ All subroutines indexed successfully!")
    else:
        print("⚠️  Some subroutines still missing — check file contents.")


if __name__ == "__main__":
    print("=" * 60)
    print("RE-INDEXING MV SOURCE FILES INTO CHROMADB")
    print("=" * 60)
    print()

    print("STEP 1 — Loading source files ...")
    docs = load_all_sources(SOURCE_FILE_PATH)

    if not docs:
        print("✗ No documents loaded. Check SOURCE_FILE_PATH.")
        exit(1)

    print()
    print(f"STEP 2 — Total chunks to index: {len(docs)}")
    print()

    print("STEP 3 — Rebuilding ChromaDB ...")
    vectorstore = rebuild_chroma(docs, CHROMA_PATH)

    print()
    print("STEP 4 — Verifying index ...")
    verify_index(vectorstore, SOURCE_FILE_PATH)