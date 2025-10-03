#!/usr/bin/env python3
"""
PAN Migration Script
====================
Migrates plaintext PANs to hashed PANs in nfc_cards.json for PCI DSS compliance.

This script:
1. Backs up the existing nfc_cards.json file
2. Reads all scan records
3. Converts plaintext 'pan' fields to 'pan_hash' + 'pan_last4'
4. Saves the migrated data
5. Verifies the migration

IMPORTANT: Run this script ONCE before deploying the updated code.
"""

import json
import os
import sys
import shutil
from datetime import datetime

# Add app directory to path so we can import pan_security
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.pan_security import hash_pan, mask_pan, sanitize_pan_for_logging

# File paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CARDS_DATA_FILE = os.path.join(DATA_DIR, "nfc_cards.json")
BACKUP_FILE = os.path.join(DATA_DIR, f"nfc_cards_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")


def migrate_pan_data():
    """
    Migrate plaintext PANs to hashed format.
    """
    print("=" * 70)
    print("PCI DSS PAN MIGRATION SCRIPT")
    print("=" * 70)
    print()

    # Check if file exists
    if not os.path.exists(CARDS_DATA_FILE):
        print(f"⚠️  No data file found at: {CARDS_DATA_FILE}")
        print("   Creating new empty file with correct structure...")
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CARDS_DATA_FILE, 'w') as f:
            json.dump({'recent_card_scans': []}, f, indent=2)
        print("✅ Empty data file created. No migration needed.")
        return

    # Backup original file
    print(f"📦 Creating backup: {BACKUP_FILE}")
    shutil.copy2(CARDS_DATA_FILE, BACKUP_FILE)
    print("✅ Backup created successfully")
    print()

    # Load existing data
    print(f"📖 Loading data from: {CARDS_DATA_FILE}")
    with open(CARDS_DATA_FILE, 'r') as f:
        data = json.load(f)

    scans = data.get('recent_card_scans', [])
    print(f"   Found {len(scans)} scan records")
    print()

    if len(scans) == 0:
        print("ℹ️  No scans to migrate. Exiting.")
        return

    # Migrate each scan
    migrated_count = 0
    already_hashed_count = 0
    error_count = 0

    print("🔄 Migrating scan records...")
    print()

    for i, scan in enumerate(scans):
        try:
            # Check if already migrated
            if 'pan_hash' in scan and 'pan_last4' in scan:
                already_hashed_count += 1
                # Remove legacy 'pan' field if it exists
                if 'pan' in scan:
                    del scan['pan']
                continue

            # Check if has legacy plaintext PAN
            if 'pan' not in scan:
                print(f"   ⚠️  Scan {i+1}: No PAN field found, skipping")
                continue

            # Get plaintext PAN
            pan = scan['pan']

            # Normalize PAN
            pan_normalized = str(pan).replace(" ", "").replace("-", "").strip()

            # Hash it
            pan_hash = hash_pan(pan_normalized)
            pan_last4 = pan_normalized[-4:] if len(pan_normalized) >= 4 else ""

            # Update record
            scan['pan_hash'] = pan_hash
            scan['pan_last4'] = pan_last4

            # Remove plaintext PAN
            del scan['pan']

            migrated_count += 1

            # Show progress
            if migrated_count % 10 == 0 or migrated_count <= 5:
                print(f"   ✅ Migrated scan {i+1}: {sanitize_pan_for_logging(pan_normalized)} -> {pan_hash[:16]}...")

        except Exception as e:
            error_count += 1
            print(f"   ❌ Error migrating scan {i+1}: {e}")

    print()
    print("=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)
    print(f"Total scans:          {len(scans)}")
    print(f"Migrated:             {migrated_count}")
    print(f"Already hashed:       {already_hashed_count}")
    print(f"Errors:               {error_count}")
    print()

    if error_count > 0:
        print("⚠️  WARNING: Some records failed to migrate!")
        response = input("Continue with save? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Migration aborted. Original file unchanged.")
            return

    # Save migrated data
    print(f"💾 Saving migrated data to: {CARDS_DATA_FILE}")
    with open(CARDS_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print("✅ Migration completed successfully!")
    print()
    print(f"📁 Backup saved at: {BACKUP_FILE}")
    print()

    # Verify migration
    print("🔍 Verifying migration...")
    with open(CARDS_DATA_FILE, 'r') as f:
        verify_data = json.load(f)

    verify_scans = verify_data.get('recent_card_scans', [])
    plaintext_count = sum(1 for scan in verify_scans if 'pan' in scan)
    hashed_count = sum(1 for scan in verify_scans if 'pan_hash' in scan and 'pan_last4' in scan)

    print(f"   Records with plaintext PAN: {plaintext_count}")
    print(f"   Records with hashed PAN:    {hashed_count}")

    if plaintext_count > 0:
        print()
        print("⚠️  WARNING: Some plaintext PANs still exist!")
        print("   You may want to review these records manually.")
    else:
        print()
        print("✅ SUCCESS: All PANs have been hashed!")

    print()
    print("=" * 70)
    print("NEXT STEPS:")
    print("=" * 70)
    print("1. Review the migrated data in:", CARDS_DATA_FILE)
    print("2. Test the application to ensure NFC card recognition still works")
    print("3. If everything works, you can delete the backup file")
    print("4. Deploy the updated application")
    print()


def rollback_migration():
    """
    Rollback to the most recent backup.
    """
    print("=" * 70)
    print("ROLLBACK MIGRATION")
    print("=" * 70)
    print()

    # Find most recent backup
    backups = [f for f in os.listdir(DATA_DIR) if f.startswith('nfc_cards_backup_')]
    if not backups:
        print("❌ No backup files found!")
        return

    backups.sort(reverse=True)
    most_recent = os.path.join(DATA_DIR, backups[0])

    print(f"📦 Most recent backup: {most_recent}")
    response = input("Restore this backup? (yes/no): ")

    if response.lower() == 'yes':
        shutil.copy2(most_recent, CARDS_DATA_FILE)
        print("✅ Backup restored successfully!")
    else:
        print("❌ Rollback cancelled.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
        rollback_migration()
    else:
        migrate_pan_data()
