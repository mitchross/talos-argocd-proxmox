#!/bin/sh

node ace queue:work --all &
exec node bin/server.js
