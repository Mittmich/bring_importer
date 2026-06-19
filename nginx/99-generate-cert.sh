#!/bin/sh
# Generates a self-signed TLS certificate on first run.
# Skipped on subsequent starts if the cert already exists.
set -e

CERT_DIR=/etc/nginx/certs
CERT=$CERT_DIR/server.crt
KEY=$CERT_DIR/server.key

mkdir -p "$CERT_DIR"

if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
    echo "nginx: generating self-signed TLS certificate..."
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "$KEY" -out "$CERT" \
        -subj "/CN=localhost/O=BringImporter"
    chmod 600 "$KEY"
    echo "nginx: certificate written to $CERT_DIR"
fi
