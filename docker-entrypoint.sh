#!/bin/sh
set -e
# Export current environment into a shell-safe file for cron to source
printenv | awk -F= '{ val = substr($0, index($0, "=") + 1); gsub(/"/, "\\\"", val); printf "export %s=\"%s\"\n", $1, val }' > /app/.env || true
# Ensure log file is connected to container stdout
ln -sf /proc/1/fd/1 /app/YT_project.log || true

# Execute the container CMD (should be `cron -f`)
exec "$@"
