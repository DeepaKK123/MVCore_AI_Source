"""
mcp_servers/jira_mcp.py
Read-only Jira MCP Server for the MV AI Knowledge Hub.

Exposes Jira tickets, epics, sprints and search as MCP tools.
NO write operations — information only.

Tools exposed:
  - get_ticket             : full details of a specific ticket
  - search_tickets         : JQL-based ticket search
  - get_tickets_for_code   : find tickets mentioning a subroutine name
  - get_recent_tickets     : recently updated tickets
  - get_sprint_tickets     : current sprint tickets
  - get_open_bugs          : all open bugs
  - get_tickets_by_assignee: tickets assigned to a person
  - get_project_summary    : high-level project stats

Run standalone:
    python -m mcp_servers.jira_mcp

Register in Claude Code (claude_desktop_config.json):
    {
      "mcpServers": {
        "mv-jira": {
          "command": "python",
          "args": ["-m", "mcp_servers.jira_mcp"],
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

from connectors.jira_connector import (
    get_ticket,
    search_tickets,
    get_tickets_for_subroutine,
    get_recent_tickets,
    get_sprint_tickets,
    get_open_bugs,
    get_tickets_by_assignee,
    get_project_summary,
)
from config import jira_configured

server = Server("mv-jira-readonly")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_ticket",
            description=(
                "Get full details of a specific Jira ticket including description, "
                "status, assignee, comments. Use when user mentions a ticket key like PROJ-123."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Jira ticket key e.g. PROJ-123"},
                },
                "required": ["key"],
            },
        ),
        types.Tool(
            name="search_tickets",
            description=(
                "Search Jira using JQL (Jira Query Language). "
                "Use for complex queries: by status, assignee, date range, labels etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "jql":         {"type": "string", "description": "JQL query string"},
                    "max_results": {"type": "integer", "default": 20},
                },
                "required": ["jql"],
            },
        ),
        types.Tool(
            name="get_tickets_for_code",
            description=(
                "Find Jira tickets that mention a specific MV BASIC subroutine name. "
                "Use when asked: 'What tickets relate to UPDATE.ORDER?', "
                "'Which stories mention ORD.PROCESS?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "subroutine_name": {
                        "type": "string",
                        "description": "Subroutine name e.g. UPDATE.ORDER",
                    },
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": ["subroutine_name"],
            },
        ),
        types.Tool(
            name="get_recent_tickets",
            description=(
                "Get most recently updated Jira tickets in the project. "
                "Use when asked: 'What tickets were worked on recently?', "
                "'Show me recent Jira activity'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 20},
                },
            },
        ),
        types.Tool(
            name="get_sprint_tickets",
            description=(
                "Get all tickets in the current active sprint. "
                "Use when asked: 'What are we working on this sprint?', "
                "'Show current sprint tickets'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 50},
                },
            },
        ),
        types.Tool(
            name="get_open_bugs",
            description=(
                "Get all open/unresolved bugs in the project. "
                "Use when asked: 'What bugs are open?', 'Show me known issues'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 20},
                },
            },
        ),
        types.Tool(
            name="get_tickets_by_assignee",
            description=(
                "Get open tickets assigned to a specific person. "
                "Use when asked: 'What is John working on?', 'Show tickets for Sarah'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "assignee_name": {"type": "string", "description": "Person's name"},
                    "max_results":   {"type": "integer", "default": 20},
                },
                "required": ["assignee_name"],
            },
        ),
        types.Tool(
            name="get_project_summary",
            description=(
                "Get high-level project stats: total tickets, open tickets, bugs, sprint count. "
                "Use when asked: 'How is the project doing?', 'Give me a project overview'"
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if not jira_configured():
        return [types.TextContent(
            type="text",
            text="Jira is not configured. Add JIRA_URL, JIRA_EMAIL, JIRA_TOKEN to .env",
        )]
    try:
        if name == "get_ticket":
            result = get_ticket(arguments["key"])
        elif name == "search_tickets":
            result = search_tickets(arguments["jql"], arguments.get("max_results", 20))
        elif name == "get_tickets_for_code":
            result = get_tickets_for_subroutine(
                arguments["subroutine_name"], arguments.get("max_results", 10)
            )
        elif name == "get_recent_tickets":
            result = get_recent_tickets(arguments.get("max_results", 20))
        elif name == "get_sprint_tickets":
            result = get_sprint_tickets(arguments.get("max_results", 50))
        elif name == "get_open_bugs":
            result = get_open_bugs(arguments.get("max_results", 20))
        elif name == "get_tickets_by_assignee":
            result = get_tickets_by_assignee(
                arguments["assignee_name"], arguments.get("max_results", 20)
            )
        elif name == "get_project_summary":
            result = get_project_summary()
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
