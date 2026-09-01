#!/bin/sh
if [ ! -d "/config/custom_components/hacs" ]; then
  echo "HACS not found, installing..."
  apk add --no-cache bash wget unzip curl
  # Try to install HACS with timeout, skip if fails
  timeout 120 sh -c 'wget -O - https://get.hacs.xyz | bash -' || {
    echo "HACS install timed out or failed, continuing anyway..."
    echo "You can install HACS manually later from https://hacs.xyz"
  }
else
  echo "HACS already installed"
fi

