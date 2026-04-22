"""
connectors/github_connector.py
GitHub integration — syncs MV BASIC source files from a GitHub repo
into the local mv_source/ folder, then triggers reindex.

Requires in .env:
    GITHUB_TOKEN     — Personal Access Token (repo or public_repo scope)
    GITHUB_REPO      — e.g. "your-org/your-repo"
    GITHUB_BRANCH    — e.g. "main"
    GITHUB_MV_FOLDER — folder inside repo containing MV BASIC files
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from github import Github, GithubException

from config import (
    GITHUB_TOKEN,
    GITHUB_REPO,
    GITHUB_BRANCH,
    GITHUB_MV_FOLDER,
    SYNC_META_PATH,
)
from connectors._cache import ttl_cache


# ── Client ─────────────────────────────────────────────────────────────────────

def _get_client() -> Github:
    if not GITHUB_TOKEN:
        raise ValueError(
            "GITHUB_TOKEN is not set. Add it to your .env file.\n"
            "Create a token at: GitHub → Settings → Developer settings → PAT"
        )
    return Github(GITHUB_TOKEN)


def _get_repo():
    if not GITHUB_REPO:
        raise ValueError(
            "GITHUB_REPO is not set. Add it to your .env file.\n"
            "Format: 'your-org/your-repo-name'"
        )
    g = _get_client()
    try:
        return g.get_repo(GITHUB_REPO)
    except GithubException as e:
        raise RuntimeError(
            f"Cannot access repo '{GITHUB_REPO}': {e.data.get('message', str(e))}\n"
            "Check GITHUB_TOKEN has the correct scopes and GITHUB_REPO is correct."
        )


# ── Repo info ──────────────────────────────────────────────────────────────────

def get_repo_info() -> dict:
    """Return basic repo metadata for display in the UI."""
    repo = _get_repo()
    return {
        "name":      repo.name,
        "full_name": repo.full_name,
        "branch":    GITHUB_BRANCH,
        "folder":    GITHUB_MV_FOLDER,
        "private":   repo.private,
        "last_push": (
            repo.pushed_at.strftime("%Y-%m-%d %H:%M UTC")
            if repo.pushed_at else "unknown"
        ),
    }


# ── File listing ───────────────────────────────────────────────────────────────

def list_remote_files() -> list[dict]:
    """
    List all files in GITHUB_MV_FOLDER on GITHUB_BRANCH.
    Returns list of {name, path, sha, size} dicts.
    """
    repo = _get_repo()
    try:
        contents = repo.get_contents(GITHUB_MV_FOLDER, ref=GITHUB_BRANCH)
    except GithubException as e:
        raise RuntimeError(
            f"Cannot list folder '{GITHUB_MV_FOLDER}' in repo '{GITHUB_REPO}': "
            f"{e.data.get('message', str(e))}\n"
            "Check GITHUB_MV_FOLDER is correct."
        )
    return [
        {
            "name": f.name,
            "path": f.path,
            "sha":  f.sha,
            "size": f.size,
        }
        for f in contents
        if f.type == "file"
    ]


# ── Sync ───────────────────────────────────────────────────────────────────────

def sync_to_local(local_dir: str = "./mv_source") -> dict:
    """
    Download all MV BASIC files from GitHub into local_dir.

    Returns:
        {
            synced:  [list of filenames successfully downloaded],
            skipped: [list of filenames skipped (unchanged)],
            errors:  [list of {file, error} dicts],
            total:   int,
        }
    """
    repo   = _get_repo()
    target = Path(local_dir)
    target.mkdir(parents=True, exist_ok=True)

    result = {"synced": [], "skipped": [], "errors": [], "total": 0}

    try:
        contents = repo.get_contents(GITHUB_MV_FOLDER, ref=GITHUB_BRANCH)
    except GithubException as e:
        raise RuntimeError(
            f"Cannot access '{GITHUB_MV_FOLDER}' in '{GITHUB_REPO}': "
            f"{e.data.get('message', str(e))}"
        )

    files = [f for f in contents if f.type == "file"]
    result["total"] = len(files)

    for remote_file in files:
        local_path = target / remote_file.name
        try:
            content = remote_file.decoded_content.decode("utf-8", errors="ignore")

            # Skip if file is identical (compare by SHA)
            sha_cache = _load_sync_meta().get("file_shas", {})
            if local_path.exists() and sha_cache.get(remote_file.name) == remote_file.sha:
                result["skipped"].append(remote_file.name)
                continue

            local_path.write_text(content, encoding="utf-8")
            result["synced"].append(remote_file.name)

        except Exception as e:
            result["errors"].append({"file": remote_file.name, "error": str(e)})

    _save_sync_meta(result)
    return result


# ── Commit history ─────────────────────────────────────────────────────────────

@ttl_cache(ttl_seconds=120)
def get_file_commits(filename: str, max_commits: int = 10) -> list[dict]:
    """Commit history for a specific MV BASIC file."""
    repo   = _get_repo()
    path   = f"{GITHUB_MV_FOLDER}/{filename}"
    result = []
    try:
        for i, commit in enumerate(repo.get_commits(path=path, sha=GITHUB_BRANCH)):
            if i >= max_commits:
                break
            result.append({
                "sha":     commit.sha[:7],
                "message": commit.commit.message.split("\n")[0],
                "author":  commit.author.login if commit.author else commit.commit.author.name,
                "date":    commit.commit.author.date.strftime("%Y-%m-%d %H:%M"),
                "url":     commit.html_url,
            })
    except Exception:
        pass
    return result


@ttl_cache(ttl_seconds=120)
def get_recent_repo_commits(max_commits: int = 20) -> list[dict]:
    """Most recent commits across the entire repo."""
    repo   = _get_repo()
    result = []
    try:
        for i, commit in enumerate(repo.get_commits(sha=GITHUB_BRANCH)):
            if i >= max_commits:
                break
            try:
                files_changed = [f.filename for f in commit.files]
            except Exception:
                files_changed = []
            mv_files = [
                f.split("/")[-1] for f in files_changed
                if GITHUB_MV_FOLDER in f
            ]
            result.append({
                "sha":         commit.sha[:7],
                "message":     commit.commit.message.split("\n")[0],
                "author":      commit.author.login if commit.author else commit.commit.author.name,
                "date":        commit.commit.author.date.strftime("%Y-%m-%d %H:%M"),
                "mv_files":    mv_files,
                "total_files": len(files_changed),
                "url":         commit.html_url,
            })
    except Exception:
        pass
    return result


def get_commit_details(sha: str) -> dict:
    """Full details of a specific commit — files changed, additions, deletions."""
    repo   = _get_repo()
    commit = repo.get_commit(sha)
    return {
        "sha":       commit.sha[:7],
        "message":   commit.commit.message,
        "author":    commit.author.login if commit.author else commit.commit.author.name,
        "date":      commit.commit.author.date.strftime("%Y-%m-%d %H:%M"),
        "url":       commit.html_url,
        "stats": {
            "additions": commit.stats.additions,
            "deletions": commit.stats.deletions,
            "total":     commit.stats.total,
        },
        "files": [
            {
                "filename":  f.filename.split("/")[-1],
                "status":    f.status,          # added / modified / removed
                "additions": f.additions,
                "deletions": f.deletions,
                "patch":     f.patch[:500] if f.patch else "",
            }
            for f in commit.files
        ],
    }


@ttl_cache(ttl_seconds=300)
def get_contributors() -> list[dict]:
    """List all contributors with commit counts."""
    repo   = _get_repo()
    result = []
    for contributor in repo.get_contributors():
        result.append({
            "login":   contributor.login,
            "name":    contributor.name or contributor.login,
            "commits": contributor.contributions,
            "url":     contributor.html_url,
        })
    return result


def get_file_last_changed(filename: str) -> dict:
    """Who last changed a specific subroutine and when."""
    commits = get_file_commits(filename, max_commits=1)
    if not commits:
        return {"error": f"No commit history found for '{filename}'"}
    last = commits[0]
    return {
        "file":    filename,
        "last_changed_by":   last["author"],
        "last_changed_date": last["date"],
        "commit_message":    last["message"],
        "sha":               last["sha"],
        "url":               last["url"],
    }


def search_commits_by_author(author_name: str, max_commits: int = 20) -> list[dict]:
    """Find all commits by a specific author."""
    all_commits = get_recent_repo_commits(max_commits=100)
    matched = [c for c in all_commits if author_name.lower() in c["author"].lower()]
    return matched[:max_commits]


# ── Sync metadata (SHA cache + timestamps) ─────────────────────────────────────

def _load_sync_meta() -> dict:
    if os.path.exists(SYNC_META_PATH):
        with open(SYNC_META_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_sync_meta(sync_result: dict):
    meta = _load_sync_meta()

    # Rebuild SHA cache from all currently tracked files
    file_shas = meta.get("file_shas", {})
    repo      = _get_repo()
    try:
        contents = repo.get_contents(GITHUB_MV_FOLDER, ref=GITHUB_BRANCH)
        for f in contents:
            if f.type == "file":
                file_shas[f.name] = f.sha
    except Exception:
        pass

    meta.update({
        "last_sync":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "repo":         GITHUB_REPO,
        "branch":       GITHUB_BRANCH,
        "folder":       GITHUB_MV_FOLDER,
        "files_synced": len(sync_result.get("synced", [])),
        "files_total":  sync_result.get("total", 0),
        "file_shas":    file_shas,
    })

    with open(SYNC_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)


def get_last_sync_info() -> dict:
    """Return last sync metadata for display in the UI."""
    meta = _load_sync_meta()
    return {
        "last_sync":    meta.get("last_sync", "Never"),
        "repo":         meta.get("repo", GITHUB_REPO or "not configured"),
        "branch":       meta.get("branch", GITHUB_BRANCH),
        "folder":       meta.get("folder", GITHUB_MV_FOLDER),
        "files_synced": meta.get("files_synced", 0),
        "files_total":  meta.get("files_total", 0),
    }
