# Architecture & Macro-Containerization Plan

> **Status**: Future Architecture Proposal (Do Not Develop Yet)  
> **Author**: Antigravity AI & Homelab Operator  

---

## 1. Overview & Objectives

As the homelab grows, setting up a fresh host machine or migrating services requires re-installing language runtimes, system dependencies, and package managers.

This architecture plan proposes a **hybrid containerization strategy**:
- Package heavy web services and background applications into a minimal set of macro-containers (under a unified `zfadli/homelab` container specification) to guarantee instant reproducibility.
- Maintain **native host execution** for interactive CLI tools (`claude`, `agy`), browser terminals, and tmux sessions to guarantee zero-latency execution and seamless local environment access.
- Expose **container architecture, storage volume usage, and system metrics** transparently on the Homelab Cockpit (`services/status`).

---

## 2. Architectural Design Principles

### Rule A: No Microservice Proliferation
Do **NOT** split every sub-component into individual microservices. Maintain a maximum of 1–2 consolidated macro-containers:
1. **`zfadli/homelab-web`**: Consolidated container hosting web dashboards, API gateways, and web apps.
2. **`zfadli/homelab-media`**: Consolidated container hosting media management services (Sonarr, Radarr, Prowlarr, Readarr, Jellyfin).

### Rule B: Hybrid Native Execution for Interactive CLI & Agent Tools
Interactive AI coding CLIs (`claude`, `agy`), tmux session managers, and browser terminal bridges MUST remain host-native:
- **Why**: Running interactive agent CLIs inside containerized abstractions introduces execution overhead, TTY/PTY binding complexity, socket isolation issues, and versioning friction with host tools.
- **Implementation**: The Homelab Cockpit (`services/status`) runs as a lightweight Python daemon directly on the host, executing CLI tools (`claude -p /usage`, `agy -p /usage`) via native login shells while probing container status via local Docker sockets (`/var/run/docker.sock`).

---

## 3. Homelab Cockpit Visibility & System Metrics

The Homelab Cockpit status page (`services/status`) will be extended to report system architecture and volume usage without compromising rendering speed or smoothness:

1. **Volume & Storage Overhead Card**:
   - Displays real-time disk usage for persistent volumes (e.g. `/var/lib/docker/volumes`, media storage, Obsidian vault).
   - Asynchronous background polling (cached server-side with a 30-second TTL) so browser page refreshes stay instant and smooth.

2. **Container Architecture & Health Badging**:
   - Visual badges distinguishing `[Native]` host processes from `[Container]` macro-services.
   - Direct inspection of container memory, CPU usage, and mount points.

---

## 4. Migration & Execution Checklist (Future Steps)

- [ ] Build `zfadli/homelab-web` base Dockerfile for non-CLI web services.
- [ ] Implement Docker socket Volume & Storage probe in `status_server.py`.
- [ ] Add Storage & Architecture metrics card to `services/status` header.
- [ ] Validate zero-latency CLI execution for `claude` and `agy` in native tmux sessions.
