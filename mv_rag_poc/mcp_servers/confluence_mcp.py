"""
mcp_servers/confluence_mcp.py
Read-only Confluence MCP Server for the MV AI Knowledge Hub.

Tools exposed:
  - search_pages          : full-text search across Confluence
  - get_page_by_title     : get a specific page by title
  - get_pages_for_code    : find pages mentioning a subroutine
  - get_recent_pages      : recently updated pages
  - get_space_pages       : list all pages in the space
  - get_space_summary     : high-level space stats

Run standalone:
    python -m mcp_servers.confluence_mcp

Register in Claude Code (claude_desktop_config.json):
    {
      "mcpServers": {
        "mv-confluence": {
          "command": "python",
          "args": ["-m", "mcp_servers.confluence_mcp"],
          "cwd": "<path-to-mv_rag_poc>"
        }
      }
    }
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from connectors.confluence_connector import (
    search_pages,
    get_page_by_title,
    get_pages_for_subroutine,
    get_recent_pages,
    get_space_pages,
    get_space_summary,
)
from config import confluence_configured

server = Server("mv-confluence-readonly")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_pages",
            description=(
                "Full-text search across Confluence pages. "
                "Use when asked: 'Find documentation about X', "
                "'Is there a spec for the order process?', 'Find the runbook for Y'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query":       {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_page_by_title",
            description=(
                "Get a specific Confluence page by its title. "
                "Use when asked: 'Show me the Order Processing spec', "
                "'Get the design doc for Inventory'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Page title or partial title"},
                },
                "required": ["title"],
            },
        ),
        types.Tool(
            name="get_pages_for_code",
            description=(
                "Find Confluence pages that mention a specific MV BASIC subroutine. "
                "Use when asked: 'What docs exist for UPDATE.ORDER?', "
                "'Is there any documentation for ORD.PROCESS?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "subroutine_name": {
                        "type": "string",
                        "description": "Subroutine name e.g. UPDATE.ORDER",
                    },
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["subroutine_name"],
            },
        ),
        types.Tool(
            name="get_recent_pages",
            description=(
                "Get most recently updated Confluence pages. "
                "Use when asked: 'What docs were updated recently?', "
                "'Show latest wiki changes'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 10},
                },
            },
        ),
        types.Tool(
            name="get_space_pages",
            description=(
                "List all pages in the Confluence space. "
                "Use when asked: 'What documentation exists?', "
                "'List all wiki pages'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 50},
                },
            },
        ),
        types.Tool(
            name="get_space_summary",
            description=(
                "Get a high-level summary of the Confluence space. "
                "Use when asked: 'Tell me about the wiki', 'How much documentation do we have?'"
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if not confluence_configured():
        return [types.TextContent(
            type="text",
            text="Confluence not configured. Add JIRA_URL, JIRA_EMAIL, JIRA_TOKEN to .env",
        )]
    try:
        if name == "search_pages":
            result = search_pages(arguments["query"], arguments.get("max_results", 10))
        elif name == "get_page_by_title":
            result = get_page_by_title(arguments["title"])
        elif name == "get_pages_for_code":
            result = get_pages_for_subroutine(
                arguments["subroutine_name"], arguments.get("max_results", 5)
            )
        elif name == "get_recent_pages":
            result = get_recent_pages(arguments.get("max_results", 10))
        elif name == "get_space_pages":
            result = get_space_pages(arguments.get("max_results", 50))
        elif name == "get_space_summary":
            result = get_space_summary()
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {e}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
