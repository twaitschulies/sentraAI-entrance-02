#!/usr/bin/env python3
"""Test script to verify new routes are accessible after login"""

import requests

BASE_URL = "http://localhost:5001"

# Start a session to maintain cookies
session = requests.Session()

print("🔐 Testing Flask App Routes")
print("=" * 50)

# 1. Test login
print("\n1. Testing login with admin/admin...")
login_data = {
    "username": "admin",
    "password": "admin"
}

response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=False)
if response.status_code == 302:  # Redirect after successful login
    print("✅ Login successful! Redirecting to:", response.headers.get('Location'))
else:
    print(f"❌ Login failed with status: {response.status_code}")
    exit(1)

# Follow the redirect to complete login
session.get(f"{BASE_URL}/dashboard")

# 2. Test access to new feature routes
print("\n2. Testing access to new features...")

routes_to_test = [
    ("/dashboard", "Dashboard"),
    ("/users", "User Management"),
    ("/opening_hours", "Opening Hours"),
    ("/whitelabel", "White-Label Configuration"),
    ("/settings", "Settings"),
]

for route, name in routes_to_test:
    response = session.get(f"{BASE_URL}{route}", allow_redirects=False)
    if response.status_code == 200:
        # Check if we can find expected content
        if route == "/users" and "Benutzerverwaltung" in response.text:
            print(f"✅ {name:30} - Accessible and content verified")
        elif route == "/opening_hours" and "Öffnungszeiten" in response.text:
            print(f"✅ {name:30} - Accessible and content verified")
        elif route == "/whitelabel" and ("White-Label" in response.text or "white-label" in response.text.lower()):
            print(f"✅ {name:30} - Accessible and content verified")
        else:
            print(f"✅ {name:30} - Accessible (Status: {response.status_code})")
    elif response.status_code == 302:
        print(f"⚠️  {name:30} - Redirecting to: {response.headers.get('Location')}")
    else:
        print(f"❌ {name:30} - Failed (Status: {response.status_code})")

# 3. Check if menu items are visible in dashboard
print("\n3. Checking if menu items are visible in dashboard...")
response = session.get(f"{BASE_URL}/dashboard")
if response.status_code == 200:
    menu_items = [
        ("Benutzerverwaltung", "User Management menu"),
        ("Öffnungszeiten", "Opening Hours menu"),
        ("White-Label", "White-Label menu"),
    ]

    for text, description in menu_items:
        if text in response.text:
            print(f"✅ {description:30} - Found in navigation")
        else:
            print(f"❌ {description:30} - NOT found in navigation")
            # Check if it's a session issue
            if 'session.role' in response.text:
                print("   ⚠️  Template may be checking session.role incorrectly")
            if 'session.user.role' in response.text:
                print("   ⚠️  Template may be checking session.user.role")

print("\n" + "=" * 50)
print("Test complete!")