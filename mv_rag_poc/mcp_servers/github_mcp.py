"""
mcp_servers/github_mcp.py
Read-only GitHub MCP Server for the MV AI Knowledge Hub.

Exposes GitHub history and metadata as MCP tools the LLM can call.
NO write operations — information only.

Tools exposed:
  - get_file_history      : commit history for a specific subroutine
  - get_file_last_changed : who last changed a subroutine and when
  - get_recent_commits    : recent commits across the whole repo
  - get_commit_details    : full details of a specific commit
  - get_contributors      : list all contributors with commit counts
  - search_commits_by_author : find commits by a specific developer

Run standalone:
    python -m mcp_servers.github_mcp

Or register in Claude Code (claude_desktop_config.json):
    {
      "mcpServers": {
        "mv-github": {
          "command": "python",
          "args": ["-m", "mcp_servers.github_mcp"],
          "cwd": "<path-to-mv_rag_poc>"
        }
      }
    }
"""

import json
import sys
import os

# Add project root to path so config/connectors are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from connectors.github_connector import (
    get_file_commits,
    get_file_last_changed,
    get_recent_repo_commits,
    get_commit_details,
    get_contributors,
    search_commits_by_author,
    get_repo_info,
)
from config import github_configured

server = Server("mv-github-readonly")


# ── Tool definitions ───────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_file_history",
            description=(
                "Get the commit history for a specific MV BASIC subroutine file. "
                "Use when asked: 'What changed in X?', 'Show me the history of X', "
                "'How many times was X modified?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Subroutine filename e.g. UPDATE.ORDER, ORD.PROCESS",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Max commits to return (default 10)",
                        "default": 10,
                    },
                },
                "required": ["filename"],
            },
        ),
        types.Tool(
            name="get_file_last_changed",
            description=(
                "Find out who last changed a subroutine and when. "
                "Use when asked: 'Who last modified X?', 'When was X last updated?', "
                "'Who wrote X?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Subroutine filename e.g. UPDATE.ORDER",
                    },
                },
                "required": ["filename"],
            },
        ),
        types.Tool(
            name="get_recent_commits",
            description=(
                "Get the most recent commits across the whole repository. "
                "Use when asked: 'What changed recently?', 'What happened last week?', "
                "'Show me recent activity', 'What was changed in the last sprint?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "max_commits": {
                        "type": "integer",
                        "description": "Max commits to return (default 20)",
                        "default": 20,
                    },
                },
            },
        ),
        types.Tool(
            name="get_commit_details",
            description=(
                "Get full details of a specific commit including files changed, "
                "lines added/deleted, and code diffs. "
                "Use when asked about a specific commit SHA."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sha": {
                        "type": "string",
                        "description": "Commit SHA (full or first 7 chars)",
                    },
                },
                "required": ["sha"],
            },
        ),
        types.Tool(
            name="get_contributors",
            description=(
                "List all contributors to the codebase with their commit counts. "
                "Use when asked: 'Who works on this codebase?', 'Who are the developers?', "
                "'Who has the most commits?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="search_commits_by_author",
            description=(
                "Find all recent commits made by a specific developer. "
                "Use when asked: 'What did John change?', 'Show me commits by Sarah'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "author_name": {
                        "type": "string",
                        "description": "Developer name or partial name to search",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Max commits to return (default 20)",
                        "default": 20,
                    },
                },
                "required": ["author_name"],
            },
        ),
    ]


# ── Tool execution ─────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if not github_configured():
        return [types.TextContent(
            type="text",
            text="GitHub is not configured. Add GITHUB_TOKEN and GITHUB_REPO to .env",
        )]

    try:
        if name == "get_file_history":
            result = get_file_commits(
                arguments["filename"],
                max_commits=arguments.get("max_commits", 10),
            )
        elif name == "get_file_last_changed":
            result = get_file_last_changed(arguments["filename"])
        elif name == "get_recent_commits":
            result = get_recent_repo_commits(
                max_commits=arguments.get("max_commits", 20),
            )
        elif name == "get_commit_details":
            result = get_commit_details(arguments["sha"])
        elif name == "get_contributors":
            result = get_contributors()
        elif name == "search_commits_by_author":
            result = search_commits_by_author(
                arguments["author_name"],
                max_commits=arguments.get("max_commits", 20),
            )
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {e}")]


# ── Entry point ────────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
