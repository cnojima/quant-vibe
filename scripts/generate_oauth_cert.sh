#!/bin/bash
#
# Generate self-signed SSL certificate for Schwab OAuth callback
#
# This certificate is used by nginx to handle HTTPS on port 53430 for OAuth redirects.
# Schwab requires HTTPS for OAuth callback URLs.

set -e

CERT_DIR="./src/admin_ui/frontend/ssl"
CERT_FILE="$CERT_DIR/nginx-selfsigned.crt"
KEY_FILE="$CERT_DIR/nginx-selfsigned.key"

echo "========================================"
echo "Schwab OAuth SSL Certificate Generator"
echo "========================================"
echo ""

# Create directory if it doesn't exist
mkdir -p "$CERT_DIR"

# Check if certificate already exists
if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "⚠️  Certificate already exists:"
    echo "   $CERT_FILE"
    echo "   $KEY_FILE"
    echo ""
    read -p "Regenerate? (y/N): " response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "Keeping existing certificate."
        exit 0
    fi
    echo ""
fi

echo "Generating self-signed SSL certificate..."
echo ""

# Generate certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -subj "/C=US/ST=CA/L=SF/O=QuantVibe/CN=localhost" \
    2>/dev/null

echo "✓ Certificate generated successfully!"
echo ""
echo "Certificate: $CERT_FILE"
echo "Private Key: $KEY_FILE"
echo ""
echo "This certificate is valid for 365 days."
echo ""
echo "⚠️  IMPORTANT: This is a self-signed certificate."
echo "   Your browser will show a security warning when accessing"
echo "   https://127.0.0.1:53430/ - this is expected."
echo "   Click 'Advanced' and 'Proceed' to continue."
echo ""
echo "Next steps:"
echo "1. Update your Schwab app callback URL to: https://127.0.0.1:53430/"
echo "2. Rebuild the nginx container: docker compose build admin_ui_frontend"
echo "3. Restart nginx: docker compose up -d admin_ui_frontend"
echo ""
