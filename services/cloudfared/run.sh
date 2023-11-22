#!/bin/sh

curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-armhf.deb && 

sudo dpkg -i cloudflared.deb && 

sudo cloudflared service install $(cat ./.token.txt)
