#!/bin/sh
set -e

PUID=${PUID:-1000}
PGID=${PGID:-1000}

mkdir -p /app/config /downloads /music

if [ "$(id -u)" = "0" ]; then
    if ! getent group appgroup >/dev/null 2>&1; then
        groupadd -g "${PGID}" -o appgroup || true
    fi
    if ! getent passwd appuser >/dev/null 2>&1; then
        useradd -u "${PUID}" -g "${PGID}" -o -m -s /bin/sh appuser || true
    fi
    chown -R "${PUID}:${PGID}" /app/config /downloads 2>/dev/null || true
    chown "${PUID}:${PGID}" /music 2>/dev/null || true
    exec gosu "${PUID}:${PGID}" "$@"
fi

exec "$@"
