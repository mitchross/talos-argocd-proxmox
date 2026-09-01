#!/bin/sh
for d in thumbs upload backups library profile encoded-video; do
  mkdir -p "/library/$d" && touch "/library/$d/.immich"
done
echo "immich /library folder markers ensured"

