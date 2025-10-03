#!/bin/bash

# Script to configure static IP address for Guard NFC/QR System
# Target IP: 192.168.200.51

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}      Configuring Static IP: 192.168.200.51        ${NC}"
echo -e "${BLUE}====================================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# Network configuration
STATIC_IP="192.168.200.51"
GATEWAY="192.168.200.1"
DNS_SERVER="8.8.8.8"
INTERFACE="eth0"

echo -e "${CYAN}Current network configuration:${NC}"
ifconfig eth0 | grep inet

echo -e "\n${YELLOW}This script will:${NC}"
echo -e "  • Configure static IP: ${GREEN}$STATIC_IP${NC}"
echo -e "  • Gateway: ${GREEN}$GATEWAY${NC}"
echo -e "  • DNS: ${GREEN}$DNS_SERVER${NC}"
echo -e "  • Interface: ${GREEN}$INTERFACE${NC}"
echo
read -p "Continue? (y/N): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}Configuration cancelled${NC}"
    exit 0
fi

# Backup existing configuration
echo -e "${BLUE}Creating configuration backup...${NC}"
if [ -f /etc/dhcpcd.conf ]; then
    cp /etc/dhcpcd.conf /etc/dhcpcd.conf.backup.$(date +%Y%m%d_%H%M%S)
fi

# Method 1: Try dhcpcd (most common on Raspberry Pi OS)
if systemctl is-active --quiet dhcpcd; then
    echo -e "${BLUE}Configuring via dhcpcd...${NC}"

    # Remove any existing static IP configuration for eth0
    sed -i '/^interface eth0/,/^$/d' /etc/dhcpcd.conf 2>/dev/null

    # Add new static IP configuration
    cat >> /etc/dhcpcd.conf << EOF

# Static IP configuration for Guard System
interface eth0
static ip_address=$STATIC_IP/24
static routers=$GATEWAY
static domain_name_servers=$DNS_SERVER 8.8.4.4
EOF

    echo -e "${GREEN}✅ dhcpcd configuration updated${NC}"

    # Restart dhcpcd service
    systemctl restart dhcpcd
    sleep 5

# Method 2: NetworkManager
elif systemctl is-active --quiet NetworkManager; then
    echo -e "${BLUE}Configuring via NetworkManager...${NC}"

    # Delete any existing guard connection
    nmcli connection delete "guard-static" 2>/dev/null || true

    # Create new static connection
    nmcli connection add type ethernet con-name "guard-static" ifname "$INTERFACE" \
        ip4 "$STATIC_IP/24" gw4 "$GATEWAY" ipv4.dns "$DNS_SERVER" \
        ipv4.method manual autoconnect yes

    # Activate the connection
    nmcli connection up "guard-static"

    echo -e "${GREEN}✅ NetworkManager configuration applied${NC}"

# Method 3: systemd-networkd
elif systemctl is-active --quiet systemd-networkd; then
    echo -e "${BLUE}Configuring via systemd-networkd...${NC}"

    cat > /etc/systemd/network/20-guard-eth0.network << EOF
[Match]
Name=eth0

[Network]
Address=$STATIC_IP/24
Gateway=$GATEWAY
DNS=$DNS_SERVER
EOF

    systemctl restart systemd-networkd
    sleep 5

    echo -e "${GREEN}✅ systemd-networkd configuration applied${NC}"

# Method 4: Traditional /etc/network/interfaces
else
    echo -e "${BLUE}Configuring via /etc/network/interfaces...${NC}"

    # Backup existing file
    if [ -f /etc/network/interfaces ]; then
        cp /etc/network/interfaces /etc/network/interfaces.backup.$(date +%Y%m%d_%H%M%S)
    fi

    # Create interfaces configuration
    cat > /etc/network/interfaces << EOF
# Network interfaces configuration
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address $STATIC_IP
    netmask 255.255.255.0
    gateway $GATEWAY
    dns-nameservers $DNS_SERVER
EOF

    # Restart networking
    ifdown eth0 && ifup eth0

    echo -e "${GREEN}✅ Network interfaces configuration applied${NC}"
fi

# Update hosts file
echo -e "${BLUE}Updating /etc/hosts...${NC}"
HOSTNAME=$(hostname)

# Backup hosts file
cp /etc/hosts /etc/hosts.backup.$(date +%Y%m%d_%H%M%S)

# Remove old entries and add new
sed -i '/127.0.1.1/d' /etc/hosts
echo -e "127.0.1.1\t$HOSTNAME" >> /etc/hosts
echo -e "$STATIC_IP\t$HOSTNAME" >> /etc/hosts

# Update nginx configuration if exists
if [ -f /etc/nginx/sites-available/qrverification ]; then
    echo -e "${BLUE}Updating nginx configuration...${NC}"

    # Backup nginx config
    cp /etc/nginx/sites-available/qrverification /etc/nginx/sites-available/qrverification.backup.$(date +%Y%m%d_%H%M%S)

    # Update server_name to include new IP
    sed -i "s/server_name .*/server_name $HOSTNAME $STATIC_IP localhost _;/" /etc/nginx/sites-available/qrverification

    # Test nginx configuration
    nginx -t > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        systemctl reload nginx
        echo -e "${GREEN}✅ Nginx configuration updated${NC}"
    else
        echo -e "${YELLOW}⚠️ Nginx configuration test failed, keeping old config${NC}"
    fi
fi

echo -e "\n${BLUE}====================================================${NC}"
echo -e "${GREEN}Static IP configuration complete!${NC}"
echo -e "${BLUE}====================================================${NC}"

# Display new configuration
echo -e "\n${CYAN}New network configuration:${NC}"
sleep 3
NEW_IP=$(ip addr show eth0 | grep "inet " | awk '{print $2}' | cut -d/ -f1)
echo -e "IP Address: ${GREEN}$NEW_IP${NC}"

if [ "$NEW_IP" == "$STATIC_IP" ]; then
    echo -e "\n${GREEN}✅ Success! System is now using IP: $STATIC_IP${NC}"
    echo -e "${YELLOW}Note: You may need to update router port forwarding rules${NC}"
    echo -e "${YELLOW}      to point to the new IP address${NC}"
else
    echo -e "\n${YELLOW}⚠️ IP configuration may take a moment to apply${NC}"
    echo -e "${YELLOW}   Please check with: ifconfig eth0${NC}"
    echo -e "${YELLOW}   You may need to reboot for changes to take full effect${NC}"
fi

echo -e "\n${CYAN}Services status:${NC}"
systemctl is-active qrverification && echo -e "QR Verification: ${GREEN}Active${NC}" || echo -e "QR Verification: ${RED}Inactive${NC}"
systemctl is-active nginx && echo -e "Nginx: ${GREEN}Active${NC}" || echo -e "Nginx: ${RED}Inactive${NC}"

echo -e "\n${BLUE}You can now access the system at:${NC}"
echo -e "  • HTTP: ${GREEN}http://$STATIC_IP${NC}"
echo -e "  • SSH:  ${GREEN}ssh user@$STATIC_IP${NC}"

echo -e "\n${YELLOW}If you lose SSH access, you can:${NC}"
echo -e "  1. Connect via console/keyboard"
echo -e "  2. Restore dhcpcd.conf from backup"
echo -e "  3. Or reboot to apply changes properly"