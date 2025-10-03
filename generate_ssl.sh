#!/bin/bash

# SSL-Zertifikat Generator für Guard NFC QR System
# Erstellt Self-Signed Zertifikate für HTTPS

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}SSL-Zertifikat Generator für Guard System${NC}"
echo -e "${BLUE}=======================================${NC}"

# SSL-Verzeichnis erstellen
SSL_DIR="/etc/ssl/guard"
mkdir -p "$SSL_DIR"

# Hostname ermitteln
HOSTNAME=$(hostname)
if [ -z "$HOSTNAME" ]; then
    HOSTNAME="guard-system"
fi

echo -e "${YELLOW}Erstelle SSL-Zertifikat für Hostname: $HOSTNAME${NC}"

# Self-Signed Zertifikat erstellen
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SSL_DIR/guard.key" \
    -out "$SSL_DIR/guard.crt" \
    -subj "/C=DE/ST=State/L=City/O=Organization/OU=Guard System/CN=$HOSTNAME" \
    -config <(
    echo '[req]'
    echo 'default_bits = 2048'
    echo 'prompt = no'
    echo 'distinguished_name = req_distinguished_name'
    echo 'req_extensions = v3_req'
    echo '[req_distinguished_name]'
    echo "C=DE"
    echo "ST=State"
    echo "L=City"
    echo "O=Guard System"
    echo "OU=Security"
    echo "CN=$HOSTNAME"
    echo '[v3_req]'
    echo 'basicConstraints = CA:FALSE'
    echo 'keyUsage = nonRepudiation, digitalSignature, keyEncipherment'
    echo 'subjectAltName = @alt_names'
    echo '[alt_names]'
    echo "DNS.1 = $HOSTNAME"
    echo "DNS.2 = $HOSTNAME.local"
    echo "DNS.3 = localhost"
    echo "IP.1 = 127.0.0.1"
    echo "IP.2 = $(hostname -I | awk '{print $1}')"
) 2>/dev/null

if [ $? -eq 0 ] && [ -f "$SSL_DIR/guard.crt" ] && [ -f "$SSL_DIR/guard.key" ]; then
    # Berechtigungen setzen
    chmod 600 "$SSL_DIR/guard.key"
    chmod 644 "$SSL_DIR/guard.crt"
    chown root:root "$SSL_DIR"/*
    
    echo -e "${GREEN}✅ SSL-Zertifikat erfolgreich erstellt:${NC}"
    echo -e "${GREEN}   Zertifikat: $SSL_DIR/guard.crt${NC}"
    echo -e "${GREEN}   Private Key: $SSL_DIR/guard.key${NC}"
    echo -e "${GREEN}   Gültig für: $HOSTNAME, $HOSTNAME.local, localhost${NC}"
    
    # Nginx SSL-Konfiguration erstellen
    cat > nginx_ssl_config.conf << EOF
server {
    listen 80;
    server_name $HOSTNAME localhost _;
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name $HOSTNAME localhost _;

    # SSL-Konfiguration
    ssl_certificate $SSL_DIR/guard.crt;
    ssl_certificate_key $SSL_DIR/guard.key;
    
    # SSL-Sicherheitseinstellungen
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_session_timeout 10m;
    ssl_session_cache shared:SSL:10m;

    # Erhöhe die maximale Upload-Größe für CSV-Dateien
    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }

    # Statische Dateien direkt servieren
    location /static/ {
        alias $(pwd)/app/static/;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }

    # Gzip-Kompression aktivieren
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
}
EOF

    echo -e "${GREEN}✅ Nginx SSL-Konfiguration erstellt: nginx_ssl_config.conf${NC}"
    echo -e "${YELLOW}⚠️  Hinweis: Self-Signed Zertifikat - Browser zeigt Sicherheitswarnung${NC}"
    
else
    echo -e "${RED}❌ Fehler beim Erstellen des SSL-Zertifikats${NC}"
    exit 1
fi 