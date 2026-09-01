#!/bin/bash
rcon-cli -c /home/steam/server/rcon.yml "save" || true
sleep 5
rcon-cli -c /home/steam/server/rcon.yml "quit" || true
sleep 15

