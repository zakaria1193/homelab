# arrMcpAI Service

This service provides a self-contained setup for `arr-mcp`, a feature-rich MCP (Model Context Protocol) server for Sonarr, Radarr, Prowlarr, and Readarr. It starts both the backend MCP server (running in HTTP/SSE mode on port `10938`) and the frontend React dashboard (on port `10939`).

## Directory Structure
* `arr-mcp/` - Cloned repository containing the Python backend and Vite frontend.
* `arr-mcp-backend.service.template` - Template for the backend systemd daemon.
* `arr-mcp-frontend.service.template` - Template for the frontend systemd daemon.
* `Makefile` - Tasks for setup, build, running, and systemd management.
* `.env` - Environment configurations containing API keys and endpoints.

## Setup Instructions

1. **Install Dependencies**
   Run the following target to sync the Python virtual environment and install node packages:
   ```bash
   make install
   ```

2. **Start Services**
   Generate the systemd service files, enable them, and start them:
   ```bash
   make start
   ```

3. **Check Status**
   ```bash
   make status
   ```

4. **View Logs**
   ```bash
   make logs
   ```
