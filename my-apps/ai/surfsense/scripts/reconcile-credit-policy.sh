#!/bin/sh
set -eu

psql --set=ON_ERROR_STOP=1 <<'SQL'
UPDATE "user"
SET credit_micros_balance = 0,
    credit_micros_reserved = 0
WHERE credit_micros_balance <> 0
   OR credit_micros_reserved <> 0;
SQL
