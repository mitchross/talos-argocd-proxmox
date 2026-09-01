#!/bin/bash
echo "Pre-warming SteamCMD to complete self-update..."
/home/steam/steamcmd/steamcmd.sh +quit || true
cp -a /home/steam/steamcmd/* /steam-cache/ 2>/dev/null || true
echo "SteamCMD pre-warm complete."

