"""Read-only MCP boundary; no arbitrary file, URL, SQL or write tool."""
from mcp.server.fastmcp import FastMCP
from rafeeq.domain import calculate_fee, search_policy

server = FastMCP('Rafeeq municipal tools')
server.tool()(calculate_fee)
server.tool()(search_policy)

if __name__ == '__main__':
    server.run(transport='stdio')
