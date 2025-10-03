#!/usr/bin/env python3
"""Test script to verify all admin features are accessible"""

import requests
import sys

BASE_URL = "http://localhost:5001"

def test_admin_features():
    """Test all admin features are accessible after login"""

    session = requests.Session()

    print("🔐 Testing Admin Feature Accessibility")
    print("=" * 50)

    # 1. Login as admin
    print("\n1. Logging in as admin...")
    login_response = session.post(
        f"{BASE_URL}/login",
        data={"username": "admin", "password": "admin"},
        allow_redirects=False
    )

    if login_response.status_code != 302:
        print(f"❌ Login failed with status: {login_response.status_code}")
        return False
    print("✅ Login successful")

    # 2. Test all admin features
    print("\n2. Testing Admin Features:")

    admin_routes = [
        ("/users", "User Management", "Benutzerverwaltung"),
        ("/opening_hours", "Opening Hours", "Öffnungszeiten"),
        ("/whitelabel", "White-Label Config", "White-Label"),
        ("/settings", "Settings", "Einstellungen"),
        ("/logs", "Logs", "Protokolle"),
        ("/nfc_cards", "NFC Management", "NFC"),
        ("/barcodes", "Barcode Management", "Barcode")
    ]

    all_accessible = True
    for route, name, expected_text in admin_routes:
        response = session.get(f"{BASE_URL}{route}")

        if response.status_code == 200:
            if expected_text in response.text:
                print(f"  ✅ {name:25} - Accessible and verified")
            else:
                print(f"  ⚠️  {name:25} - Accessible but content not verified")
        else:
            print(f"  ❌ {name:25} - Failed (Status: {response.status_code})")
            all_accessible = False

    # 3. Check navigation menu
    print("\n3. Checking Navigation Menu Items:")
    dashboard = session.get(f"{BASE_URL}/dashboard")

    if dashboard.status_code == 200:
        menu_items = [
            "Benutzerverwaltung",
            "Öffnungszeiten",
            "White-Label"
        ]

        for item in menu_items:
            if item in dashboard.text:
                print(f"  ✅ {item} - Present in navigation")
            else:
                print(f"  ❌ {item} - Missing from navigation")
                all_accessible = False

    return all_accessible

if __name__ == "__main__":
    try:
        success = test_admin_features()
        print("\n" + "=" * 50)
        if success:
            print("✅ All admin features are accessible!")
            sys.exit(0)
        else:
            print("❌ Some features have issues. Check above for details.")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Is it running on port 5001?")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)