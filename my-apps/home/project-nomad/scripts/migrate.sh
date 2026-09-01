#!/bin/sh
set -eu

node ace migration:run --force
node ace db:seed
