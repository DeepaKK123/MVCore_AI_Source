"""
sync_now.py
One-shot CLI sync: pulls all UniBasic files from GitHub → mv_source/,
then rebuilds the dependency graph and ChromaDB index.

Usage:
    python sync_now.py
"""

import sys
from config import SOURCE_DIR, DOCS_DIR, GRAPH_PATH, CHROMA_PATH, github_configured
from connectors.github_connector import sync_to_local, get_last_sync_info, get_repo_info
from graph.dependency_graph import build_graph, save_graph
from rag.ingest import ingest_corpus


def main():
    print("=" * 60)
    print("  MV AI — GitHub Sync + Rebuild")
    print("=" * 60)

    # ── Check .env is configured ──────────────────────────────────────────────
    if not github_configured():
        print("\n✗ GitHub not configured. Add GITHUB_TOKEN and GITHUB_REPO to .env")
        sys.exit(1)

    # ── Show repo info ─────────────────────────────────────────────────────────
    print("\n[1/4] Connecting to GitHub...")
    try:
        info = get_repo_info()
        print(f"  ✓  Repo   : {info['full_name']}  ({'private' if info['private'] else 'public'})")
        print(f"  ✓  Branch : {info['branch']}")
        print(f"  ✓  Folder : {info['folder']}")
        print(f"  ✓  Last push: {info['last_push']}")
    except Exception as e:
        print(f"  ✗  Cannot connect to GitHub: {e}")
        sys.exit(1)

    # ── Sync files ────────────────────────────────────────────────────────────
    print(f"\n[2/4] Syncing UniBasic files → {SOURCE_DIR} ...")
    try:
        result = sync_to_local(SOURCE_DIR)
    except Exception as e:
        print(f"  ✗  Sync failed: {e}")
        sys.exit(1)

    print(f"  ✓  Synced  : {len(result['synced'])} file(s)")
    for f in result["synced"]:
        print(f"       + {f}")
    print(f"  ⊘  Skipped : {len(result['skipped'])} unchanged file(s)")
    if result["errors"]:
        for err in result["errors"]:
            print(f"  ✗  ERROR   : {err['file']} — {err['error']}")

    if not result["synced"] and not result["skipped"]:
        print("  ✗  No files found in the GitHub folder. Check GITHUB_MV_FOLDER in .env")
        sys.exit(1)

    # ── Rebuild dependency graph ───────────────────────────────────────────────
    print(f"\n[3/4] Rebuilding dependency graph...")
    try:
        G = build_graph(SOURCE_DIR)
        save_graph(G, GRAPH_PATH)
        print(f"  ✓  Graph: {G.number_of_nodes()} subroutines, {G.number_of_edges()} call edges")
    except Exception as e:
        print(f"  ✗  Graph build failed: {e}")
        sys.exit(1)

    # ── Re-index ChromaDB ─────────────────────────────────────────────────────
    print(f"\n[4/4] Re-indexing into ChromaDB (embedding — may take a few minutes)...")
    try:
        ingest_corpus(SOURCE_DIR, DOCS_DIR, chroma_path=CHROMA_PATH)
        print(f"  ✓  ChromaDB rebuilt at {CHROMA_PATH}")
    except Exception as e:
        print(f"  ✗  Ingest failed: {e}")
        sys.exit(1)

    # ── Done ──────────────────────────────────────────────────────────────────
    sync_info = get_last_sync_info()
    print("\n" + "=" * 60)
    print("  Sync complete!")
    print(f"  Files synced : {sync_info['files_synced']} / {sync_info['files_total']}")
    print(f"  Subroutines  : {G.number_of_nodes()} in graph")
    print("\n  Start the app:")
    print("    streamlit run app.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
