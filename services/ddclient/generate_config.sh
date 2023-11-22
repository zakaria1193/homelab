#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
CONFIG_ENV="$SCRIPT_DIR/config/ddclient.conf"

CLOUDFARE_KEY="$(cat ~/cert/cloudfare.key)"

echo """
daemon=1800                             # check every 300 seconds
syslog=yes                              # log update msgs to syslog
ssl=yes                                 # use ssl-support.  Works with
                                        # ssl-library

use=web, web=checkip.dyndns.com/, web-skip='IP Address'
cache=/tmp/ddclient.cache

#
## CloudFlare (cloudflare.com)
##
protocol=cloudflare,
zone=zakariafadli.com,           \
login=zakaria1193@gmail.com,     \
password=$CLOUDFARE_KEY          \
""" > $CONFIG_ENV
# FIXME hide password using git-crypt

case $(cat /etc/machine-id) in
  "8c32ed2befb945bcb5bcf26daf1f864d")
    echo Generating config for pi4 at Home in Issy
    URLS="www.zakariafadli.com, transmission.zakariafadli.com, hass.zakariafadli.com, portainer.zakariafadli.com, media.zakariafadli.com"
    ;;

  "a80304ee19f1405f8695cc2de9dfd9fa")
    echo Generating config for pi2 at Home in sidi rahal
    URLS="sidirahal.zakariafadli.com"
    ;;

  *)
    echo unknown host. incomplete config genrated.
    URLS=""
    ;;
esac

echo "$URLS" >> $CONFIG_ENV
