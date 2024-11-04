This repo holds my configurations for my services on my home server.

All services are containarized in docker. All you need is a `docker-compose up -d`

# Infra

### ~~NGINX reverse proxy~~

~~For routing traffic to my different machines & services.~~
This is unmaintained. Now i use cloudfared tunneling. No need to open ports. Easier ID management. VPN like access to my home network etc...


### ddclient for dynamic DNS update

For dynamic DNS update, saves the hassle of setting up static IP with the ISP.

### Portainer

For "fleet monitoring", by fleet i mean my low power server (a raspberry pi4 running ubuntu server and my stronger refubrished DELL tower server)

# Homeautomation stack

I use Home Assistant, under ./hass for connecting all my devices.

Netatmo cameras, thermostat & weather
Legrand's outlets, lights, shutters
Google cast devices

# Media server stack

### Jellyfin for media client

Serves my movies and shows.

### Sonarr and radarr

To search and dequest my downloads from te download clients.

### Transmission and SABnzbd for downloading

Downloading clients


### Jackett

For inde indexer management.
