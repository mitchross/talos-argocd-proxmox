#!/bin/sh
echo "Waiting for redis to be ready..."
until nc -z redis 6379; do
  echo "Redis not ready, retrying in 2s..."
  sleep 2
done
echo "Redis is ready!"

