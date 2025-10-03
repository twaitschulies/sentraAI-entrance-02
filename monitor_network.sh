#!/bin/bash

# Network Monitoring Script for Guard NFC/QR System
# Checks for network configuration issues and reports status

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}      Network Configuration Monitor                 ${NC}"
echo -e "${BLUE}====================================================${NC}"

# Expected configuration
EXPECTED_IP="192.168.200.51"
EXPECTED_GATEWAY="192.168.200.1"
EXPECTED_INTERFACE="eth0"

# Function to check IP configuration
check_ip_config() {
    local interface=$1
    local ip_count=$(ip addr show $interface 2>/dev/null | grep -c "inet ")
    local actual_ips=$(ip addr show $interface 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d'/' -f1)

    echo -e "\n${CYAN}Interface: $interface${NC}"
    echo -e "IP Count: $ip_count"

    if [ "$ip_count" -eq 0 ]; then
        echo -e "${RED}❌ No IP address configured${NC}"
        return 1
    elif [ "$ip_count" -gt 1 ]; then
        echo -e "${YELLOW}⚠️ Multiple IPs detected:${NC}"
        echo "$actual_ips" | while read ip; do
            echo "   - $ip"
        done
        return 2
    else
        local actual_ip=$(echo "$actual_ips" | head -1)
        if [ "$actual_ip" == "$EXPECTED_IP" ]; then
            echo -e "${GREEN}✅ IP configured correctly: $actual_ip${NC}"
            return 0
        else
            echo -e "${YELLOW}⚠️ IP mismatch: Expected $EXPECTED_IP, got $actual_ip${NC}"
            return 3
        fi
    fi
}

# Function to check gateway
check_gateway() {
    local gateway=$(ip route | grep default | awk '{print $3}' | head -1)

    echo -e "\n${CYAN}Gateway Configuration:${NC}"
    if [ -z "$gateway" ]; then
        echo -e "${RED}❌ No default gateway configured${NC}"
        return 1
    elif [ "$gateway" == "$EXPECTED_GATEWAY" ]; then
        echo -e "${GREEN}✅ Gateway correct: $gateway${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️ Gateway mismatch: Expected $EXPECTED_GATEWAY, got $gateway${NC}"
        return 2
    fi
}

# Function to check network managers
check_network_managers() {
    echo -e "\n${CYAN}Network Manager Status:${NC}"

    local issues=0

    # Check dhcpcd
    if systemctl is-active --quiet dhcpcd; then
        echo -e "${GREEN}✅ dhcpcd is active (preferred)${NC}"
    else
        echo -e "${RED}❌ dhcpcd is not active${NC}"
        issues=$((issues + 1))
    fi

    # Check NetworkManager (should be inactive)
    if systemctl is-active --quiet NetworkManager; then
        echo -e "${YELLOW}⚠️ NetworkManager is active (can conflict with dhcpcd)${NC}"
        issues=$((issues + 1))
    else
        echo -e "${GREEN}✅ NetworkManager is inactive (correct)${NC}"
    fi

    # Check systemd-networkd (should be inactive)
    if systemctl is-active --quiet systemd-networkd; then
        echo -e "${YELLOW}⚠️ systemd-networkd is active (can conflict with dhcpcd)${NC}"
        issues=$((issues + 1))
    else
        echo -e "${GREEN}✅ systemd-networkd is inactive (correct)${NC}"
    fi

    return $issues
}

# Function to check services
check_services() {
    echo -e "\n${CYAN}Service Status:${NC}"

    # Check nginx
    if systemctl is-active --quiet nginx; then
        echo -e "${GREEN}✅ nginx is active${NC}"

        # Check nginx listening ports
        local nginx_ports=$(netstat -tlnp 2>/dev/null | grep nginx | awk '{print $4}')
        if [ ! -z "$nginx_ports" ]; then
            echo "   Listening on:"
            echo "$nginx_ports" | while read port; do
                echo "   - $port"
            done
        fi
    else
        echo -e "${RED}❌ nginx is not active${NC}"
    fi

    # Check qrverification service
    if systemctl is-active --quiet qrverification; then
        echo -e "${GREEN}✅ qrverification service is active${NC}"
    else
        echo -e "${RED}❌ qrverification service is not active${NC}"
    fi
}

# Function to test connectivity
test_connectivity() {
    echo -e "\n${CYAN}Connectivity Test:${NC}"

    # Test gateway ping
    if ping -c 1 -W 2 $EXPECTED_GATEWAY > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Gateway reachable${NC}"
    else
        echo -e "${RED}❌ Gateway unreachable${NC}"
    fi

    # Test internet connectivity
    if ping -c 1 -W 2 8.8.8.8 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Internet connectivity working${NC}"
    else
        echo -e "${YELLOW}⚠️ No internet connectivity${NC}"
    fi

    # Test local web service
    if curl -s -o /dev/null -w "%{http_code}" http://localhost | grep -q "200\|301\|302"; then
        echo -e "${GREEN}✅ Local web service responding${NC}"
    else
        echo -e "${RED}❌ Local web service not responding${NC}"
    fi
}

# Function to check for common issues
check_common_issues() {
    echo -e "\n${CYAN}Common Issue Check:${NC}"

    local issues_found=false

    # Check for duplicate IP assignments
    local all_ips=$(hostname -I)
    local ip_count=$(echo "$all_ips" | wc -w)

    if [ "$ip_count" -gt 1 ]; then
        echo -e "${YELLOW}⚠️ Multiple IP addresses on system: $all_ips${NC}"
        echo "   Run 'sudo ./fix_network_conflict.sh' to resolve"
        issues_found=true
    fi

    # Check dhcpcd.conf for static IP configuration
    if [ -f /etc/dhcpcd.conf ]; then
        if grep -q "interface eth0" /etc/dhcpcd.conf && grep -q "static ip_address=$EXPECTED_IP" /etc/dhcpcd.conf; then
            echo -e "${GREEN}✅ Static IP configured in dhcpcd.conf${NC}"
        else
            echo -e "${YELLOW}⚠️ Static IP not properly configured in dhcpcd.conf${NC}"
            echo "   Run 'sudo ./configure_static_ip.sh' to configure"
            issues_found=true
        fi
    fi

    # Check for orphaned network configurations
    if [ -d /etc/NetworkManager/system-connections/ ]; then
        local nm_configs=$(ls /etc/NetworkManager/system-connections/ 2>/dev/null | wc -l)
        if [ "$nm_configs" -gt 0 ]; then
            echo -e "${YELLOW}⚠️ NetworkManager configurations found (should be removed)${NC}"
            issues_found=true
        fi
    fi

    if [ "$issues_found" = false ]; then
        echo -e "${GREEN}✅ No common issues detected${NC}"
    fi
}

# Main monitoring routine
echo -e "\n${BLUE}Starting network monitoring...${NC}"

# Check IP configuration
check_ip_config $EXPECTED_INTERFACE
ip_status=$?

# Check gateway
check_gateway
gateway_status=$?

# Check network managers
check_network_managers
manager_status=$?

# Check services
check_services

# Test connectivity
test_connectivity

# Check for common issues
check_common_issues

# Summary
echo -e "\n${BLUE}====================================================${NC}"
echo -e "${BLUE}                    Summary                         ${NC}"
echo -e "${BLUE}====================================================${NC}"

if [ "$ip_status" -eq 0 ] && [ "$gateway_status" -eq 0 ] && [ "$manager_status" -eq 0 ]; then
    echo -e "${GREEN}✅ Network configuration is optimal${NC}"
    echo -e "${GREEN}   System is using single IP: $EXPECTED_IP${NC}"
else
    echo -e "${YELLOW}⚠️ Network configuration needs attention${NC}"
    echo ""
    echo -e "${CYAN}Recommended actions:${NC}"

    if [ "$ip_status" -eq 2 ]; then
        echo -e "1. Run: ${GREEN}sudo ./fix_network_conflict.sh${NC}"
        echo "   To resolve multiple IP addresses"
    elif [ "$ip_status" -ne 0 ]; then
        echo -e "1. Run: ${GREEN}sudo ./configure_static_ip.sh${NC}"
        echo "   To configure static IP address"
    fi

    if [ "$manager_status" -gt 0 ]; then
        echo -e "2. Run: ${GREEN}sudo ./fix_network_conflict.sh${NC}"
        echo "   To resolve network manager conflicts"
    fi
fi

# Continuous monitoring option
echo ""
read -p "Start continuous monitoring (updates every 30 seconds)? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${CYAN}Starting continuous monitoring... Press Ctrl+C to stop${NC}"
    while true; do
        clear
        $0 --no-prompt
        sleep 30
    done
fi