#!/bin/bash

# Network Diagnostics Script for Guard NFC/QR System

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}         Network Diagnostics for Guard System       ${NC}"
echo -e "${BLUE}====================================================${NC}"

echo -e "\n${CYAN}1. Network Interfaces:${NC}"
echo "---------------------"
ifconfig 2>/dev/null || ip addr show

echo -e "\n${CYAN}2. Routing Table:${NC}"
echo "----------------"
route -n 2>/dev/null || ip route

echo -e "\n${CYAN}3. Active Network Manager:${NC}"
echo "-------------------------"
if systemctl is-active --quiet dhcpcd; then
    echo -e "${GREEN}✓ dhcpcd is active${NC}"
    echo "  Config: /etc/dhcpcd.conf"
    grep -v '^#' /etc/dhcpcd.conf 2>/dev/null | grep -v '^$' | head -20
fi

if systemctl is-active --quiet NetworkManager; then
    echo -e "${GREEN}✓ NetworkManager is active${NC}"
    nmcli connection show 2>/dev/null
fi

if systemctl is-active --quiet systemd-networkd; then
    echo -e "${GREEN}✓ systemd-networkd is active${NC}"
    ls -la /etc/systemd/network/ 2>/dev/null
fi

echo -e "\n${CYAN}4. Port Listening Status:${NC}"
echo "------------------------"
netstat -tlnp 2>/dev/null | grep -E ':80|:443|:5000|:5001|:8000|:22' || ss -tlnp | grep -E ':80|:443|:5000|:5001|:8000|:22'

echo -e "\n${CYAN}5. Nginx Configuration:${NC}"
echo "----------------------"
if [ -f /etc/nginx/sites-enabled/qrverification ]; then
    echo "Active nginx config:"
    grep -E "listen|server_name|proxy_pass" /etc/nginx/sites-enabled/qrverification
else
    echo "No nginx configuration found in /etc/nginx/sites-enabled/"
fi

echo -e "\n${CYAN}6. Firewall Rules (iptables):${NC}"
echo "----------------------------"
iptables -t nat -L PREROUTING -n -v 2>/dev/null | head -10 || echo "No NAT rules or permission denied"
iptables -L INPUT -n -v 2>/dev/null | head -10 || echo "No INPUT rules or permission denied"

echo -e "\n${CYAN}7. Service Status:${NC}"
echo "-----------------"
systemctl status qrverification --no-pager 2>/dev/null | head -15 || echo "QR Verification service not found"

echo -e "\n${CYAN}8. ARP Table (local network):${NC}"
echo "----------------------------"
arp -a 2>/dev/null | grep -E "192.168.200.49|192.168.200.51" || echo "No ARP entries for .49 or .51"

echo -e "\n${CYAN}9. DNS Resolution:${NC}"
echo "-----------------"
echo "Hostname: $(hostname)"
echo "Hostname -I: $(hostname -I)"
echo "Resolving hostname:"
getent hosts $(hostname) 2>/dev/null || host $(hostname) 2>/dev/null || echo "Cannot resolve hostname"

echo -e "\n${CYAN}10. Virtual Interfaces Check:${NC}"
echo "----------------------------"
if ip addr show | grep -q "eth0:"; then
    echo -e "${YELLOW}Virtual interfaces found:${NC}"
    ip addr show | grep "eth0:"
else
    echo "No virtual interfaces (eth0:x) found"
fi

echo -e "\n${CYAN}11. DHCP Lease Information:${NC}"
echo "-------------------------"
if [ -f /var/lib/dhcp/dhclient.leases ]; then
    echo "DHCP client leases:"
    tail -20 /var/lib/dhcp/dhclient.leases
elif [ -f /var/lib/dhcpcd5/dhcpcd-eth0.lease ]; then
    echo "dhcpcd lease info:"
    cat /var/lib/dhcpcd5/dhcpcd-eth0.lease 2>/dev/null | strings | head -20
else
    echo "No DHCP lease files found"
fi

echo -e "\n${CYAN}12. Connection Test:${NC}"
echo "-------------------"
echo "Testing connectivity to gateway (192.168.200.1):"
ping -c 1 192.168.200.1 > /dev/null 2>&1 && echo -e "${GREEN}✓ Gateway reachable${NC}" || echo -e "${RED}✗ Gateway unreachable${NC}"

echo "Testing web service locally:"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost 2>/dev/null || echo "Local web service not responding"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost:8000 2>/dev/null || echo "Gunicorn not responding on port 8000"

echo -e "\n${CYAN}13. Summary:${NC}"
echo "-----------"
CURRENT_IP=$(ip addr show eth0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1)
echo -e "Current eth0 IP: ${GREEN}$CURRENT_IP${NC}"

# Check for potential issues
echo -e "\n${YELLOW}Potential Issues Detected:${NC}"

if [ "$CURRENT_IP" != "192.168.200.51" ]; then
    echo -e "${YELLOW}• Current IP ($CURRENT_IP) differs from desired (192.168.200.51)${NC}"
    echo -e "  Solution: Run configure_static_ip.sh to set static IP"
fi

# Check if multiple IPs are being used
if netstat -tlnp 2>/dev/null | grep -q ":80 "; then
    NGINX_LISTEN=$(netstat -tlnp 2>/dev/null | grep ":80 " | awk '{print $4}')
    if [[ "$NGINX_LISTEN" == "0.0.0.0:80" ]] || [[ "$NGINX_LISTEN" == ":::80" ]]; then
        echo -e "${YELLOW}• Nginx listening on all interfaces (0.0.0.0)${NC}"
        echo -e "  This allows access via any configured IP address"
    fi
fi

# Check for port forwarding indicators
if [ -f /proc/sys/net/ipv4/ip_forward ]; then
    IP_FORWARD=$(cat /proc/sys/net/ipv4/ip_forward)
    if [ "$IP_FORWARD" == "1" ]; then
        echo -e "${YELLOW}• IP forwarding is enabled on this system${NC}"
        echo -e "  This might indicate NAT/routing configuration"
    fi
fi

echo -e "\n${BLUE}====================================================${NC}"
echo -e "${GREEN}Diagnostics Complete${NC}"
echo -e "${BLUE}====================================================${NC}"

echo -e "\n${CYAN}Recommendations:${NC}"
echo -e "1. If you see different IPs for web and SSH access:"
echo -e "   • Check router/firewall for port forwarding rules"
echo -e "   • Router might be forwarding port 80 from .51 to .49"
echo -e ""
echo -e "2. To consolidate on single IP (192.168.200.51):"
echo -e "   • Run: ${GREEN}sudo ./configure_static_ip.sh${NC}"
echo -e "   • Update router port forwarding if necessary"
echo -e "   • Reboot if changes don't apply immediately"