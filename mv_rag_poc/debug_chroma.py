"""
debug_chroma.py
Run this to diagnose why certain subroutines are not found in ChromaDB.

Usage:
    python debug_chroma.py
"""

import os
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma

# ── Config ─────────────────────────────────────────────────────────────────────
CHROMA_PATH      = "./chroma_db"
SOURCE_FILE_PATH = "mv_source"

SUBROUTINES = [
    "CHECK.INVENTORY",
    "CUSTOMER.LOOKUP",
    "GET.CUSTOMER.INFO",
    "GET.ORDER.DETAILS",
    "INV.UPDATE",
    "ORD.PROCESS",
    "ORD.VALIDATE",
    "ORDER.LOOKUP",
]

def run_diagnostic():
    print("=" * 60)
    print("STEP 1 — Check source files exist on disk")
    print("=" * 60)
    for sub in SUBROUTINES:
        fpath = os.path.join(SOURCE_FILE_PATH, sub)
        exists = os.path.isfile(fpath)
        size   = os.path.getsize(fpath) if exists else 0
        status = f"✓ EXISTS ({size} bytes)" if exists else "✗ MISSING"
        print(f"  {sub:<30} {status}")

    print()
    print("=" * 60)
    print("STEP 2 — Check ChromaDB collection contents")
    print("=" * 60)
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    vectorstore = Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=embeddings,
    )

    # Get all stored documents
    collection = vectorstore._collection
    all_docs = collection.get(include=["metadatas", "documents"])

    total = len(all_docs["ids"])
    print(f"  Total chunks in ChromaDB: {total}")
    print()

    # Check which subroutines have chunks
    print("  Chunks per subroutine:")
    for sub in SUBROUTINES:
        count = sum(
            1 for m in all_docs["metadatas"]
            if sub.upper() in m.get("source", "").upper()
        )
        status = f"✓ {count} chunk(s)" if count > 0 else "✗ NO CHUNKS FOUND"
        print(f"  {sub:<30} {status}")

    print()
    print("=" * 60)
    print("STEP 3 — Show all unique sources stored in ChromaDB")
    print("=" * 60)
    sources = sorted(set(
        m.get("source", "UNKNOWN")
        for m in all_docs["metadatas"]
    ))
    for s in sources:
        print(f"  {s}")

    print()
    print("=" * 60)
    print("STEP 4 — Test similarity search for each subroutine")
    print("=" * 60)
    for sub in SUBROUTINES:
        results = vectorstore.similarity_search(sub, k=3)
        print(f"\n  Query: '{sub}'")
        if results:
            for r in results:
                src = r.metadata.get("source", "unknown")
                preview = r.page_content[:80].replace("\n", " ")
                print(f"    → source: {src}")
                print(f"      preview: {preview}...")
        else:
            print(f"    ✗ No results returned")

    print()
    print("=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_diagnostic()