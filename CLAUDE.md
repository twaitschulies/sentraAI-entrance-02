# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Guard NFC/QR v2** - A physical door access control system running on Raspberry Pi 4b, using NFC bank cards and QR codes for authentication. This is a production security system that controls real physical door access.

## Critical Context

- **PRIMARY FUNCTION**: NFC bank card (EMV) authentication for door access
- **ZERO TOLERANCE**: NFC failures = people locked out
- **HARDWARE**: Raspberry Pi 4b (4GB RAM, ARM architecture, SD card storage)
- **GPIO**: Pin 17 controls door relay
- **READERS**: ACR122U or PC/SC compatible NFC, USB HID barcode scanners

## 🔴 CRITICAL: Session Role Handling Pattern

### Known Recurring Issue
New admin features often aren't visible because of session variable misconfiguration. This MUST be handled correctly:

**THE PATTERN THAT WORKS:**
```python
# In login route - ALWAYS set role at root level:
if user:
    session['user'] = user
    session['role'] = user.get('role', 'user')  # CRITICAL: Templates expect this at root
    session['username'] = username
    session.permanent = True
```

**In Templates:**
```html
<!-- CORRECT: Use session.role -->
{% if session.role == 'admin' %}

<!-- WRONG: Don't use these -->
{% if session.user.role == 'admin' %}  <!-- NO! -->
{% if session.get('user_role') == 'admin' %}  <!-- NO! -->
```

**See `IMPLEMENTATION_CHECKLIST.md` for complete feature implementation guide.**

## Time-Based Door Control System

### New Advanced Door Control Features

The system now includes a comprehensive time-based door control system with three distinct operational modes:

**🟢 Always Open Mode (Default: 08:00-16:00 weekdays)**
- GPIO pin permanently HIGH during configured timeframe
- No NFC/barcode scanning required for entry
- Ideal for business hours with high foot traffic
- QR exit scanning remains functional

**🔵 Normal Operation Mode (Default: 16:00-04:00)**
- GPIO defaults to LOW state
- NFC card and barcode scans trigger temporary HIGH for door opening
- Standard access control behavior
- All authentication methods active

**🔴 Access Blocked Mode (Default: 04:00-08:00)**
- GPIO stays LOW regardless of NFC scans
- NFC entry attempts are rejected with logging
- QR/barcode exit scanning ALWAYS works (fail-safe for emergency egress)
- Ideal for overnight/maintenance hours

### Key Components

- **Door Control Manager** (`app/models/door_control.py`) - Core time-based logic
- **Enhanced GPIO Control** (`app/gpio_control.py`) - Hardware integration
- **API Endpoints** (`app/routes.py`) - Configuration and status APIs
- **Background Monitoring** - Automatic mode transitions every 30 seconds
- **Fail-Safe Design** - QR exits always work regardless of mode

### Configuration

Door control settings are stored in `/data/door_control.json` and managed via the Opening Hours page in the admin interface.

## Common Development Commands

```bash
# Start development server (local testing)
python3 wsgi.py

# Test the new door control system
python3 test_door_control_system.py

# Service management (production)
sudo systemctl status qrverification
sudo systemctl restart qrverification
sudo systemctl stop qrverification

# View logs
sudo journalctl -u qrverification -f
sudo journalctl -u qrverification -n 50

# Installation/Update
sudo ./install.sh

# Create system backup
./backup_system.sh

# Test NFC reader
pcsc_scan
python3 -c "from smartcard.System import readers; print(readers())"

# Test GPIO
python3 -c "from app.gpio_control import pulse, get_gpio_state; print('GPIO:', get_gpio_state()); pulse()"

# Fix dependencies
./fix_dependencies.sh

# Generate SSL certificates
./generate_ssl.sh
```

## Architecture Overview

### Core Components

1. **Flask Application** (`app/__init__.py`)
   - Entry point: `wsgi.py`
   - Gunicorn WSGI server in production
   - Nginx reverse proxy on port 80

2. **NFC System** (Multiple implementations - needs consolidation)
   - `app/nfc_reader.py` - Main NFC reader
   - `app/nfc_reader_enhanced.py` - Enhanced version
   - `app/nfc_enhanced.py` - Alternative enhancement
   - Uses pyscard library for PC/SC readers
   - **CRITICAL**: Must handle disconnections/reconnections

3. **QR/Barcode Scanner** (`app/scanner.py`)
   - Uses evdev for HID input devices
   - Thread-based scanning
   - Supports temporary (24h reset) and permanent codes

4. **GPIO Control** (`app/gpio_control.py`)
   - Controls door relay on GPIO pin 17
   - Uses gpiozero/lgpio for Pi 5 compatibility
   - Pulse duration for door unlock

5. **User Management** (`app/models/user.py`)
   - Admin user: admin/admin (hardcoded fallback)
   - JSON-based storage in `data/users.json`
   - Session-based authentication

### Data Storage

- **JSON Files** (Problem: Not production-ready)
  - `data/users.json` - User accounts
  - `data/scan_data.json` - QR scan history
  - `data/nfc_cards.json` - NFC card registry
- **SQLite Databases** (Partially implemented)
  - `data/fallback_log.sqlite` - Fallback logging
  - `data/nfc_raw_data_analysis.db` - NFC analysis
- **Text Files**
  - `barcode_database.txt` - Temporary QR codes
  - `permanent_barcodes.txt` - Permanent QR codes

### Multiple Logging Systems (Needs consolidation)

- Standard Python logging (`app/logging_setup.py`)
- Error logger (`app/error_logger.py`)
- Webhook logger (`app/webhook_logger.py`)
- Structured fallback log (`app/structured_fallback_log.py`)
- Safe logging (`app/safe_logging.py`)

## Critical Issues to Address

1. **NFC Stability**
   - Connection drops after ~100 reads
   - No automatic reconnection
   - Memory leaks in pyscard
   - Multiple competing implementations

2. **Security Vulnerabilities**
   - Hardcoded admin/admin credentials
   - No HTTPS by default
   - Passwords stored in plaintext
   - No input validation in some routes

3. **Code Duplication**
   - Multiple NFC reader implementations
   - Multiple logging systems
   - Multiple card enhancement modules

4. **Production Readiness**
   - Flask dev server sometimes used
   - JSON files instead of proper database
   - No connection pooling for NFC
   - No proper error recovery

## Hardware Constraints (Raspberry Pi 4b)

- **RAM**: 4GB total, ~3GB usable
- **Storage**: SD card (minimize writes!)
- **CPU**: ARM Cortex-A72 (not x86)
- **Power**: USB powered (can be unstable)
- **Heat**: CPU throttling issues

## Development Guidelines

### When Modifying Code

1. **ALWAYS update `install.sh`** for new dependencies
2. **Test on real Pi 4b hardware** before deployment
3. **Handle all exceptions** - crashes lock people out
4. **Clean up resources** (GPIO, NFC connections)
5. **Use logging, not print()** for debugging
6. **Validate all user input** - security critical
7. **Consider SD card wear** - minimize writes

### Performance Targets

- NFC read time: <500ms
- Web response: <200ms (95th percentile)
- System boot: <60 seconds
- Memory usage: <500MB
- NFC success rate: >99.9%

### Code Style

- Follow existing patterns in the codebase
- Use type hints where appropriate
- Document critical functions
- Keep functions focused and testable

## Testing Requirements

For any changes to NFC or door control:

1. Test 1000+ consecutive NFC reads
2. Test power loss recovery
3. Test concurrent access
4. Verify memory usage stays stable
5. Test with actual door hardware

## Important Files

- `app/nfc_reader.py` - Core NFC logic (CRITICAL)
- `app/gpio_control.py` - Door control (CRITICAL)
- `app/scanner.py` - QR/barcode scanning
- `app/routes.py` - Web API endpoints
- `install.sh` - Deployment script (KEEP SYNCED!)
- `requirements.txt` - Python dependencies

## System Services

The application runs as a systemd service:
- Service file: `/etc/systemd/system/qrverification.service`
- Nginx config: `/etc/nginx/sites-available/qrverification`
- Working directory: Installation directory
- User: root (for GPIO access)

## Common Pitfalls

1. **Never** use blocking I/O in main thread
2. **Never** trust user input without validation
3. **Never** forget to update install.sh
4. **Never** skip resource cleanup (GPIO, connections)
5. **Never** ignore pcscd service status for NFC

## Debugging Commands

```bash
# Check if pcscd is running (required for NFC)
sudo systemctl status pcscd

# List all input devices (for scanner)
ls -la /dev/input/

# Check GPIO permissions
ls -la /dev/gpiomem

# Monitor system resources
htop

# Check SD card wear
sudo smartctl -a /dev/mmcblk0
```

## Current State Notes

- Multiple overlapping NFC implementations need consolidation
- Logging system is fragmented across multiple modules
- "Allow All Barcodes" mode exists (bypasses all security)
- Admin credentials reset to admin/admin on every restart
- Some enhanced modules may not be fully integrated