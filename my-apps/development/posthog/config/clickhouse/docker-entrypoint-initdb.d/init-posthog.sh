#!/bin/bash
set -e

clickhouse client -n <<-EOSQL
    CREATE DATABASE IF NOT EXISTS posthog;
    CREATE DATABASE IF NOT EXISTS cyclotron;
EOSQL
