#!/bin/bash

# Fix Network Conflict - Consolidate to single IP 192.168.200.51
# Resolves dhcpcd vs NetworkManager conflict

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}   Fix Network Conflict - Single IP 192.168.200.51  ${NC}"
echo -e "${BLUE}====================================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${CYAN}Current situation detected:${NC}"
echo -e "• Multiple IPs on eth0: .49, .50, .51"
echo -e "• Both dhcpcd AND NetworkManager are active"
echo -e "• dhcpcd.conf already has static IP config for .51"
echo ""
echo -e "${YELLOW}This script will:${NC}"
echo -e "1. Disable NetworkManager (conflicts with dhcpcd)"
echo -e "2. Keep dhcpcd as primary network manager"
echo -e "3. Remove extra IP addresses"
echo -e "4. Apply static IP 192.168.200.51 correctly"
echo ""
read -p "Continue? (y/N): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}Fix cancelled${NC}"
    exit 0
fi

echo -e "\n${BLUE}Step 1: Creating backups...${NC}"
# Backup current network configs
cp /etc/dhcpcd.conf /etc/dhcpcd.conf.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null
systemctl status NetworkManager --no-pager > /tmp/nm-status-backup.$(date +%Y%m%d_%H%M%S).log 2>&1

echo -e "${GREEN}✅ Backups created${NC}"

echo -e "\n${BLUE}Step 2: Stopping NetworkManager...${NC}"
# NetworkManager conflicts with dhcpcd on Raspberry Pi
systemctl stop NetworkManager 2>/dev/null
systemctl disable NetworkManager 2>/dev/null
echo -e "${GREEN}✅ NetworkManager disabled (dhcpcd is preferred on Raspberry Pi)${NC}"

echo -e "\n${BLUE}Step 3: Removing duplicate IP addresses...${NC}"
# Remove extra IPs (.49 and .50)
ip addr del 192.168.200.49/24 dev eth0 2>/dev/null
ip addr del 192.168.200.50/24 dev eth0 2>/dev/null
echo -e "${GREEN}✅ Extra IPs removed${NC}"

echo -e "\n${BLUE}Step 4: Verifying dhcpcd configuration...${NC}"
# Check if static IP is already in dhcpcd.conf
if grep -q "interface eth0" /etc/dhcpcd.conf; then
    echo -e "${GREEN}✅ Static IP configuration already present in dhcpcd.conf${NC}"
else
    # Add static IP configuration if missing
    echo -e "${YELLOW}Adding static IP configuration...${NC}"
    cat >> /etc/dhcpcd.conf << EOF

# Static IP configuration for Guard System
interface eth0
static ip_address=192.168.200.51/24
static routers=192.168.200.1
static domain_name_servers=192.168.200.1 8.8.8.8
EOF
fi

echo -e "\n${BLUE}Step 5: Restarting dhcpcd service...${NC}"
# Restart dhcpcd to apply configuration
systemctl restart dhcpcd
sleep 5

echo -e "${GREEN}✅ dhcpcd restarted${NC}"

echo -e "\n${BLUE}Step 6: Fixing nginx configuration...${NC}"
# Check if nginx config exists in sites-available but not enabled
if [ -f /usr/local/bin/nginx/sites-available/qrverification ] && [ ! -f /etc/nginx/sites-enabled/qrverification ]; then
    echo -e "${YELLOW}Enabling nginx configuration...${NC}"
    ln -sf /usr/local/bin/nginx/sites-available/qrverification /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx
elif [ -f /usr/local/bin/QRVerification/nginx_config.conf ]; then
    echo -e "${YELLOW}Found nginx config in QRVerification directory...${NC}"
    cp /usr/local/bin/QRVerification/nginx_config.conf /etc/nginx/sites-available/qrverification
    ln -sf /etc/nginx/sites-available/qrverification /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx
else
    echo -e "${CYAN}Creating basic nginx configuration...${NC}"
    cat > /etc/nginx/sites-available/qrverification << 'EOF'
server {
    listen 80;
    server_name guard-pi-1706 192.168.200.51 localhost _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
EOF
    ln -sf /etc/nginx/sites-available/qrverification /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx
fi

echo -e "${GREEN}✅ Nginx configuration updated${NC}"

echo -e "\n${BLUE}Step 7: Verifying network configuration...${NC}"
sleep 3

# Check current IPs
CURRENT_IPS=$(hostname -I)
echo -e "Current IP addresses: ${GREEN}$CURRENT_IPS${NC}"

# Verify single IP
IP_COUNT=$(hostname -I | wc -w)
if [ "$IP_COUNT" -eq 1 ]; then
    echo -e "${GREEN}✅ Success! Single IP address configured${NC}"
else
    echo -e "${YELLOW}⚠️ Multiple IPs still present. A reboot may be required.${NC}"
fi

# Check if .51 is active
if ip addr show eth0 | grep -q "192.168.200.51"; then
    echo -e "${GREEN}✅ IP 192.168.200.51 is active${NC}"
else
    echo -e "${RED}❌ IP 192.168.200.51 not found. Please check configuration.${NC}"
fi

echo -e "\n${BLUE}Step 8: Service status check...${NC}"
# Check services
systemctl is-active dhcpcd > /dev/null && echo -e "dhcpcd: ${GREEN}Active${NC}" || echo -e "dhcpcd: ${RED}Inactive${NC}"
systemctl is-active NetworkManager > /dev/null && echo -e "NetworkManager: ${YELLOW}Still Active (should be disabled)${NC}" || echo -e "NetworkManager: ${GREEN}Disabled (correct)${NC}"
systemctl is-active nginx > /dev/null && echo -e "nginx: ${GREEN}Active${NC}" || echo -e "nginx: ${RED}Inactive${NC}"
systemctl is-active qrverification > /dev/null && echo -e "QR Verification: ${GREEN}Active${NC}" || echo -e "QR Verification: ${RED}Inactive${NC}"

echo -e "\n${BLUE}====================================================${NC}"
echo -e "${GREEN}Network conflict resolution complete!${NC}"
echo -e "${BLUE}====================================================${NC}"

echo -e "\n${CYAN}Next steps:${NC}"
echo -e "1. ${YELLOW}Verify single IP:${NC} ifconfig eth0"
echo -e "2. ${YELLOW}Test web access:${NC} http://192.168.200.51"
echo -e "3. ${YELLOW}If multiple IPs persist:${NC} sudo reboot"
echo ""
echo -e "${GREEN}The system should now use only IP 192.168.200.51${NC}"
echo -e "${CYAN}SSH and Web interface will both be on the same IP.${NC}"

# Optional reboot prompt
echo ""
read -p "Would you like to reboot now for a clean start? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Rebooting in 5 seconds...${NC}"
    echo -e "${CYAN}After reboot, connect to: ssh user@192.168.200.51${NC}"
    sleep 5
    reboot
fi