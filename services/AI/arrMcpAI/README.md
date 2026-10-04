# arrMcpAI Service

This service provides a self-contained setup for `arr-mcp`, a feature-rich MCP (Model Context Protocol) server for Sonarr, Radarr, Prowlarr, and Readarr. It runs the backend MCP server in HTTP/SSE mode on port `10938`. The React dashboard (port `10939`) is not started.

`arr-mcp/` is a submodule on our fork, `zakaria1193/arr-mcp`, which carries a small local patch on top of `sandraschi/arr-mcp`. The upstream is kept as the `upstream` remote. To pull its changes:

```bash
cd arr-mcp
git fetch upstream && git rebase upstream/master && git push --force-with-lease origin master
cd .. && git add arr-mcp   # then commit the pointer bump in homelab
```

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
