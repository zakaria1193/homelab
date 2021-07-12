#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
CONFIG_ENV="$SCRIPT_DIR/config/ddclient.conf"

echo """protocol=dyndns2
server=dynv6.com
login=none
use=web
password='opqtuVeUAW8-wTa8vcxAkTszrgygAk'
""" > $CONFIG_ENV
# FIXME hide password using git-crypt

case $(cat /etc/machine-id) in
  "8c32ed2befb945bcb5bcf26daf1f864d")
    echo Generating config for pi4 at Home in Issy
    URLS="www.zakariafadli.com, transmission.zakariafadli.com, hass.zakariafadli.com, portainer.zakariafadli.com, media.zakariafadli.com, radarr.zakariafadli.com
"
    ;;

  "a80304ee19f1405f8695cc2de9dfd9fa") # pi2B in morocco
    echo Generating config for pi2 at Home in Issy
    URLS="sidirahal.zakariafadli.com"
    ;;

  *)
    echo unknown host. incomplete config genrated.
    URLS=""
    ;;
esac

echo "$URLS" >> $CONFIG_ENV

