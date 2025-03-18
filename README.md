# Personal Homelab

This repository contains the infrastructure-as-code configurations for my personal homelab environment. It's designed to run a variety of self-hosted services for home automation, media management, and infrastructure monitoring.

## Core Infrastructure

### Cloudflared Tunneling
Provides secure remote access to my homelab services without exposing ports to the internet. This zero-trust approach ensures:
- Secure remote access to all services
- No need for port forwarding
- Simple identity management
- VPN-like access to home network

### Portainer
Container management solution deployed across my homelab fleet:
- Primary Server: Refurbished DELL tower server for resource-intensive services
- Secondary Server: Raspberry Pi 4 (Ubuntu Server) for lightweight services
- Provides container monitoring, logs, and easy deployment management

### ddclient
Handles dynamic DNS updates automatically, keeping my domain names pointed to my home IP address even when it changes.

## Smart Home Infrastructure

### Home Assistant
The central brain of my smart home setup, integrating:
- **Climate Control**: Netatmo smart thermostat and weather stations for temperature monitoring and automation
- **Security**: Netatmo cameras for home surveillance
- **Lighting & Power**: Legrand smart outlets, light switches, and automated shutters
- **Entertainment**: Google Cast devices integration for automated media control

### MQTT & Zigbee Integration
- **MQTT Broker**: Message broker handling all IoT device communications
- **Zigbee2MQTT**: Bridges Zigbee devices to my network, enabling native integration with Home Assistant
  - Allows use of various Zigbee devices without vendor-specific hubs
  - Provides direct local control of smart devices

## Media Management System

### Core Media Server
- **Jellyfin**: Self-hosted media streaming solution
  - Serves movies, TV shows, and books
  - Provides transcoding for various devices
  - Supports multiple users with personalized libraries

### Automated Media Management
- **Sonarr**: Automated TV show library management
- **Radarr**: Automated movie library management
- **Readarr**: Automated ebook library management
- **Prowlarr**: Unified indexer management for all *arr services

### Download Management
- **Transmission**: Torrent client with scheduling and bandwidth management

## Monitoring & Database

### System Telemetry
- **OpenObserve**: Modern observability platform for:
  - System metrics monitoring
  - Log aggregation
  - Performance tracking

### Database
- **CouchDB**: Document database for:
  - Application data storage
  - Service state persistence
  - Configuration management

## Deployment

All services are containerized using Docker and can be deployed with a simple:
```bash
docker-compose up -d
```
