from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, request, session, make_response
from app.gpio_control import open_door, close_door, get_gpio_state
from app.scanner import load_codes, get_current_scans
from app.nfc_reader import get_registered_cards, get_current_card_scans, register_card, delete_card, load_device_config, save_device_config
from datetime import datetime, timedelta, time as datetime_time
from app.models.user import user_manager
from app.models.opening_hours import opening_hours_manager
from app.models.whitelabel import whitelabel_manager
from app.models.network import network_manager
# PCI DSS Compliance: PAN Security Module
from app.pan_security import hash_pan, mask_pan, verify_pan, is_hashed_pan, sanitize_pan_for_logging
import os
import json
import subprocess
from functools import wraps
import logging
import re
import random
import time

logger = logging.getLogger(__name__)

# Import unified logger functions
try:
    from app.unified_logger import unified_logger, log_info, log_error, log_warning, log_system, log_auth, log_door, log_nfc
except ImportError:
    # Fallback if unified logger not available
    pass



bp = Blueprint("routes", __name__)

# Context processor to make whitelabel_manager available in all templates
@bp.context_processor
def inject_whitelabel():
    return dict(whitelabel_manager=whitelabel_manager)

# Context processor to make barcode visibility available in all templates
@bp.context_processor
def inject_barcode_visibility():
    settings = load_settings()
    return dict(barcode_visibility_enabled=settings.get('barcode_visibility_enabled', True))

# Einfache Authentifizierung ohne Security-Modul
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Sie müssen sich anmelden, um auf diese Seite zuzugreifen.', 'error')
            return redirect(url_for('routes.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Legacy decorator for admin-only access. Use permission_required instead for new code."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Sie müssen sich anmelden, um auf diese Seite zuzugreifen.', 'error')
            return redirect(url_for('routes.login'))

        username = session.get('username')

        # System users (sentrasupport and kassen24) have admin rights
        if username in ['sentrasupport', 'kassen24']:
            return f(*args, **kwargs)

        if session['user'].get('role') != 'admin':
            flash('Sie haben keine Berechtigung für diese Aktion.', 'error')
            return redirect(url_for('routes.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def whitelabel_access_required(f):
    """Decorator for whitelabel configuration - Only sentrasupport and kassen24 users."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Sie müssen sich anmelden, um auf diese Seite zuzugreifen.', 'error')
            return redirect(url_for('routes.login'))

        username = session.get('username')

        # Only allow sentrasupport and kassen24 users
        if username not in ['sentrasupport', 'kassen24']:
            flash('Sie haben keine Berechtigung für die Whitelabel-Konfiguration.', 'error')
            return redirect(url_for('routes.dashboard'))

        return f(*args, **kwargs)
    return decorated_function

def permission_required(permission):
    """Decorator to check if user has a specific page permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                flash('Sie müssen sich anmelden, um auf diese Seite zuzugreifen.', 'error')
                return redirect(url_for('routes.login'))

            username = session.get('username')

            # Spezielle Behandlung für system users - haben immer alle Rechte
            if username in ['sentrasupport', 'kassen24']:
                return f(*args, **kwargs)

            # Normale Berechtigungsprüfung
            if not username or not user_manager.has_page_access(username, permission):
                flash('Sie haben keine Berechtigung für diese Seite.', 'error')
                return redirect(url_for('routes.dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Sie müssen sich anmelden, um auf diese Seite zuzugreifen.', 'error')
            return redirect(url_for('routes.login'))

        username = session.get('username')

        # System users haben Manager-Rechte
        if username in ['sentrasupport', 'kassen24']:
            return f(*args, **kwargs)

        if session['user'].get('role') not in ['admin', 'manager']:
            flash('Sie haben keine Berechtigung für diese Aktion.', 'error')
            return redirect(url_for('routes.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Konfigurationsdatei für Einstellungen - KORRIGIERT: Verwende config.json aus dem Stammverzeichnis
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

def load_settings():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                settings = json.load(f)
                # Ensure door_open_time exists with default value
                if 'door_open_time' not in settings:
                    settings['door_open_time'] = 1.5
                # Ensure allow_all_barcodes exists with default value
                if 'allow_all_barcodes' not in settings:
                    settings['allow_all_barcodes'] = False
                # Ensure webhook settings exist with default values
                if 'nfc_webhook_url' not in settings:
                    settings['nfc_webhook_url'] = ''
                if 'barcode_webhook_url' not in settings:
                    settings['barcode_webhook_url'] = ''
                if 'webhook_enabled' not in settings:
                    settings['webhook_enabled'] = True
                if 'webhook_timeout' not in settings:
                    settings['webhook_timeout'] = 5
                if 'webhook_auth_user' not in settings:
                    settings['webhook_auth_user'] = ''
                if 'webhook_auth_password' not in settings:
                    settings['webhook_auth_password'] = ''
                if 'webhook_auth_type' not in settings:
                    settings['webhook_auth_type'] = 'digest'
                if 'nfc_webhook_delay' not in settings:
                    settings['nfc_webhook_delay'] = 0.0
                if 'barcode_webhook_delay' not in settings:
                    settings['barcode_webhook_delay'] = 0.0
                # Add barcode visibility setting (only sentrasupport can change)
                if 'barcode_visibility_enabled' not in settings:
                    settings['barcode_visibility_enabled'] = True  # Default: show barcode features
                return settings
        except Exception as e:
            logging.getLogger(__name__).warning(f"Fehler beim Laden der Konfiguration: {e}")
    return {
        'username': 'admin',
        'password': 'admin',
        'door_open_time': 1.5,
        'allow_all_barcodes': False,
        'nfc_webhook_url': '',
        'barcode_webhook_url': '',
        'webhook_enabled': True,
        'webhook_timeout': 5,
        'webhook_auth_user': '',
        'webhook_auth_password': '',
        'webhook_auth_type': 'digest',  # 'none', 'basic', 'digest'
        'nfc_webhook_delay': 0.0,
        'barcode_webhook_delay': 0.0,
        'barcode_visibility_enabled': True  # Default: show barcode features
    }

def save_settings(settings):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

        # Load existing settings first to preserve data not in current settings dict
        existing_settings = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    existing_settings = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"JSON Decode Error in config file: {e}")
                # If config is corrupted, backup and start fresh
                backup_file = CONFIG_FILE + '.backup.' + str(int(time.time()))
                os.rename(CONFIG_FILE, backup_file)
                logger.warning(f"Corrupted config backed up to: {backup_file}")
            except Exception as e:
                logger.error(f"Error loading existing config: {e}")

        # Merge settings, preserving webhook settings if not explicitly provided
        webhook_keys = ['webhook_enabled', 'nfc_webhook_url', 'barcode_webhook_url',
                       'webhook_timeout', 'webhook_auth_user', 'webhook_auth_password',
                       'webhook_auth_type', 'nfc_webhook_delay', 'barcode_webhook_delay']

        # Log webhook settings persistence
        webhook_preserved = False
        for key in webhook_keys:
            if key not in settings and key in existing_settings:
                settings[key] = existing_settings[key]
                webhook_preserved = True

        if webhook_preserved:
            logger.debug("Webhook settings preserved from existing config")

        # Log the webhook_enabled state being saved
        if 'webhook_enabled' in settings:
            logger.info(f"Saving webhook_enabled state: {settings['webhook_enabled']}")

        # Use atomic write to prevent corruption
        temp_file = CONFIG_FILE + '.tmp'
        with open(temp_file, 'w') as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)

        # Atomic rename
        os.replace(temp_file, CONFIG_FILE)
        logger.debug("Settings saved successfully")

    except Exception as e:
        logger.error(f"Critical error saving configuration: {e}")
        raise  # Re-raise to ensure caller knows save failed

def load_permanent_codes():
    try:
        with open('permanent_barcodes.txt', 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def load_temporary_codes():
    try:
        with open('barcode_database.txt', 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def save_permanent_codes(codes):
    with open('permanent_barcodes.txt', 'w') as f:
        for code in codes:
            f.write(f"{code}\n")

def save_temporary_codes(codes):
    with open('barcode_database.txt', 'w') as f:
        for code in codes:
            f.write(f"{code}\n")

def restart_service():
    try:
        subprocess.run(['sudo', 'systemctl', 'restart', 'qrverification.service'])
        return True
    except Exception as e:
        print(f"Fehler beim Neustarten des Services: {e}")
        return False

@bp.route("/login", methods=["GET", "POST"])
def login():
    # Wenn der Benutzer bereits angemeldet ist, leite zum Dashboard weiter
    if 'user' in session:
        return redirect(url_for('routes.dashboard'))
    
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')
        
        # IP-Adresse des Benutzers ermitteln
        ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
        user = user_manager.authenticate(username, password, ip_address)
        
        if user:
            # Erfolgreiche Anmeldung - Einfache Session
            session['user'] = user
            session['role'] = user.get('role', 'user')  # Add role to session root for template access
            session['username'] = username  # Add username for convenience
            session.permanent = True

            # Enhanced login logging with context
            try:
                log_auth(f"User login successful", username=username,
                        extra_context={
                            'ip_address': ip_address,
                            'user_role': user.get('role', 'user'),
                            'login_time': datetime.now().isoformat()
                        })
            except:
                # Fallback to basic logging if unified logger fails
                logging.info(f"Erfolgreiche Anmeldung für Benutzer: {username} von IP: {ip_address}")

            # Prüfe ob Passwortänderung erzwungen wird
            if user.get('force_password_change', False):
                flash('Bitte ändern Sie Ihr Passwort aus Sicherheitsgründen.', 'warning')
                return redirect(url_for('routes.change_password'))

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('routes.dashboard'))
        
        # Enhanced failed login logging with context
        try:
            log_auth(f"User login failed", username=username,
                    extra_context={
                        'ip_address': ip_address,
                        'attempt_time': datetime.now().isoformat(),
                        'reason': 'Invalid credentials'
                    })
        except:
            # Fallback to basic logging if unified logger fails
            logging.warning(f"Fehlgeschlagene Anmeldung für Benutzer: {username} von IP: {ip_address}")

        flash('Ungültiger Benutzername oder Passwort.', 'danger')
    
    return render_template('login.html')

@bp.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        username = session.get('username')

        if new_password != confirm_password:
            flash('Neue Passwörter stimmen nicht überein.', 'danger')
            return render_template('change_password.html')

        if len(new_password) < 8:
            flash('Neues Passwort muss mindestens 8 Zeichen lang sein.', 'danger')
            return render_template('change_password.html')

        if user_manager.change_password(username, current_password, new_password):
            # Entferne force_password_change Flag
            user_manager.update_user(username, {"force_password_change": False})
            flash('Passwort erfolgreich geändert!', 'success')
            return redirect(url_for('routes.dashboard'))
        else:
            flash('Aktuelles Passwort ist falsch.', 'danger')

    return render_template('change_password.html')

@bp.route("/logout")
def logout():
    username = session.get('user', {}).get('username', 'Unbekannt')
    user_role = session.get('role', 'unknown')

    # Enhanced logout logging with context
    try:
        log_auth(f"User logout", username=username,
                extra_context={
                    'logout_time': datetime.now().isoformat(),
                    'user_role': user_role,
                    'session_duration': 'unknown'  # Could calculate from login time if stored
                })
    except:
        # Fallback to basic logging if unified logger fails
        logging.info(f"Benutzer abgemeldet: {username}")

    session.clear()
    flash('Sie wurden erfolgreich abgemeldet.', 'success')
    return redirect(url_for('routes.login'))

@bp.route("/users")
@permission_required('users')
def users():
    users_list = user_manager.get_all_users()

    # Hole Login-Historie mit Pagination
    page = request.args.get('login_page', 1, type=int)
    per_page = 10  # 10 Einträge pro Seite
    login_history, total_logins, total_login_pages = user_manager.get_login_history(page=page, per_page=per_page)

    return render_template('users.html',
                         users=users_list,
                         login_history=login_history,
                         login_page=page,
                         total_login_pages=total_login_pages,
                         total_logins=total_logins)

@bp.route("/add_user", methods=["POST"])
@permission_required('users')
def add_user():
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'employee')
    name = request.form.get('name', '')
    email = request.form.get('email', '')
    phone = request.form.get('phone', '')

    if not username or not password:
        flash('Benutzername und Passwort sind erforderlich.', 'danger')
        return redirect(url_for('routes.users'))

    success = user_manager.create_user(
        username=username,
        password=password,
        role=role,
        name=name,
        email=email,
        phone=phone
    )

    if success:
        flash(f'Benutzer {username} wurde erfolgreich erstellt.', 'success')
    else:
        flash(f'Fehler beim Erstellen des Benutzers {username}.', 'danger')

    return redirect(url_for('routes.users'))

@bp.route("/update_user", methods=["POST"])
@permission_required('users')
def update_user():
    username = request.form.get('username')
    data = {}

    # Handle all form fields
    if request.form.get('password'):
        data['password'] = request.form.get('password')

    if request.form.get('role'):
        data['role'] = request.form.get('role')

    # Handle new fields (always update, even if empty)
    data['name'] = request.form.get('name', '')
    data['email'] = request.form.get('email', '')
    data['phone'] = request.form.get('phone', '')

    if not username:
        flash('Benutzername ist erforderlich.', 'danger')
        return redirect(url_for('routes.users'))

    success = user_manager.update_user(username, data)

    if success:
        flash(f'Benutzer {username} wurde erfolgreich aktualisiert.', 'success')
    else:
        flash(f'Fehler beim Aktualisieren des Benutzers {username}.', 'danger')

    return redirect(url_for('routes.users'))

@bp.route("/delete_user", methods=["POST"])
@permission_required('users')
def delete_user():
    username = request.form.get('username')
    
    if not username:
        flash('Benutzername ist erforderlich.', 'danger')
        return redirect(url_for('routes.users'))
    
    # Verhindere das Löschen des eigenen Accounts
    if username == session.get('username'):
        flash('Sie können Ihren eigenen Account nicht löschen.', 'danger')
        return redirect(url_for('routes.users'))
    
    success = user_manager.delete_user(username)
    
    if success:
        flash(f'Benutzer {username} wurde erfolgreich gelöscht.', 'success')
    else:
        flash(f'Fehler beim Löschen des Benutzers {username}.', 'danger')
    
    return redirect(url_for('routes.users'))

@bp.route("/get_user_permissions")
@permission_required('users')
def get_user_permissions():
    """Get user permissions as JSON for AJAX requests."""
    username = request.args.get('username')

    if not username:
        return jsonify({"error": "Username required"}), 400

    permissions = user_manager.get_user_permissions(username)
    return jsonify(permissions)

@bp.route("/update_user_permissions", methods=["POST"])
@permission_required('users')
def update_user_permissions():
    """Update user permissions."""
    username = request.form.get('username')

    if not username:
        flash('Benutzername ist erforderlich.', 'danger')
        return redirect(url_for('routes.users'))

    # Get selected permissions from form
    selected_permissions = request.form.getlist('permissions[]')

    # Get all available permissions and create a permission dict
    all_permissions = user_manager.get_available_permissions()
    permissions = {}

    for permission in all_permissions:
        permissions[permission] = permission in selected_permissions

    success = user_manager.update_user_permissions(username, permissions)

    if success:
        flash(f'Berechtigungen für Benutzer {username} wurden erfolgreich aktualisiert.', 'success')
    else:
        flash(f'Fehler beim Aktualisieren der Berechtigungen für Benutzer {username}.', 'danger')

    return redirect(url_for('routes.users'))

# Opening Hours Management Routes
@bp.route("/opening_hours")
@admin_required
def opening_hours():
    """Display opening hours configuration page."""
    config = opening_hours_manager.get_hours()

    # Also load door control configuration
    try:
        from app.models.door_control_simple import simple_door_control_manager as door_control_manager
        door_config = door_control_manager.get_config()
    except Exception as e:
        logger.error(f"Error loading door control config: {e}")
        door_config = None

    return render_template('opening_hours.html', config=config, door_config=door_config)

@bp.route("/opening_hours/update", methods=["POST"])
@admin_required
def update_opening_hours():
    """Update opening hours configuration."""
    try:
        config = {
            "enabled": request.form.get('enabled') == 'on',
            "weekdays": {}
        }

        # Update weekday hours
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            config['weekdays'][day] = {
                'enabled': request.form.get(f'{day}_enabled') == 'on',
                'start': request.form.get(f'{day}_start', '00:00'),
                'end': request.form.get(f'{day}_end', '23:59')
            }

        # Preserve holidays and exceptions
        current_config = opening_hours_manager.get_hours()
        config['holidays'] = current_config.get('holidays', [])
        config['exceptions'] = current_config.get('exceptions', [])

        # Get previous config for logging changes
        previous_config = current_config.copy()

        if opening_hours_manager.update_hours(config):
            # Log the opening hours changes
            username = session.get('username', 'unknown')
            try:
                log_system(f"Opening hours configuration updated",
                          extra_context={
                              'changed_by': username,
                              'previous_enabled': previous_config.get('enabled', False),
                              'new_enabled': config['enabled'],
                              'weekdays_changed': config['weekdays'],
                              'change_time': datetime.now().isoformat()
                          })
            except:
                logging.info(f"Öffnungszeiten geändert von {username}")

            flash('Öffnungszeiten wurden erfolgreich aktualisiert.', 'success')
        else:
            flash('Fehler beim Aktualisieren der Öffnungszeiten.', 'danger')
    except Exception as e:
        flash(f'Fehler: {str(e)}', 'danger')

    return redirect(url_for('routes.opening_hours'))

@bp.route("/opening_hours/holiday/add", methods=["POST"])
@admin_required
def add_holiday():
    """Add a holiday date."""
    date_str = request.form.get('date')
    if date_str:
        if opening_hours_manager.add_holiday(date_str):
            # Log holiday addition
            username = session.get('username', 'unknown')
            try:
                log_system(f"Holiday date added",
                          extra_context={
                              'changed_by': username,
                              'holiday_date': date_str,
                              'change_time': datetime.now().isoformat()
                          })
            except:
                logging.info(f"Feiertag {date_str} hinzugefügt von {username}")

            flash(f'Feiertag {date_str} wurde hinzugefügt.', 'success')
        else:
            flash('Fehler beim Hinzufügen des Feiertags.', 'danger')
    return redirect(url_for('routes.opening_hours'))

@bp.route("/opening_hours/holiday/remove", methods=["POST"])
@admin_required
def remove_holiday():
    """Remove a holiday date."""
    date_str = request.form.get('date')
    if date_str:
        if opening_hours_manager.remove_holiday(date_str):
            # Log holiday removal
            username = session.get('username', 'unknown')
            try:
                log_system(f"Holiday date removed",
                          extra_context={
                              'changed_by': username,
                              'holiday_date': date_str,
                              'change_time': datetime.now().isoformat()
                          })
            except:
                logging.info(f"Feiertag {date_str} entfernt von {username}")

            flash(f'Feiertag {date_str} wurde entfernt.', 'success')
        else:
            flash('Fehler beim Entfernen des Feiertags.', 'danger')
    return redirect(url_for('routes.opening_hours'))

@bp.route("/opening_hours/exception/add", methods=["POST"])
@admin_required
def add_exception():
    """Add an exception date with special hours."""
    date_str = request.form.get('date')
    enabled = request.form.get('enabled') == 'on'
    start = request.form.get('start', '00:00')
    end = request.form.get('end', '23:59')

    if date_str:
        if opening_hours_manager.add_exception(date_str, enabled, start, end):
            # Log exception addition
            username = session.get('username', 'unknown')
            try:
                log_system(f"Opening hours exception added",
                          extra_context={
                              'changed_by': username,
                              'exception_date': date_str,
                              'enabled': enabled,
                              'start_time': start,
                              'end_time': end,
                              'change_time': datetime.now().isoformat()
                          })
            except:
                logging.info(f"Ausnahme für {date_str} hinzugefügt von {username}")

            flash(f'Ausnahme für {date_str} wurde hinzugefügt.', 'success')
        else:
            flash('Fehler beim Hinzufügen der Ausnahme.', 'danger')
    return redirect(url_for('routes.opening_hours'))

@bp.route("/opening_hours/exception/remove", methods=["POST"])
@admin_required
def remove_exception():
    """Remove an exception date."""
    date_str = request.form.get('date')
    if date_str:
        if opening_hours_manager.remove_exception(date_str):
            # Log exception removal
            username = session.get('username', 'unknown')
            try:
                log_system(f"Opening hours exception removed",
                          extra_context={
                              'changed_by': username,
                              'exception_date': date_str,
                              'change_time': datetime.now().isoformat()
                          })
            except:
                logging.info(f"Ausnahme für {date_str} entfernt von {username}")

            flash(f'Ausnahme für {date_str} wurde entfernt.', 'success')
        else:
            flash('Fehler beim Entfernen der Ausnahme.', 'danger')
    return redirect(url_for('routes.opening_hours'))

# White-label Configuration Routes
@bp.route("/whitelabel")
@whitelabel_access_required
def whitelabel():
    """Display white-label configuration page."""
    config = whitelabel_manager.get_config()
    return render_template('whitelabel.html', config=config)

@bp.route("/whitelabel/update", methods=["POST"])
@whitelabel_access_required
def update_whitelabel():
    """Update white-label configuration."""
    try:
        updates = {
            "enabled": request.form.get('enabled') == 'on',
            "company_name": request.form.get('company_name', 'Zugangssystem'),
            "primary_color": request.form.get('primary_color', '#0d6efd'),
            "secondary_color": request.form.get('secondary_color', '#6c757d'),
            "accent_color": request.form.get('accent_color', '#28a745'),
            "danger_color": request.form.get('danger_color', '#dc3545'),
            "warning_color": request.form.get('warning_color', '#ffc107'),
            "info_color": request.form.get('info_color', '#17a2b8'),
            "header_bg_color": request.form.get('header_bg_color', '#343a40'),
            "sidebar_bg_color": request.form.get('sidebar_bg_color', '#212529'),
            "font_family": request.form.get('font_family', 'Inter, sans-serif'),
            "custom_css": request.form.get('custom_css', ''),
            "footer_text": request.form.get('footer_text', ''),
            "login_page_title": request.form.get('login_page_title', 'Zugangssystem Login'),
            "login_page_subtitle": request.form.get('login_page_subtitle', 'Bitte melden Sie sich an'),
            "dashboard_title": request.form.get('dashboard_title', 'Dashboard')
        }

        # Handle logo upload
        if 'logo_file' in request.files:
            logo = request.files['logo_file']
            if logo and logo.filename:
                updates['logo_file'] = logo.read()

        # Handle favicon upload
        if 'favicon_file' in request.files:
            favicon = request.files['favicon_file']
            if favicon and favicon.filename:
                updates['favicon_file'] = favicon.read()

        # Get previous config for logging
        previous_config = whitelabel_manager.get_config()

        if whitelabel_manager.update_config(updates):
            # Log whitelabel changes
            username = session.get('username', 'unknown')
            changed_fields = []

            # Track specific changes (without logging large file data)
            for key, new_value in updates.items():
                if key not in ['logo_file', 'favicon_file']:
                    old_value = previous_config.get(key, '')
                    if str(old_value) != str(new_value):
                        changed_fields.append(f"{key}: '{old_value}' → '{new_value}'")
                elif key in ['logo_file', 'favicon_file'] and new_value:
                    changed_fields.append(f"{key}: file_updated")

            try:
                log_system(f"White-label configuration updated",
                          extra_context={
                              'changed_by': username,
                              'changed_fields': changed_fields,
                              'change_time': datetime.now().isoformat()
                          })
            except:
                logging.info(f"White-Label-Konfiguration geändert von {username}")

            flash('White-Label-Konfiguration wurde erfolgreich aktualisiert.', 'success')
        else:
            flash('Fehler beim Aktualisieren der White-Label-Konfiguration.', 'danger')
    except Exception as e:
        flash(f'Fehler: {str(e)}', 'danger')

    return redirect(url_for('routes.whitelabel'))

@bp.route("/whitelabel/reset", methods=["POST"])
@whitelabel_access_required
def reset_whitelabel():
    """Reset white-label configuration to defaults."""
    if whitelabel_manager.reset_to_defaults():
        # Log whitelabel reset
        username = session.get('username', 'unknown')
        try:
            log_system(f"White-label configuration reset to defaults",
                      extra_context={
                          'changed_by': username,
                          'action': 'reset_to_defaults',
                          'change_time': datetime.now().isoformat()
                      })
        except:
            logging.info(f"White-Label-Konfiguration zurückgesetzt von {username}")

        flash('White-Label-Konfiguration wurde auf Standardwerte zurückgesetzt.', 'success')
    else:
        flash('Fehler beim Zurücksetzen der White-Label-Konfiguration.', 'danger')
    return redirect(url_for('routes.whitelabel'))

@bp.route("/")
@bp.route("/dashboard")
@login_required
def dashboard():
    # Check if barcode visibility is disabled
    settings = load_settings()
    barcode_visibility_enabled = settings.get('barcode_visibility_enabled', True)

    # Hole die aktuellsten Scan-Daten
    # Only include barcode scans if the feature is enabled
    if barcode_visibility_enabled:
        current_scans = get_current_scans()
    else:
        current_scans = []

    # Hole NFC-Kartendaten, wenn vorhanden
    try:
        from app.nfc_reader import get_registered_cards, get_current_card_scans
        registered_cards = get_registered_cards()
        card_scans = get_current_card_scans()

        # Convert NFC scans to display format - SHOW SCANS FROM LAST 30 DAYS
        nfc_scans_formatted = []

        # Filter to show scans from the last 30 days (consistent with cleanup policy)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        seen_scans = set()  # Track unique scans by pan_hash+timestamp to avoid exact duplicates

        # Sort scans by timestamp (newest first) and process
        sorted_scans = sorted(card_scans, key=lambda x: x.get('timestamp', ''), reverse=True)

        for scan in sorted_scans:
            # Parse timestamp and check if it's within last 30 days
            try:
                scan_time = datetime.strptime(scan.get('timestamp', ''), '%Y-%m-%d %H:%M:%S')
                if scan_time < thirty_days_ago:
                    continue  # Skip scans older than 30 days
            except:
                continue  # Skip if timestamp can't be parsed

            # PCI DSS COMPLIANT: Use pan_hash for deduplication, pan_last4 for display
            pan_hash = scan.get('pan_hash')
            pan_last4 = scan.get('pan_last4')
            timestamp = scan.get('timestamp', '')

            # Legacy support: if no hash exists, it's old plaintext data
            if not pan_hash and 'pan' in scan:
                pan = scan.get('pan', '')
                if pan and not is_hashed_pan(pan):
                    # Convert legacy plaintext to hash+last4
                    pan_hash = hash_pan(pan)
                    pan_last4 = pan[-4:] if len(pan) >= 4 else pan

            # FIXED: Deduplicate by pan_hash+timestamp instead of just pan_hash
            # This allows showing multiple scans of the same card at different times
            scan_key = f"{pan_hash}:{timestamp}"
            if scan_key in seen_scans:
                continue  # Skip exact duplicate (same card, same time)
            if pan_hash and timestamp:
                seen_scans.add(scan_key)

            # Format PAN for display (PCI DSS compliant - masked)
            if pan_last4:
                display_pan = f"****-{pan_last4}"
            else:
                display_pan = "****-****"

            # Get card type from scan data (use actual detected type)
            card_type = scan.get('card_type', 'Bankkarte')

            # Format the scan for display
            formatted_scan = {
                'timestamp': timestamp,  # FIXED: Use full timestamp for consistent sorting
                'display_time': scan.get('timestamp', '').split(' ')[1][:5] if ' ' in scan.get('timestamp', '') else scan.get('timestamp', '')[:5],  # HH:MM for display
                'code': f"NFC-{display_pan}",
                'pan': display_pan,  # PCI DSS COMPLIANT: Masked PAN for template fallback
                'status': scan.get('status', 'NFC-Karte'),
                'scan_type': 'nfc',
                'pan_last4': pan_last4,  # PCI DSS COMPLIANT: Only last 4 digits
                'pan_hash': pan_hash,  # FIXED: Include pan_hash for unique scanId in template
                'card_type': card_type  # Include actual card type
            }

            nfc_scans_formatted.append(formatted_scan)

        # Keep NFC and barcode scans separate to avoid duplication
        # NFC scans will be shown in their own section in dashboard
        all_scans = current_scans  # Only barcode scans for historical section

    except ImportError:
        registered_cards = []
        card_scans = []
        nfc_scans_formatted = []
        all_scans = current_scans

    # Sortiere nach Zeitstempel absteigend (only barcode scans)
    all_scans = sorted(all_scans, key=lambda x: x['timestamp'], reverse=True)

    # Berechne Statistiken für heute
    today = datetime.now().date()
    today_scans = sum(1 for scan in current_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() == today)
    try:
        today_card_scans = sum(1 for scan in card_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() == today)
    except:
        today_card_scans = 0

    # Berechne Statistiken für die letzten 30 Tage
    thirty_days_ago = today - timedelta(days=30)
    scans_30_days = sum(1 for scan in current_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() >= thirty_days_ago)
    
    # Filter-Parameter
    page = request.args.get('page', 1, type=int)
    nfc_page = request.args.get('nfc_page', 1, type=int)  # Separate pagination for NFC scans
    current_date = request.args.get('date', '')
    current_time_from = request.args.get('time_from', '')
    current_time_to = request.args.get('time_to', '')
    current_validity = request.args.get('validity', '')
    
    # Filtern der Scans
    filtered_scans = all_scans.copy()
    
    if current_date:
        filtered_date = datetime.strptime(current_date, '%Y-%m-%d').date()
        filtered_scans = [scan for scan in filtered_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() == filtered_date]
    
    if current_time_from:
        from_time = datetime.strptime(current_time_from, '%H:%M').time()
        filtered_scans = [scan for scan in filtered_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').time() >= from_time]
    
    if current_time_to:
        to_time = datetime.strptime(current_time_to, '%H:%M').time()
        filtered_scans = [scan for scan in filtered_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').time() <= to_time]
    
    if current_validity:
        if current_validity == 'valid':
            filtered_scans = [scan for scan in filtered_scans if scan['status'] in ['Permanent', 'Temporär', 'NFC-Karte', 'Gültig']]
        elif current_validity == 'invalid':
            filtered_scans = [scan for scan in filtered_scans if scan['status'] in ['Ungültig', 'Gesperrt']]
    
    # Paginierung
    scans_per_page = 15
    total_scans = len(filtered_scans)
    total_pages = (total_scans + scans_per_page - 1) // scans_per_page
    
    # Stellt sicher, dass die angeforderte Seite gültig ist
    if page < 1:
        page = 1
    elif page > total_pages and total_pages > 0:
        page = total_pages
    
    # Berechne Start- und End-Index für aktuelle Seite
    start_idx = (page - 1) * scans_per_page
    end_idx = min(start_idx + scans_per_page, total_scans)
    
    # Erstelle Seitenbereich für Paginierung
    if total_pages <= 5:
        page_range = range(1, total_pages + 1)
    else:
        if page <= 3:
            page_range = range(1, 6)
        elif page >= total_pages - 2:
            page_range = range(total_pages - 4, total_pages + 1)
        else:
            page_range = range(page - 2, page + 3)
    
    # Hole Barcodes für Statistik
    active_barcodes = len(load_temporary_codes())
    permanent_codes = len(load_permanent_codes())
    
    # Berechne NFC-Statistiken für die letzten 30 Tage
    try:
        card_scans_30_days = sum(1 for scan in card_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() >= thirty_days_ago)
    except:
        card_scans_30_days = 0

    # NFC Scans Pagination (7 entries per page as requested: 5-7 range)
    nfc_scans_per_page = 7
    total_nfc_scans = len(nfc_scans_formatted)
    nfc_total_pages = (total_nfc_scans + nfc_scans_per_page - 1) // nfc_scans_per_page if total_nfc_scans > 0 else 1

    # Validate nfc_page
    if nfc_page < 1:
        nfc_page = 1
    elif nfc_page > nfc_total_pages and nfc_total_pages > 0:
        nfc_page = nfc_total_pages

    # Calculate NFC pagination range
    nfc_start_idx = (nfc_page - 1) * nfc_scans_per_page
    nfc_end_idx = min(nfc_start_idx + nfc_scans_per_page, total_nfc_scans)

    # Create NFC page range for pagination display
    if nfc_total_pages <= 5:
        nfc_page_range = range(1, nfc_total_pages + 1)
    else:
        if nfc_page <= 3:
            nfc_page_range = range(1, 6)
        elif nfc_page >= nfc_total_pages - 2:
            nfc_page_range = range(nfc_total_pages - 4, nfc_total_pages + 1)
        else:
            nfc_page_range = range(nfc_page - 2, nfc_page + 3)

    return render_template(
        'dashboard.html',
        scans=filtered_scans[start_idx:end_idx],
        today_scans=today_scans,
        today_card_scans=today_card_scans,
        card_scans_30_days=card_scans_30_days,
        active_barcodes=active_barcodes,
        permanent_codes=permanent_codes,
        scans_30_days=scans_30_days,
        page=page,
        total_pages=total_pages,
        total_scans=total_scans,
        page_range=page_range,
        current_date=current_date,
        current_time_from=current_time_from,
        current_time_to=current_time_to,
        current_validity=current_validity,
        barcode_visibility_enabled=barcode_visibility_enabled,
        nfc_scans=nfc_scans_formatted[nfc_start_idx:nfc_end_idx],  # Paginated NFC scans (7 per page)
        nfc_page=nfc_page,
        nfc_total_pages=nfc_total_pages,
        total_nfc_scans=total_nfc_scans,
        nfc_page_range=nfc_page_range
    )

@bp.route("/barcodes")
@login_required
def barcodes():
    # Check if barcode features are disabled system-wide
    settings = load_settings()
    if not settings.get('barcode_visibility_enabled', True):
        flash('Barcode-Funktionen sind in diesem System deaktiviert.', 'warning')
        return redirect(url_for('routes.dashboard'))

    # Lade alle Barcodes für Frontend-Suche und -Paginierung
    # (Frontend-JavaScript übernimmt Paginierung und Suche)
    permanent_codes = load_permanent_codes()
    temporary_codes = load_temporary_codes()

    # Alle Codes an Frontend übertragen für vollständige Suche
    return render_template(
        "barcodes.html",
        permanent_codes=permanent_codes,  # Alle permanenten Codes
        temporary_codes=temporary_codes,  # Alle temporären Codes
        total_permanent=len(permanent_codes),
        total_temporary=len(temporary_codes)
    )

@bp.route("/add_barcode", methods=["POST"])
@login_required
def add_barcode():
    # Check if barcode features are disabled system-wide
    settings = load_settings()
    if not settings.get('barcode_visibility_enabled', True):
        return jsonify({"success": False, "message": "Barcode-Funktionen sind deaktiviert"})

    barcode = request.form.get('barcode')
    code_type = request.form.get('type')
    
    if not barcode:
        flash("Barcode darf nicht leer sein!")
        return redirect(url_for('routes.barcodes'))
    
    success = False
    if code_type == 'permanent':
        codes = load_permanent_codes()
        if barcode not in codes:
            codes.append(barcode)
            save_permanent_codes(codes)
            success = True
            flash("Permanenter Barcode hinzugefügt!")
    else:
        codes = load_temporary_codes()
        if barcode not in codes:
            codes.append(barcode)
            save_temporary_codes(codes)
            success = True
            flash("Temporärer Barcode hinzugefügt!")
    
    # Service-Neustart entfernt - nicht nötig im vereinfachten System
    
    return redirect(url_for('routes.barcodes'))

@bp.route("/delete_barcode", methods=["POST"])
@login_required
def delete_barcode():
    # Check if barcode features are disabled system-wide
    settings = load_settings()
    if not settings.get('barcode_visibility_enabled', True):
        flash('Barcode-Funktionen sind deaktiviert', 'warning')
        return redirect(url_for('routes.dashboard'))

    barcode = request.form.get('barcode')
    code_type = request.form.get('type')
    
    success = False
    if code_type == 'permanent':
        codes = load_permanent_codes()
        if barcode in codes:
            codes.remove(barcode)
            save_permanent_codes(codes)
            success = True
            flash("Permanenter Barcode gelöscht!")
    else:
        codes = load_temporary_codes()
        if barcode in codes:
            codes.remove(barcode)
            save_temporary_codes(codes)
            success = True
            flash("Temporärer Barcode gelöscht!")
    
    # Service-Neustart entfernt - nicht nötig im vereinfachten System
    
    return redirect(url_for('routes.barcodes'))

@bp.route("/settings")
@login_required
def settings():
    # Only allow admin users or special users to access settings
    if session.get('role') != 'admin' and session.get('username') not in ['sentrasupport', 'kassen24']:
        flash("Zugriff verweigert. Nur Administratoren können auf die Einstellungen zugreifen.", "danger")
        return redirect(url_for('routes.dashboard'))

    settings = load_settings()

    # Get current timezone from settings or default to Europe/Berlin
    current_timezone = settings.get('timezone', 'Europe/Berlin')

    # Get current time in the configured timezone
    from datetime import datetime
    import pytz
    try:
        tz = pytz.timezone(current_timezone)
        current_time = datetime.now(tz).strftime('%d.%m.%Y %H:%M:%S %Z')
    except:
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M:%S')

    return render_template(
        "settings.html",
        username=settings['username'],
        door_open_time=settings.get('door_open_time', 1.5),
        allow_all_barcodes=settings.get('allow_all_barcodes', False),
        nfc_webhook_url=settings.get('nfc_webhook_url', ''),
        barcode_webhook_url=settings.get('barcode_webhook_url', ''),
        webhook_enabled=settings.get('webhook_enabled', True),
        webhook_timeout=settings.get('webhook_timeout', 5),
        webhook_auth_user=settings.get('webhook_auth_user', ''),
        webhook_auth_password=settings.get('webhook_auth_password', ''),
        webhook_auth_type=settings.get('webhook_auth_type', 'digest'),
        nfc_webhook_delay=settings.get('nfc_webhook_delay', 0.0),
        barcode_webhook_delay=settings.get('barcode_webhook_delay', 0.0),
        barcode_visibility_enabled=settings.get('barcode_visibility_enabled', True),
        current_timezone=current_timezone,
        current_time=current_time
    )

@bp.route("/update_timezone", methods=["POST"])
@login_required
def update_timezone():
    """Update system timezone configuration."""
    settings = load_settings()

    # Get new timezone from form
    new_timezone = request.form.get('timezone', 'Europe/Berlin')

    # Validate timezone
    import pytz
    valid_timezones = [
        'Europe/Berlin', 'Europe/London', 'Europe/Paris',
        'Europe/Amsterdam', 'Europe/Vienna', 'Europe/Zurich', 'UTC'
    ]

    if new_timezone not in valid_timezones:
        flash("Ungültige Zeitzone ausgewählt!", "error")
        return redirect(url_for('routes.settings') + '#network-tab')

    # Update timezone in settings
    settings['timezone'] = new_timezone
    save_settings(settings)

    # Try to update system timezone (requires root on Linux)
    try:
        import subprocess
        # This command works on Raspberry Pi OS (Debian-based)
        subprocess.run(['sudo', 'timedatectl', 'set-timezone', new_timezone],
                      check=False, timeout=5)
        flash(f"Zeitzone erfolgreich auf {new_timezone} geändert!", "success")
    except Exception as e:
        flash(f"Zeitzone in Einstellungen gespeichert. System-Zeitzone konnte nicht geändert werden: {str(e)}", "warning")

    return redirect(url_for('routes.settings') + '#network-tab')

@bp.route("/update_settings", methods=["POST"])
@login_required
def update_settings():
    # Load current settings
    settings = load_settings()

    # Check if this is an AJAX auto-save request (single field update)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Audio-Einstellungen entfernt - werden jetzt über Webhooks gesteuert

    # Update user settings
    if 'username' in request.form:
        settings['username'] = request.form.get('username', settings['username'])
    new_password = request.form.get('password')
    if new_password:  # Nur aktualisieren, wenn ein neues Passwort eingegeben wurde
        settings['password'] = new_password

    # Update door time settings
    door_open_time = request.form.get('door_open_time')
    if door_open_time:
        settings['door_open_time'] = float(door_open_time)

    # Update barcode settings - Handle checkboxes properly for auto-save
    if 'allow_all_barcodes' in request.form or (not is_ajax and request.form.get('active_tab') == 'door-settings'):
        settings['allow_all_barcodes'] = request.form.get('allow_all_barcodes') == 'on'

    # NFC allow_all_nfc_cards feature has been removed for security reasons

    # Update Webhook settings - Only update if present in form (important for auto-save)
    if 'nfc_webhook_url' in request.form:
        settings['nfc_webhook_url'] = request.form.get('nfc_webhook_url', '').strip()
    if 'barcode_webhook_url' in request.form:
        settings['barcode_webhook_url'] = request.form.get('barcode_webhook_url', '').strip()

    # Handle webhook_enabled checkbox properly for auto-save
    if 'webhook_enabled' in request.form or (not is_ajax and request.form.get('active_tab') == 'integrations-settings'):
        settings['webhook_enabled'] = request.form.get('webhook_enabled') == 'on'

    if 'webhook_auth_user' in request.form:
        settings['webhook_auth_user'] = request.form.get('webhook_auth_user', '').strip()
    if 'webhook_auth_password' in request.form:
        settings['webhook_auth_password'] = request.form.get('webhook_auth_password', '').strip()
    if 'webhook_auth_type' in request.form:
        settings['webhook_auth_type'] = request.form.get('webhook_auth_type', 'digest')

    webhook_timeout = request.form.get('webhook_timeout')
    if webhook_timeout:
        try:
            settings['webhook_timeout'] = max(1, min(30, int(webhook_timeout)))  # 1-30 Sekunden
        except ValueError:
            settings['webhook_timeout'] = 5  # Fallback

    # Update Webhook Delays
    nfc_webhook_delay = request.form.get('nfc_webhook_delay')
    if nfc_webhook_delay:
        try:
            settings['nfc_webhook_delay'] = max(0.0, min(30.0, float(nfc_webhook_delay)))  # 0-30 Sekunden
        except ValueError:
            settings['nfc_webhook_delay'] = 0.0  # Fallback

    barcode_webhook_delay = request.form.get('barcode_webhook_delay')
    if barcode_webhook_delay:
        try:
            settings['barcode_webhook_delay'] = max(0.0, min(30.0, float(barcode_webhook_delay)))  # 0-30 Sekunden
        except ValueError:
            settings['barcode_webhook_delay'] = 0.0  # Fallback

    # Update barcode visibility setting - ONLY sentrasupport can change this
    if session.get('username') == 'sentrasupport':
        if 'barcode_visibility_enabled' in request.form or (not is_ajax and request.form.get('active_tab') == 'door-settings'):
            settings['barcode_visibility_enabled'] = request.form.get('barcode_visibility_enabled') == 'on'

    # Log settings changes before saving
    username = session.get('username', 'unknown')
    active_tab = request.form.get('active_tab', 'general')
    changed_fields = []

    # Track which fields were changed by comparing form data
    for key, value in request.form.items():
        if key not in ['active_tab']:
            if key == 'password' and value:  # Don't log passwords
                changed_fields.append('password')
            elif key in ['allow_all_barcodes', 'webhook_enabled', 'barcode_visibility_enabled']:
                # Handle checkboxes
                old_value = settings.get(key, False)
                new_value = value == 'on'
                if old_value != new_value:
                    changed_fields.append(f"{key}: {old_value} → {new_value}")
            elif key in settings and str(settings.get(key, '')) != str(value):
                if key not in ['webhook_auth_password']:  # Don't log sensitive data
                    changed_fields.append(f"{key}: {settings.get(key)} → {value}")
                else:
                    changed_fields.append(key)

    # Enhanced settings change logging
    if changed_fields:
        try:
            log_system(f"System settings updated",
                      extra_context={
                          'changed_by': username,
                          'settings_tab': active_tab,
                          'changed_fields': changed_fields,
                          'change_time': datetime.now().isoformat(),
                          'is_ajax': request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                      })
        except:
            # Fallback to basic logging
            logging.info(f"Einstellungen geändert von {username}: {', '.join(changed_fields)}")

    # Save all settings
    save_settings(settings)

    # Check if this is an AJAX request
    if is_ajax:
        return jsonify({"success": True, "message": "Einstellungen gespeichert"})

    flash("Alle Einstellungen wurden erfolgreich gespeichert!")

    # Preserve the active tab
    active_tab = request.form.get('active_tab', 'door-settings')
    # Always include the tab hash in redirect URL
    return redirect(url_for('routes.settings') + f'#{active_tab}')

@bp.route("/test_webhook", methods=["POST"])
@login_required
def test_webhook():
    """Testet einen Webhook-Aufruf."""
    webhook_type = request.form.get('webhook_type')
    settings = load_settings()
    
    if not settings.get('webhook_enabled', False):
        return jsonify({'success': False, 'message': 'Webhooks sind deaktiviert'})
    
    if webhook_type == 'nfc':
        webhook_url = settings.get('nfc_webhook_url', '').strip()
        test_data = {'type': 'nfc', 'card_id': '****1234', 'test': True}
    elif webhook_type == 'barcode':
        webhook_url = settings.get('barcode_webhook_url', '').strip()
        test_data = {'type': 'barcode', 'code': 'TEST123456', 'test': True}
    else:
        return jsonify({'success': False, 'message': 'Unbekannter Webhook-Typ'})
    
    if not webhook_url:
        return jsonify({'success': False, 'message': f'{webhook_type.upper()}-Webhook-URL ist nicht konfiguriert'})
    
    try:
        import requests
        timeout = settings.get('webhook_timeout', 5)
        
        # GET-Request für Axis-Lautsprecher Kompatibilität
        response = requests.get(webhook_url, params=test_data, timeout=timeout)
        
        if response.status_code == 200:
            return jsonify({
                'success': True, 
                'message': f'{webhook_type.upper()}-Webhook erfolgreich getestet!',
                'status_code': response.status_code,
                'response_time': f"{response.elapsed.total_seconds():.2f}s"
            })
        else:
            return jsonify({
                'success': False, 
                'message': f'Webhook-Test fehlgeschlagen: HTTP {response.status_code}',
                'status_code': response.status_code
            })
    
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': f'Webhook-Test Timeout nach {timeout}s'})
    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'message': f'Webhook-Test Fehler: {str(e)}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Unerwarteter Fehler: {str(e)}'})

@bp.route("/open_door_route", methods=["POST"])
@login_required
def open_door_route():
    open_door()
    flash("✅ Tür wurde geöffnet.")
    # Preserve the settings tab if we're coming from settings page
    referrer = request.referrer or url_for("routes.dashboard")
    if '/settings' in referrer and '#' not in referrer:
        referrer = referrer + '#manual-controls'
    return redirect(referrer)

@bp.route("/close_door_route", methods=["POST"])
@login_required
def close_door_route():
    close_door()
    flash("✅ Tür wurde geschlossen.")
    # Preserve the settings tab if we're coming from settings page
    referrer = request.referrer or url_for("routes.dashboard")
    if '/settings' in referrer and '#' not in referrer:
        referrer = referrer + '#manual-controls'
    return redirect(referrer)

@bp.route("/gpio_status")
@login_required
def gpio_status():
    gpio_data = get_gpio_state()
    # Extrahiere nur den State-Wert für einfache Verarbeitung
    state_value = gpio_data.get("state", 0) if isinstance(gpio_data, dict) else 0
    return jsonify({ 
        "gpio_state": state_value,
        "full_status": gpio_data  # Für Debugging falls benötigt
    })

@bp.route("/status")
@login_required
def status():
    # Hole die aktuellsten Scan-Daten
    current_scans = get_current_scans()
    
    return jsonify({
        "status": "running",
        "scans_logged": len(current_scans),
        "last_scan": current_scans[-1] if current_scans else None
    })

@bp.route("/get_latest_scans")
@login_required
def get_latest_scans():
    # Stelle sicher, dass wir die aktuellsten Scan-Daten haben
    current_scans = get_current_scans()
    
    # Sortiere nach Zeitstempel absteigend
    current_scans = sorted(current_scans, key=lambda x: x['timestamp'], reverse=True)
    
    # Berechne Statistiken für heute
    today = datetime.now().date()
    today_scans = sum(1 for scan in current_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() == today)
    
    # Berechne Statistiken für die letzten 30 Tage
    thirty_days_ago = today - timedelta(days=30)
    scans_30_days = sum(1 for scan in current_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() >= thirty_days_ago)
    
    # Hole NFC-Kartendaten, wenn vorhanden
    try:
        from app.nfc_reader import get_registered_cards, get_current_card_scans
        registered_cards = get_registered_cards()
        all_card_scans = get_current_card_scans()
        
        # Sortiere nach Zeitstempel absteigend
        all_card_scans = sorted(all_card_scans, key=lambda x: x['timestamp'], reverse=True)
        
        # Begrenze auf 10 NFC-Kartenscans
        card_scans = all_card_scans[:10]
        
        today_card_scans = sum(1 for scan in all_card_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() == today)
    except ImportError:
        registered_cards = []
        card_scans = []
        today_card_scans = 0
    
    # Nur die neuesten Scans senden (maximal 20)
    return jsonify({
        'scans': current_scans[:20],
        'today_scans': today_scans,
        'active_barcodes': len(load_temporary_codes()),
        'permanent_codes': len(load_permanent_codes()),
        'scans_30_days': scans_30_days,
        'card_scans': card_scans
    })

@bp.route("/update_door_time", methods=["POST"])
@admin_required
def update_door_time():
    data = request.get_json()
    door_open_time = float(data.get('door_open_time', 1.5))
    
    settings = load_settings()
    settings['door_open_time'] = door_open_time
    save_settings(settings)
    
    return jsonify({"success": True})

@bp.route("/save_barcode_changes", methods=["POST"])
@login_required
def save_barcode_changes():
    # Check if barcode features are disabled system-wide
    settings = load_settings()
    if not settings.get('barcode_visibility_enabled', True):
        return jsonify({"success": False, "message": "Barcode-Funktionen sind deaktiviert"})

    data = request.get_json()
    
    try:
        # Lade bestehende Codes
        permanent_codes = load_permanent_codes()
        temporary_codes = load_temporary_codes()
        
        # Hinzufügen neuer permanenter Codes
        for code in data.get('addedPermanent', []):
            if code not in permanent_codes:
                permanent_codes.append(code)
        
        # Entfernen gelöschter permanenter Codes
        for code in data.get('removedPermanent', []):
            if code in permanent_codes:
                permanent_codes.remove(code)
        
        # Hinzufügen neuer temporärer Codes
        for code in data.get('addedTemporary', []):
            if code not in temporary_codes:
                temporary_codes.append(code)
        
        # Entfernen gelöschter temporärer Codes
        for code in data.get('removedTemporary', []):
            if code in temporary_codes:
                temporary_codes.remove(code)
        
        # Speichern der aktualisierten Listen
        save_permanent_codes(permanent_codes)
        save_temporary_codes(temporary_codes)
        
        # Service-Restart entfernt - führt zu Deadlocks
        # Die Codes werden dynamisch geladen, daher ist kein Restart nötig
        
        return jsonify({
            "success": True,
            "service_restarted": True,  # Immer True, da kein Restart mehr benötigt
            "permanent_count": len(permanent_codes),
            "temporary_count": len(temporary_codes)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/toggle_sidebar", methods=["POST"])
@login_required
def toggle_sidebar():
    data = request.get_json()
    if data and 'collapsed' in data:
        session['sidebar_collapsed'] = data['collapsed']
    return jsonify({"success": True})

@bp.route("/logs")
@login_required
def logs():
    page = request.args.get('page', 1, type=int)
    level = request.args.get('level', 'all')
    date = request.args.get('date', '')

    # Ensure page is at least 1
    if page < 1:
        page = 1

    # Nutze kundenfreundliche Filterung für Nicht-Admin-Benutzer
    customer_friendly = session.get('role') != 'admin'
    log_entries, total_entries, total_pages = get_log_entries(level=level, date=date, page=page, customer_friendly=customer_friendly)

    # Ensure page doesn't exceed total_pages
    if total_pages > 0 and page > total_pages:
        page = total_pages
        log_entries, total_entries, total_pages = get_log_entries(level=level, date=date, page=page, customer_friendly=customer_friendly)

    return render_template("logs.html", logs=log_entries, page=page, total_pages=total_pages, total_entries=total_entries,
                          current_level=level, current_date=date)

@bp.route("/get_logs")
@login_required
def get_logs():
    level = request.args.get('level', 'all')
    date = request.args.get('date', '')
    page = request.args.get('page', 1, type=int)
    # Nutze kundenfreundliche Filterung für Nicht-Admin-Benutzer
    customer_friendly = session.get('role') != 'admin'

    log_entries, total_entries, total_pages = get_log_entries(level, date, page, customer_friendly=customer_friendly)

    return jsonify({
        "logs": log_entries,
        "page": page,
        "total_pages": total_pages,
        "total_entries": total_entries
    })

@bp.route("/clear_logs", methods=["POST"])
@admin_required
def clear_logs():
    try:
        # Clear system.log (main log file)
        system_log = os.path.join(os.path.dirname(__file__), '..', 'logs', 'system.log')
        if os.path.exists(system_log):
            with open(system_log, 'w') as f:
                f.write('')

        # Also clear app.log for completeness
        app_log = os.path.join(os.path.dirname(__file__), '..', 'logs', 'app.log')
        if os.path.exists(app_log):
            with open(app_log, 'w') as f:
                f.write('[]')  # Empty JSON array for app.log

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

def get_log_entries(level='all', date='', page=1, per_page=10, customer_friendly=False):
    """
    Get log entries from the unified logger with improved filtering and context.
    """
    try:
        # Try to use the unified logger first
        from app.unified_logger import unified_logger

        # Get logs from unified logger
        limit = per_page * page  # Get more for pagination
        level_filter = None if level == 'all' else level.upper()

        all_logs = unified_logger.get_logs(limit=1000, level=level_filter)

        # Filter by date if specified
        if date:
            filtered_logs = []
            for log in all_logs:
                log_date = log.get('timestamp', '').split('T')[0]
                if log_date == date:
                    filtered_logs.append(log)
            all_logs = filtered_logs

        # Apply customer-friendly filtering if needed
        if customer_friendly or session.get('role') != 'admin':
            # Security-relevant events to always show
            SECURITY_KEYWORDS = [
                'tür', 'door', 'zugang', 'access', 'nfc', 'barcode', 'qr',
                'login', 'auth', 'benutzer', 'user', 'öffnungszeiten'
            ]

            # Technical messages to filter out
            TECHNICAL_KEYWORDS = [
                'debug', 'gpio-pin', 'werkzeug', 'traceback', 'exception',
                'stack trace', 'file "', 'line ', 'smartcard', 'pcscd'
            ]

            filtered_logs = []
            for log in all_logs:
                message_lower = log.get('message', '').lower()

                # Skip technical messages
                if any(tech in message_lower for tech in TECHNICAL_KEYWORDS):
                    continue

                # Include security-relevant messages or ERROR/CRITICAL
                if (any(sec in message_lower for sec in SECURITY_KEYWORDS) or
                    log.get('level') in ['ERROR', 'CRITICAL']):
                    filtered_logs.append(log)

            all_logs = filtered_logs

        # Calculate pagination
        total_entries = len(all_logs)
        total_pages = max(1, (total_entries + per_page - 1) // per_page)

        # Get page slice
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_logs = all_logs[start_idx:end_idx]

        # Format logs for display
        formatted_logs = []
        for log in page_logs:
            formatted_logs.append({
                'timestamp': log.get('timestamp', ''),
                'level': log.get('level', 'INFO'),
                'message': log.get('message', ''),
                'context': log.get('context', {})
            })

        return formatted_logs, total_entries, total_pages

    except ImportError:
        # Fallback to legacy method if unified logger not available
        return get_log_entries_legacy(level, date, page, per_page, customer_friendly)
    except Exception as e:
        logger.error(f"Error getting log entries: {e}")
        return [], 0, 0

def get_log_entries_legacy(level='all', date='', page=1, per_page=10, customer_friendly=False):
    """
    Holt erweiterte Log-Einträge mit detaillierten Troubleshooting-Informationen.

    Args:
        customer_friendly: Wenn True, zeigt nur kundenrelevante Events
    """
    # Security-relevant events - what should ALWAYS be shown
    SECURITY_EVENTS = [
        "tür wurde geöffnet",
        "tür geöffnet",
        "tür geschlossen",
        "zugang verweigert",
        "nfc-karte erfolgreich erkannt",
        "karte wurde gescannt",
        "barcode erkannt",
        "qr-code gescannt",
        "zugriff gewährt",
        "zugriff verweigert",
        "ungültiger code",
        "login erfolgreich",
        "login fehlgeschlagen",
        "benutzer angelegt",
        "benutzer gelöscht",
        "barcode hinzugefügt",
        "barcode gelöscht",
        "öffnungszeiten angepasst",
        "system neustart",
        "fehler beim zugriff"
    ]

    # Technical messages to ALWAYS filter out (unless admin)
    TECHNICAL_FILTERS = [
        "werkzeug",
        "debug-modus",
        "gpio-pin",
        "nfc-kartendaten geladen",
        "keine gespeicherten nfc-kartendaten",
        "konfiguration geladen",
        "scan gespeichert",
        "starting",
        "stopping",
        "initialisiert",
        "white-label",
        "opening hours configuration",
        "failed nfc scans datenbank",
        "default-admin",
        "keine login-historie",
        "traceback",
        "exception",
        "stack trace",
        "error reading",
        "failed to",
        "connection lost",
        "attempting to reconnect",
        "mockled",
        "lgpio",
        "gpiozero",
        "smartcard",
        "pcscd",
        "file \"",
        "line [0-9]+"
    ]

    log_entries = []
    # Use system.log which contains actual log data instead of app.log
    log_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'system.log')

    # Fallback to app.log if system.log doesn't exist
    if not os.path.exists(log_file):
        log_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'app.log')
        if not os.path.exists(log_file):
            return log_entries, 0, 0

    # Enhanced pattern to capture milliseconds
    log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\w+) - (.+)'
    
    try:
        with open(log_file, 'r') as f:
            for line in f:
                match = re.match(log_pattern, line.strip())
                if match:
                    timestamp, line_level, message = match.groups()
                    
                    # Filtern nach Level
                    if level != 'all' and level.upper() != line_level.upper():
                        continue
                    
                    # Filtern nach Datum
                    if date:
                        log_date = timestamp.split(' ')[0]
                        if log_date != date:
                            continue
                    
                    # Enhanced filtering for relevant security events
                    message_lower = message.lower()

                    # For non-admin users, apply strict filtering
                    if customer_friendly or session.get('role') != 'admin':
                        # Check if it's a security-relevant event
                        is_security_event = any(event in message_lower for event in SECURITY_EVENTS)

                        # Skip technical messages regardless of level
                        is_technical = any(tech_term in message_lower for tech_term in TECHNICAL_FILTERS)

                        # Filter logic:
                        # 1. Always skip technical messages
                        if is_technical and not is_security_event:
                            continue

                        # 2. Skip DEBUG and low-priority WARNING messages
                        if line_level.upper() == 'DEBUG':
                            continue

                        # 3. For INFO and WARNING, only show if it's a security event
                        if line_level.upper() in ['INFO', 'WARNING'] and not is_security_event:
                            continue

                        # 4. Always show ERROR and CRITICAL messages (after simplification)

                    # Vereinfache die Nachricht für bessere Lesbarkeit
                    simplified_message = simplify_log_message(message)

                    # Skip entries with no meaningful message content
                    if simplified_message is None:
                        continue

                    # Bessere Level-Zuordnung
                    improved_level = improve_log_level(line_level, message)

                    # Add enhanced troubleshooting data for protocol logs
                    enhanced_entry = {
                        "timestamp": timestamp,
                        "level": improved_level,
                        "message": simplified_message,
                        "original_message": message,
                        "milliseconds": timestamp.split(',')[1] if ',' in timestamp else "000"
                    }

                    # Parse and add specific error codes and hardware status where applicable
                    if "ERROR" in line_level.upper() or "CRITICAL" in line_level.upper():
                        # Extract error codes if present
                        error_code_match = re.search(r'ERROR[_\s]?([\d]+)', message)
                        if error_code_match:
                            enhanced_entry["error_code"] = error_code_match.group(1)

                        # Add hardware status indicators
                        if "NFC" in message.upper() or "reader" in message.lower():
                            enhanced_entry["hardware"] = "NFC Reader"
                            enhanced_entry["hardware_status"] = "Error"
                        elif "GPIO" in message.upper() or "door" in message.lower():
                            enhanced_entry["hardware"] = "GPIO/Door Control"
                            enhanced_entry["hardware_status"] = "Error"
                        elif "scanner" in message.lower() or "barcode" in message.lower():
                            enhanced_entry["hardware"] = "Barcode Scanner"
                            enhanced_entry["hardware_status"] = "Error"

                    # Add user action context
                    if "user" in message.lower() or "login" in message.lower():
                        enhanced_entry["action_type"] = "User Action"
                    elif "scan" in message.lower() or "card" in message.lower():
                        enhanced_entry["action_type"] = "Scan Action"
                    elif "webhook" in message.lower():
                        enhanced_entry["action_type"] = "Webhook Action"

                    log_entries.append(enhanced_entry)
                else:
                    # Handle Fortsetzungszeilen (z.B. Stacktraces)
                    if log_entries:
                        log_entries[-1]["message"] += "\n" + line.strip()
    except Exception as e:
        logging.error(f"Fehler beim Lesen der Logdatei: {e}")
    
    # Reverse order to show newest first
    log_entries = log_entries[::-1]
    
    # Paginierung
    total_entries = len(log_entries)
    total_pages = (total_entries + per_page - 1) // per_page
    
    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, total_entries)
    
    return log_entries[start_idx:end_idx], total_entries, total_pages

def simplify_log_message(message):
    """Vereinfacht Log-Nachrichten für bessere Lesbarkeit - entfernt technische Details."""
    # Entferne Pfade und replace mit ...
    message = re.sub(r'/[^/\s]+(/[^/\s]+)+', '...', message)

    # Kundenfreundliche Umformulierungen - more aggressive filtering
    customer_friendly = {
        r'Türöffnungsimpuls für \d+ Sekunden gesendet.*': 'Tür wurde geöffnet',
        r'Türöffnungsimpuls für (\d+) Sekunden gesendet.*': 'Tür wurde für \\1 Sekunden geöffnet',
        r'.*gpiozero.*lgpio.*': '',  # Entferne technische GPIO-Details
        r'.*GPIO.*': '',  # Filter out generic GPIO messages
        r'GPIO-Pin \d+ auf HIGH gesetzt.*': 'Tür geöffnet',
        r'GPIO-Pin \d+ auf LOW gesetzt.*': 'Tür geschlossen',
        r'.*MockLED.*': '',  # Entferne MockLED-Erwähnungen
        r'✅ NFC-Karte erfolgreich erkannt.*': 'NFC-Karte erfolgreich gescannt',
        r'NFC-Karte erkannt:.*': 'Karte wurde gescannt',
        r'🚫 NFC-Zugang verweigert.*': 'NFC-Zugang verweigert',
        r'🚫 Zugang verweigert.*': 'Zugang verweigert',
        r'Webhook.*erfolgreich.*': 'Webhook erfolgreich ausgelöst',
        r'Webhook.*fehlgeschlagen.*': 'Webhook-Fehler',
        r'pcsc.*': '',  # Remove pcsc references
        r'.*smartcard.*': '',  # Remove smartcard references
        r'.*HIGH.*LOW.*': '',  # Filter out generic HIGH/LOW messages
        r'.*Werkzeug.*': '',  # Remove Werkzeug messages
        r'.* \* Running on.*': '',  # Remove Flask startup messages
        r'.* \* Restarting with.*': '',  # Remove Flask restart messages
        r'.* \* Debugger.*': '',  # Remove debugger messages
        r'.*WARNING.*This is a development server.*': '',  # Remove dev server warnings
    }

    # Wende kundenfreundliche Übersetzungen an
    for pattern, replacement in customer_friendly.items():
        message = re.sub(pattern, replacement, message, flags=re.IGNORECASE)

    # Vereinfache häufige technische Muster - more aggressive
    simplifications = {
        r'Traceback \(most recent call last\):.*': '',  # Remove tracebacks entirely
        r'File ".*", line \d+, in .*': '',  # Remove file references
        r'smartcard\..*Exception': 'Kartenfehler',
        r'NoCardException': 'Keine Karte erkannt',
        r'CardConnectionException': 'Kartenverbindungsfehler',
        r'Debug-Modus aktiviert für.*': '',  # Filter out debug mode messages
        r'NFC-Kartendaten geladen: \d+ Scans': '',  # Filter out generic NFC data loaded messages
        r'Keine gespeicherten NFC-Kartendaten gefunden.*': '',  # Filter out generic NFC messages
        r'Konfiguration geladen.*': '',  # Filter out generic config loaded messages
        r'GPIO-Pulse.*': '',  # Filter out GPIO pulse messages
        r'Scan gespeichert.*': '',  # Filter out generic scan saved messages
        r'Restart triggered.*': 'System-Neustart',
        r'Starting.*': '',  # Filter out generic starting messages
        r'Stopping.*': '',  # Filter out generic stopping messages
        r'.*erfolgreich initialisiert': '',  # Filter out generic initialization messages
        r'.*erfolgreich geladen': '',  # Filter out generic loading messages
        r'.*erfolgreich gespeichert': '',  # Filter out generic saving messages
        r'White-label configuration.*': '',  # Filter out white-label config messages
        r'Opening hours configuration.*': '',  # Filter out opening hours config messages
        r'Failed NFC Scans Datenbank.*': '',  # Filter out database initialization messages
        r'Default-Admin.*': '',  # Filter out admin initialization messages
        r'Keine Login-Historie gefunden.*': '',  # Filter out login history messages
        r'.*Connection lost.*': '',  # Filter out connection messages
        r'.*Attempting to reconnect.*': '',  # Filter out reconnection messages
        r'.*Successfully reconnected.*': '',  # Filter out reconnection success
        r'^\s*-+\s*$': '',  # Remove separator lines
        r'^\s*$': '',  # Remove empty lines
        r'.*Server.*running.*': '',  # Remove server startup messages
        r'.*Listening on.*': '',  # Remove listening messages
        r'.*Press CTRL\+C.*': '',  # Remove instructions
    }
    
    for pattern, replacement in simplifications.items():
        message = re.sub(pattern, replacement, message, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove empty messages or messages with only whitespace/dots
    message = message.strip()
    if not message or message in ['...', '.', '-', '_']:
        return None  # Return None to signal this message should be filtered out

    # Kürze sehr lange Nachrichten
    if len(message) > 200:
        message = message[:197] + '...'

    return message

def improve_log_level(original_level, message):
    """Verbessert die Log-Level-Zuordnung basierend auf dem Nachrichteninhalt."""
    # Konvertiere zu Kleinbuchstaben für Vergleich
    message_lower = message.lower()
    
    # Kritische Ereignisse
    if any(keyword in message_lower for keyword in ['critical', 'fatal', 'panic', 'emergency']):
        return 'CRITICAL'
    
    # Fehler
    if any(keyword in message_lower for keyword in ['error', 'exception', 'traceback', 'failed', 'failure']):
        return 'ERROR'
    
    # Warnungen
    if any(keyword in message_lower for keyword in ['warn', 'warning', 'deprecated', 'timeout']):
        return 'WARNING'
    
    # Erfolgreiche Operationen sollten INFO sein
    if any(keyword in message_lower for keyword in ['success', 'completed', 'loaded', 'saved', 'connected']):
        return 'INFO'
    
    # Debug-Informationen
    if any(keyword in message_lower for keyword in ['debug', 'trace', 'verbose']):
        return 'DEBUG'
    
    # Fallback auf Original-Level
    return original_level

@bp.route("/get_stats")
@login_required
def get_stats():
    # Hole die aktuellsten Scan-Daten
    current_scans = get_current_scans()
    
    # Berechne Statistiken für heute
    today = datetime.now().date()
    today_scans = sum(1 for scan in current_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() == today)
    
    # Berechne Statistiken für die letzten 30 Tage
    thirty_days_ago = today - timedelta(days=30)
    scans_30_days = sum(1 for scan in current_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() >= thirty_days_ago)
    
    # Hole NFC-Kartendaten, wenn vorhanden
    try:
        from app.nfc_reader import get_registered_cards, get_current_card_scans
        registered_cards = get_registered_cards()
        card_scans = get_current_card_scans()
        today_card_scans = sum(1 for scan in card_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() == today)
    except ImportError:
        registered_cards = []
        today_card_scans = 0
    
    return jsonify({
        'today_scans': today_scans,
        'active_barcodes': len(load_temporary_codes()),
        'permanent_codes': len(load_permanent_codes()),
        'scans_30_days': scans_30_days
    })

@bp.route("/nfc_cards")
@login_required
def nfc_cards():
    """Zeigt die NFC-Kartenübersicht an."""
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Limit auf 10 Einträge pro Seite
    
    cards = get_registered_cards()
    all_card_scans = get_current_card_scans()
    
    # Sortiere nach Zeitstempel absteigend
    all_card_scans = sorted(all_card_scans, key=lambda x: x['timestamp'], reverse=True)
    
    # Berechne die Gesamtzahl der Seiten
    total_pages = (len(all_card_scans) + per_page - 1) // per_page
    
    # Begrenze die Seite auf gültige Werte
    page = max(1, min(page, total_pages if total_pages > 0 else 1))
    
    # Berechne den Start- und Endindex für die aktuelle Seite
    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, len(all_card_scans))
    
    # Hole nur die Einträge für die aktuelle Seite
    card_scans = all_card_scans[start_idx:end_idx]

    # PCI DSS COMPLIANT: Always mask PANs, no exceptions (even for admins)
    # Scans now use pan_hash and pan_last4, but support legacy plaintext PANs during migration
    for scan in card_scans:
        # New format: pan_hash + pan_last4 (PCI DSS compliant)
        # Legacy format: plaintext 'pan' field (will be migrated)
        if 'pan' in scan and scan['pan']:
            # Legacy plaintext PAN - convert to masked format for display
            if not is_hashed_pan(scan['pan']):
                # It's a plaintext PAN - mask it for display
                pan_str = str(scan['pan'])
                if len(pan_str) > 4:
                    scan['pan_last4'] = pan_str[-4:]
                # Remove plaintext PAN from display data (security)
                del scan['pan']
    
    # Vereinfachter Übergang zum neuen System
    try:
        # Statistiken für neues Dashboard berechnen
        successful_scans = len([s for s in all_card_scans if s.get('success', True)])
        failed_scans = len(all_card_scans) - successful_scans
        registered_cards = len(cards)
        
        # Hole Error-Logs für Analyse
        recent_errors = []
        top_errors = []
        problematic_prefixes = []
        
        try:
            from app import error_logger
            error_logs = error_logger.get_fallback_logs(limit=50)
            
            # Verarbeite Error-Logs für bessere Analyse
            error_types = {}
            card_prefixes = {}
            
            for log in error_logs:
                # Analysiere Fehlertyp
                error_type = log.get('error_type', 'Unbekannter Fehler')
                error_types[error_type] = error_types.get(error_type, 0) + 1
                
                # Suche nach PAN-Daten in den Logs
                raw_data = log.get('raw_data', '')
                pan_patterns = [
                    r'PAN:\s*(\d{6})',
                    r'422056(\d{10})',
                    r'444952(\d{10})',
                    r'4(\d{5})'
                ]
                
                pan_prefix = 'Unbekannt'
                for pattern in pan_patterns:
                    match = re.search(pattern, raw_data)
                    if match:
                        if len(match.group(1)) >= 6:
                            pan_prefix = match.group(1)[:6]
                        else:
                            pan_prefix = '4' + match.group(1)[:5]
                        break
                
                if pan_prefix != 'Unbekannt':
                    card_prefixes[pan_prefix] = card_prefixes.get(pan_prefix, 0) + 1
                
                # Füge zu recent_errors hinzu
                recent_errors.append({
                    'id': log.get('id', ''),
                    'timestamp': log.get('timestamp', ''),
                    'pan_prefix': pan_prefix,
                    'error_type': error_type,
                    'error_details': raw_data[:150] if raw_data else 'Keine Details verfügbar'
                })
            
            # Top 5 Fehler und problematische Präfixe
            top_errors = [{'type': k, 'count': v} for k, v in 
                         sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]]
            problematic_prefixes = [{'prefix': k, 'count': v} for k, v in 
                                  sorted(card_prefixes.items(), key=lambda x: x[1], reverse=True)[:5]]
            
        except Exception as e:
            logger.debug(f"Fehler bei Error-Log-Analyse: {e}")
        
        # Nutze neues Template mit verbesserter Struktur
        return render_template("nfc_management.html",
                             recent_scans=card_scans,
                             registered_cards_list=cards,
                             successful_scans=successful_scans,
                             failed_scans=failed_scans,
                             registered_cards=registered_cards,
                             problematic_cards=len(recent_errors),
                             recent_errors=recent_errors[:10],
                             top_errors=top_errors,
                             problematic_prefixes=problematic_prefixes,
                             enhanced_count=0,
                             enhanced_cards=[])
    except Exception as e:
        # Fallback zu altem System
        return render_template("nfc_cards.html", 
                               cards=cards, 
                               card_scans=card_scans, 
                               page=page,
                               per_page=per_page,
                               total_pages=total_pages,
                               total_scans=len(all_card_scans))

@bp.route("/get_card_scans")
@login_required
def get_card_scans():
    """Gibt die aktuellen NFC-Kartenscans zurück."""
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Limit auf 10 Einträge pro Seite
    
    all_scans = get_current_card_scans()
    
    # Sortiere nach Zeitstempel absteigend
    all_scans = sorted(all_scans, key=lambda x: x['timestamp'], reverse=True)
    
    # Berechne die Gesamtzahl der Seiten
    total_pages = (len(all_scans) + per_page - 1) // per_page
    
    # Begrenze die Seite auf gültige Werte
    page = max(1, min(page, total_pages if total_pages > 0 else 1))
    
    # Berechne den Start- und Endindex für die aktuelle Seite
    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, len(all_scans))

    # Hole nur die Scans für die aktuelle Seite
    page_scans = all_scans[start_idx:end_idx]

    # PCI DSS COMPLIANT: Always mask PANs, no exceptions (even for admins)
    # Scans now use pan_hash and pan_last4, but support legacy plaintext PANs during migration
    for scan in page_scans:
        # New format: pan_hash + pan_last4 (PCI DSS compliant)
        # Legacy format: plaintext 'pan' field (will be migrated)
        if 'pan' in scan and scan['pan']:
            # Legacy plaintext PAN - convert to masked format for display
            if not is_hashed_pan(scan['pan']):
                # It's a plaintext PAN - mask it for display
                pan_str = str(scan['pan'])
                if len(pan_str) > 4:
                    scan['pan_last4'] = pan_str[-4:]
                # Remove plaintext PAN from display data (security)
                del scan['pan']

    return jsonify({
        "scans": page_scans,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_scans": len(all_scans)
    })

@bp.route("/add_card", methods=["POST"])
@admin_required
def add_card():
    """Fügt eine neue NFC-Karte hinzu."""
    data = request.json
    
    name = data.get('name')
    pan = data.get('pan')
    expiry_date = data.get('expiry_date')
    description = data.get('description', '')
    
    if not name or not pan or not expiry_date:
        return jsonify({
            "success": False,
            "error": "Alle erforderlichen Felder müssen ausgefüllt sein"
        })
    
    # Validiere das Ablaufdatum-Format (MM/JJ)
    if not re.match(r'^\d{2}/\d{2}$', expiry_date):
        return jsonify({
            "success": False,
            "error": "Das Ablaufdatum muss im Format MM/JJ angegeben werden"
        })
    
    try:
        success = register_card(pan, expiry_date, name, description)
        
        if success:
            return jsonify({
                "success": True
            })
        else:
            return jsonify({
                "success": False,
                "error": "Fehler beim Registrieren der Karte"
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/health")
def health_check():
    """Basic health check endpoint for systemd watchdog (no auth required)."""
    import sd_notify

    try:
        # Check critical components
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "checks": {}
        }

        # Check NFC reader
        try:
            from smartcard.System import readers
            reader_list = readers()
            health_status["checks"]["nfc_reader"] = len(reader_list) > 0
        except Exception:
            health_status["checks"]["nfc_reader"] = False
            health_status["status"] = "degraded"

        # Check GPIO
        try:
            gpio_state = get_gpio_state()
            health_status["checks"]["gpio"] = gpio_state is not None
        except Exception:
            health_status["checks"]["gpio"] = False
            health_status["status"] = "degraded"

        # Check pcscd service
        try:
            result = subprocess.run(['systemctl', 'is-active', 'pcscd'],
                                  capture_output=True, text=True, timeout=2)
            health_status["checks"]["pcscd"] = result.stdout.strip() == 'active'
        except Exception:
            health_status["checks"]["pcscd"] = False
            health_status["status"] = "degraded"

        # Notify systemd watchdog if available
        try:
            notifier = sd_notify.SystemdNotifier()
            notifier.notify("WATCHDOG=1")
        except Exception:
            pass  # sd_notify not available or not running under systemd

        if health_status["status"] == "healthy":
            return jsonify(health_status), 200
        else:
            return jsonify(health_status), 503

    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

@bp.route("/api/system/health")
@login_required  
def system_health():
    """API-Endpoint für System-Gesundheitsstatus - Vereinfacht."""
    try:
        # Einfache Gesundheitsprüfung ohne komplexes Monitoring
        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "scanner": True,
                "nfc_reader": True,
                "gpio": True
            }
        }
        return jsonify({
            "success": True,
            "health": health_data
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route("/api/websocket/stats")
@login_required
def websocket_stats():
    """API-Endpoint für WebSocket-Statistiken."""
    try:
        from app.websocket import get_websocket_stats
        stats = get_websocket_stats()
        return jsonify({
            "success": True,
            "stats": stats
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route("/api/dashboard_data")
@login_required
def dashboard_data():
    """API-Endpoint für Dashboard-Daten - Vereinfacht ohne WebSocket."""
    try:
        import psutil
        import time
        from datetime import datetime, timedelta
        
        # System-Status sammeln
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        
        # Uptime formatieren
        uptime_days = int(uptime_seconds // 86400)
        uptime_hours = int((uptime_seconds % 86400) // 3600)
        uptime_minutes = int((uptime_seconds % 3600) // 60)
        
        if uptime_days > 0:
            uptime_str = f"{uptime_days}d {uptime_hours}h {uptime_minutes}m"
        elif uptime_hours > 0:
            uptime_str = f"{uptime_hours}h {uptime_minutes}m"
        else:
            uptime_str = f"{uptime_minutes}m"
        
        # NFC-Reader Status (vereinfacht)
        nfc_status = {
            "status": "Bereit",
            "description": "NFC-Reader bereit für Scans"
        }
        
        # Statistiken sammeln
        scans = get_current_scans()
        today = datetime.now().date()
        today_scans = len([scan for scan in scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() == today])
        
        # Echte NFC-Scans von NFC-Reader sammeln
        try:
            from app.nfc_reader import get_current_card_scans
            nfc_scans = get_current_card_scans()
            today_nfc_scans = len([scan for scan in nfc_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() == today])
        except ImportError:
            today_nfc_scans = 0
            nfc_scans = []
        
        # 30-Tage Statistiken
        thirty_days_ago = today - timedelta(days=30)
        scans_30_days = len([scan for scan in scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() >= thirty_days_ago])
        nfc_scans_30_days = len([scan for scan in nfc_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() >= thirty_days_ago])
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "cpu_usage": f"{cpu_percent:.1f}%",
                "ram_usage": f"{memory.percent:.1f}%",
                "uptime": uptime_str
            },
            "nfc": nfc_status,
            "statistics": {
                "scans_today": today_scans,
                "card_scans_today": today_nfc_scans,
                "scans_30_days": scans_30_days,
                "card_scans_30_days": nfc_scans_30_days
            }
        }
        
        return jsonify({
            "success": True,
            "data": data
        })
    except Exception as e:
        import logging
        logging.error(f"Dashboard-Daten Fehler: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route("/api/recent_scans")
@login_required
def recent_scans():
    """API-Endpoint für Live-Scan Updates - inkl. NFC-Scans."""
    try:
        import logging
        logger = logging.getLogger(__name__)

        limit = request.args.get('limit', 10, type=int)

        # Hole normale Barcode-Scans
        barcode_scans = get_current_scans()
        logger.debug(f"Found {len(barcode_scans)} barcode scans")

        # Hole NFC-Scans
        formatted_nfc_scans = []
        try:
            from app.nfc_reader import get_current_card_scans
            nfc_scans = get_current_card_scans()
            logger.info(f"Raw NFC scans loaded: {len(nfc_scans)} scans")

            # Deduplizierung: Track unique scans by pan_hash+timestamp (same logic as dashboard())
            seen_scans = set()

            # Filter to show scans from the last 30 days (consistent with cleanup policy)
            from datetime import datetime, timedelta
            thirty_days_ago = datetime.now() - timedelta(days=30)

            # Sort scans by timestamp (newest first) for deduplication
            nfc_scans_sorted = sorted(nfc_scans, key=lambda x: x.get('timestamp', ''), reverse=True)

            # Konvertiere NFC-Scans in einheitliches Format
            for nfc_scan in nfc_scans_sorted:
                # Handle different timestamp formats
                timestamp = nfc_scan.get('timestamp', '')
                scan_time = None
                if timestamp:
                    # Check if it's ISO format (from datetime.now().isoformat())
                    if 'T' in timestamp:
                        try:
                            # Parse ISO format
                            dt = datetime.fromisoformat(timestamp)
                            timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                            scan_time = dt
                        except:
                            logger.debug(f"Failed to parse ISO timestamp: {timestamp}")
                            # Use current time as fallback
                            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            scan_time = datetime.now()
                    else:
                        # Parse standard format
                        try:
                            scan_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                        except:
                            scan_time = datetime.now()
                else:
                    # No timestamp, use current time
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    scan_time = datetime.now()

                # Skip scans older than 30 days
                if scan_time and scan_time < thirty_days_ago:
                    continue

                # PCI DSS COMPLIANT: Use pan_hash for deduplication, pan_last4 for display
                pan_hash = nfc_scan.get('pan_hash')
                pan_last4 = nfc_scan.get('pan_last4')

                # Legacy support: if no hash exists, it's old plaintext data
                if not pan_hash and 'pan' in nfc_scan:
                    pan = nfc_scan.get('pan', '')
                    if pan and not is_hashed_pan(pan):
                        # Convert legacy plaintext to hash+last4
                        pan_hash = hash_pan(pan)
                        pan_last4 = pan[-4:] if len(pan) >= 4 else pan

                # FIXED: Deduplicate by pan_hash+timestamp instead of just pan_hash
                # This allows showing multiple scans of the same card at different times
                scan_key = f"{pan_hash}:{timestamp}"
                if scan_key in seen_scans:
                    logger.debug(f"Skipping exact duplicate NFC scan: {pan_hash[:8] if pan_hash else 'unknown'}...")
                    continue
                if pan_hash and timestamp:
                    seen_scans.add(scan_key)

                # Format PAN for display (PCI DSS compliant - masked)
                if pan_last4:
                    display_pan = f"****-{pan_last4}"
                else:
                    display_pan = "Unbekannt"

                # Determine status (make it user-friendly)
                status = nfc_scan.get('status', 'Erfolgreich')
                if 'Verweigert' in status:
                    status = 'Ungültig'
                elif status in ['NFC', 'Permanent', 'Temporär']:
                    status = 'Erfolgreich'

                # Generate unique ID for frontend deduplication
                unique_id = f"nfc-{pan_hash}" if pan_hash else f"nfc-{timestamp.replace(' ', '-').replace(':', '')}"

                formatted_scan = {
                    'id': unique_id,         # ✅ NEW: Unique ID for reliable frontend deduplication
                    'timestamp': timestamp,
                    'code': display_pan,  # Show masked PAN
                    'pan': display_pan,   # Backward compatibility
                    'pan_last4': pan_last4,  # ✅ Include pan_last4 for template
                    'pan_hash': pan_hash,    # ✅ Include pan_hash for deduplication
                    'card_type': nfc_scan.get('card_type', 'NFC'),
                    'status': status,
                    'type': 'NFC'
                }
                formatted_nfc_scans.append(formatted_scan)

                # Limit to showing max 10 recent unique scans
                if len(formatted_nfc_scans) >= 10:
                    break

            logger.info(f"Formatted {len(formatted_nfc_scans)} NFC scans")

        except ImportError as e:
            logger.error(f"Failed to import NFC reader module: {e}")
            formatted_nfc_scans = []
        except Exception as e:
            logger.error(f"Error getting NFC scans: {e}", exc_info=True)
            formatted_nfc_scans = []

        # Kombiniere alle Scans
        all_scans = barcode_scans + formatted_nfc_scans

        # Sortiere nach Zeitstempel (neueste zuerst)
        def parse_timestamp(scan):
            try:
                from datetime import datetime
                timestamp_str = scan.get('timestamp', '')
                if timestamp_str:
                    # Verschiedene Formate unterstützen
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S']:
                        try:
                            return datetime.strptime(timestamp_str, fmt)
                        except ValueError:
                            continue
                    # Fallback: aktuelles Datum
                    return datetime.now()
                return datetime.min
            except:
                return datetime.min

        try:
            all_scans.sort(key=parse_timestamp, reverse=True)
        except Exception as e:
            logger.debug(f"Failed to sort scans by timestamp: {e}")

        # Nehme nur die neuesten Scans
        recent = all_scans[:limit] if all_scans else []

        logger.info(f"Returning {len(recent)} recent scans (barcode: {len(barcode_scans)}, nfc: {len(formatted_nfc_scans)})")

        return jsonify({
            "success": True,
            "scans": recent,
            "total": len(all_scans),
            "barcode_count": len(barcode_scans),
            "nfc_count": len(formatted_nfc_scans)
        })
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Recent scans Fehler: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route("/api/system/log-level", methods=["POST"])
@admin_required
def set_log_level():
    """Setzt das Log-Level zur Laufzeit."""
    try:
        data = request.json
        new_level = data.get('level', 'INFO').upper()
        
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if new_level not in valid_levels:
            return jsonify({
                "success": False,
                "error": f"Ungültiges Log-Level. Gültige Werte: {', '.join(valid_levels)}"
            }), 400
        
        # Setze Log-Level für verschiedene Logger
        import logging
        logging.getLogger('app.nfc_reader').setLevel(getattr(logging, new_level))
        logging.getLogger('app.scanner').setLevel(getattr(logging, new_level))
        logging.getLogger('app.system_monitor').setLevel(getattr(logging, new_level))
        
        # Umgebungsvariable für NFC Debug-Modus setzen
        if new_level == 'DEBUG':
            os.environ['NFC_DEBUG'] = 'true'
        else:
            os.environ['NFC_DEBUG'] = 'false'
        
        from app.logger import log_system
        log_system(f"Log-Level geändert zu: {new_level}")
        
        return jsonify({
            "success": True,
            "message": f"Log-Level erfolgreich auf {new_level} gesetzt"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route("/delete_card", methods=["POST"])
@admin_required
def delete_card_route():
    """Löscht eine NFC-Karte."""
    data = request.json
    pan = data.get('pan')
    
    if not pan:
        return jsonify({
            "success": False,
            "error": "Keine Kartennummer angegeben"
        })
    
    try:
        success = delete_card(pan)
        
        if success:
            return jsonify({
                "success": True
            })
        else:
            return jsonify({
                "success": False,
                "error": "Karte konnte nicht gelöscht werden. Möglicherweise existiert sie nicht."
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/nfc/status")
@login_required
def nfc_status():
    """Gibt den aktuellen NFC-Reader-Status zurück."""
    try:
        # Hole den aktuellen NFC-Status
        from app.nfc_reader import get_nfc_status
        status = get_nfc_status()
        
        return jsonify({
            "success": True,
            "status": status
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/get_login_logs")
@login_required
def get_login_logs():
    """Gibt die Login-Logs zurück mit Pagination."""
    try:
        # Get pagination parameters from request
        page = request.args.get('page', 1, type=int)
        per_page = 10  # Fixed 10 entries per page for user login logs

        login_logs, total_entries, total_pages = get_login_log_entries(page=page, per_page=per_page)
        return jsonify({
            "success": True,
            "login_logs": login_logs,
            "page": page,
            "total_pages": total_pages,
            "total_entries": total_entries
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

def get_login_log_entries(page=1, per_page=10):
    """Holt erweiterte Login-Log-Einträge mit detaillierten Troubleshooting-Daten."""
    all_login_logs = []
    seen_entries = set()  # Set zum Tracking von bereits gesehenen Einträgen

    # Try both log files - system.log and app.log
    log_files = [
        os.path.join(os.path.dirname(__file__), '..', 'logs', 'system.log'),
        os.path.join(os.path.dirname(__file__), '..', 'logs', 'app.log')
    ]

    # Pattern für log Format: 2025-09-05 13:31:04,923 - SentraAI - INFO - Message
    log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([\w_]+) - (\w+) - (.+)'

    for log_file in log_files:
        if not os.path.exists(log_file):
            continue

        try:
            with open(log_file, 'r') as f:
                for line in f:
                    match = re.match(log_pattern, line.strip())
                    if match:
                        timestamp, logger_name, level, message = match.groups()

                        # Filter für Login-bezogene Nachrichten
                        if any(keyword in message.lower() for keyword in ['login', 'anmeldung', 'authentication', 'logged in', 'angemeldet', 'benutzeranmeldung']):
                            # Bestimme ob erfolgreich oder fehlgeschlagen
                            success = any(keyword in message.lower() for keyword in ['success', 'successful', 'erfolgreich', 'benutzeranmeldung'])

                            # Extrahiere Benutzername falls möglich
                            username = extract_username_from_message(message)

                            # Skip entries where username couldn't be determined
                            if username != 'Unbekannt':
                                # Enhanced login log entry with troubleshooting data
                                entry = {
                                    'timestamp': timestamp.split(',')[0],  # Remove milliseconds
                                    'milliseconds': timestamp.split(',')[1] if ',' in timestamp else "000",
                                    'username': username,
                                    'success': success,
                                    'level': level,
                                    'message': message,
                                    'ip_address': extract_ip_from_message(message) or 'unknown'
                                }

                                # Add user agent or client info if available
                                if 'browser' in message.lower() or 'client' in message.lower():
                                    entry['client_info'] = extract_client_info(message)

                                # Add error details for failed logins
                                if not success:
                                    if 'password' in message.lower():
                                        entry['failure_reason'] = 'Falsches Passwort'
                                    elif 'locked' in message.lower():
                                        entry['failure_reason'] = 'Konto gesperrt'
                                    else:
                                        entry['failure_reason'] = 'Authentifizierungsfehler'

                                # Erstelle einen eindeutigen Schlüssel für diesen Eintrag
                                # Basiert auf Timestamp und Username, um Duplikate zu vermeiden
                                entry_key = f"{entry['timestamp']}_{entry['username']}_{entry['success']}"

                                # Füge nur hinzu, wenn noch nicht gesehen
                                if entry_key not in seen_entries:
                                    seen_entries.add(entry_key)
                                    all_login_logs.append(entry)
        except Exception as e:
            logging.error(f"Fehler beim Lesen der Login-Logs aus {log_file}: {e}")

    # Sort by timestamp (newest first)
    all_login_logs.sort(key=lambda x: x['timestamp'], reverse=True)

    # Calculate pagination
    total_entries = len(all_login_logs)
    total_pages = (total_entries + per_page - 1) // per_page if total_entries > 0 else 1

    # Ensure page is valid
    page = max(1, min(page, total_pages))

    # Calculate start and end indices for current page
    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, total_entries)

    # Get entries for current page
    page_entries = all_login_logs[start_idx:end_idx]

    return page_entries, total_entries, total_pages

def extract_ip_from_message(message):
    """Extrahiert die IP-Adresse aus der Log-Nachricht."""
    # Pattern für IPv4 Adressen
    ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    match = re.search(ip_pattern, message)
    return match.group(0) if match else None

def extract_client_info(message):
    """Extrahiert Client/Browser-Informationen aus der Log-Nachricht."""
    # Patterns for common browsers and clients
    patterns = {
        'Chrome': r'Chrome/[\d.]+',
        'Firefox': r'Firefox/[\d.]+',
        'Safari': r'Safari/[\d.]+',
        'Edge': r'Edge/[\d.]+',
        'Mobile': r'Mobile|Android|iOS'
    }

    for name, pattern in patterns.items():
        if re.search(pattern, message):
            return name
    return 'Unknown'

def extract_username_from_message(message):
    """Extrahiert den Benutzernamen aus der Log-Nachricht."""
    # Spezifisches Pattern für "Benutzeranmeldung: username"
    patterns = [
        r'Benutzeranmeldung:\s*([^\s]+)',
        r'benutzeranmeldung:\s*([^\s]+)',
        r'user[:\s]+([^\s]+)',
        r'username[:\s]+([^\s]+)',
        r'benutzer[:\s]+([^\s]+)',
        r'für\s+([^\s]+)',
        r'von\s+([^\s]+)',
        r'User\s+([^\s]+)',
        r'Benutzer\s+([^\s]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return 'Unbekannt'

@bp.route("/api/session/info")
@login_required
def session_info():
    """Gibt Session-Informationen zurück - Vereinfacht"""
    user = session.get('user', {})
    info = {
        "username": user.get('username', ''),
        "role": user.get('role', 'user'),
        "logged_in": True
    }
    return jsonify({
        "success": True,
        "session": info
    })

@bp.route("/api/security/stats")
@admin_required
def security_stats():
    """Gibt einfache Sicherheitsstatistiken zurück"""
    stats = {
        "total_users": len(user_manager.get_all_users()),
        "current_session": session.get('user', {}).get('username', ''),
        "simple_auth": True
    }
    return jsonify({
        "success": True,
        "stats": stats
    })

@bp.route("/api/session/extend", methods=["POST"])
@login_required
def extend_session():
    """Verlängert die Session-Timeout - Vereinfacht"""
    user = session.get('user', {})
    session.permanent = True
    info = {
        "username": user.get('username', ''),
        "role": user.get('role', 'user'),
        "logged_in": True
    }
    return jsonify({
        "success": True,
        "message": "Session verlängert",
        "session": info
    })

@bp.route("/debug/nfc_status")
@login_required  
def debug_nfc_status():
    """Debug-Route für NFC-Status und Scan-Daten."""
    try:
        from app.nfc_reader import get_current_card_scans, get_nfc_status
        
        # Hole NFC-Scans
        nfc_scans = get_current_card_scans()
        
        # Hole NFC-Status
        nfc_status = get_nfc_status()
        
        # Berechne Statistiken
        today = datetime.now().date()
        today_nfc_scans = len([scan for scan in nfc_scans if datetime.strptime(scan['timestamp'], '%Y-%m-%d %H:%M:%S').date() == today])
        
        return jsonify({
            "success": True,
            "nfc_scans_total": len(nfc_scans),
            "nfc_scans_today": today_nfc_scans,
            "nfc_status": nfc_status,
            "sample_scans": nfc_scans[:3],  # Zeige erste 3 Scans
            "timestamp": datetime.now().isoformat()
        })
    except ImportError as e:
        return jsonify({
            "success": False,
            "error": f"NFC-Reader Modul nicht verfügbar: {e}"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

# ===============================================================
# ENHANCED NFC RAW DATA ANALYSIS ROUTES
# Erweiterte Analyse von NFC-Karten-Rohdaten zur Kartenfreigabe
# ===============================================================

# Weiterleitungen für alte NFC-Analyse-Routes
@bp.route("/nfc-analysis")
@login_required
def nfc_analysis():
    """
    Weiterleitung zur neuen vereinheitlichten Karten-Log-Seite.
    """
    flash('NFC-Analyse wurde in das Karten-Log integriert.', 'info')
    return redirect(url_for('routes.fallback_log'))

@bp.route("/nfc-card-details/<int:card_id>")
@login_required
def nfc_card_details(card_id):
    """
    Weiterleitung zur neuen vereinheitlichten Karten-Log-Seite mit Focus auf NFC-Karten.
    """
    flash(f'Kartendetails für ID {card_id} sind im Karten-Log verfügbar.', 'info')
    return redirect(url_for('routes.fallback_log') + '#nfc-cards')

@bp.route("/nfc-card-action", methods=["POST"])
@login_required  
def nfc_card_action():
    """
    Führt eine Aktion auf einer NFC-Karte aus (approve/reject/note).
    """
    try:
        from app.models.nfc_raw_data_analyzer import nfc_raw_data_analyzer
        
        card_id = request.form.get('card_id', type=int)
        action = request.form.get('action')
        admin_notes = request.form.get('admin_notes', '').strip()
        
        if not card_id or not action:
            flash('Ungültige Anfrage', 'error')
            return redirect(url_for('routes.fallback_log'))
        
        if action == 'approve':
            success = nfc_raw_data_analyzer.update_card_status(card_id, 'approved', admin_notes)
            if success:
                flash('Karte wurde genehmigt', 'success')
            else:
                flash('Fehler beim Genehmigen der Karte', 'error')
                
        elif action == 'reject':
            success = nfc_raw_data_analyzer.update_card_status(card_id, 'rejected', admin_notes)  
            if success:
                flash('Karte wurde abgelehnt', 'success')
            else:
                flash('Fehler beim Ablehnen der Karte', 'error')
                
        elif action == 'add_note':
            success = nfc_raw_data_analyzer.update_card_status(card_id, 'unknown', admin_notes)
            if success:
                flash('Notiz hinzugefügt', 'success')
            else:
                flash('Fehler beim Hinzufügen der Notiz', 'error')
        else:
            flash('Unbekannte Aktion', 'error')
        
        return redirect(url_for('routes.fallback_log'))
        
    except Exception as e:
        logger.error(f"Fehler bei der NFC-Karten-Aktion: {e}")
        flash(f'Fehler bei der Aktion: {str(e)}', 'error')
        return redirect(url_for('routes.fallback_log'))

@bp.route("/nfc-card-details-api")
@login_required
def nfc_card_details_api():
    """
    API-Endpoint für AJAX-Loading der Kartendetails.
    """
    try:
        from app.models.nfc_raw_data_analyzer import nfc_raw_data_analyzer
        
        card_id = request.args.get('card_id', type=int)
        if not card_id:
            return jsonify({'success': False, 'error': 'Keine Karten-ID angegeben'})
        
        card_data = nfc_raw_data_analyzer.get_card_details(card_id)
        if not card_data:
            return jsonify({'success': False, 'error': 'Karte nicht gefunden'})
        
        # Erstelle HTML für Modal-Content
        html_content = render_template('nfc_card_details_modal.html', card=card_data)
        
        return jsonify({'success': True, 'html': html_content})
        
    except Exception as e:
        logger.error(f"Fehler beim Laden der Kartendetails-API: {e}")
        return jsonify({'success': False, 'error': str(e)})

@bp.route("/nfc-export")
@login_required
def nfc_export():
    """
    Exportiert NFC-Kartendaten als JSON.
    """
    try:
        from app.models.nfc_raw_data_analyzer import nfc_raw_data_analyzer
        
        status_filter = request.args.get('status')
        export_data = nfc_raw_data_analyzer.export_card_data(status_filter)
        
        filename = f"nfc_cards_{status_filter or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        response = make_response(export_data)
        response.headers['Content-Type'] = 'application/json'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        logger.error(f"Fehler beim NFC-Export: {e}")
        flash(f'Fehler beim Export: {str(e)}', 'error')
        return redirect(url_for('routes.nfc_analysis'))

# ===============================================================
# FALLBACK ERROR LOGGING ROUTES (Legacy)
# Robustes Fallback-Logging für NFC-Scan Fehler
# ===============================================================

@bp.route("/fallback-log")
def fallback_log():
    """
    Einheitliches Karten-Fallback-Log mit NFC-Analyse und Error-Logs.
    """
    try:
        from app import error_logger
        from app.models.nfc_raw_data_analyzer import nfc_raw_data_analyzer
        
        # Hole Legacy Error-Logs
        logs = error_logger.get_fallback_logs(limit=50)
        total_count = error_logger.get_fallback_log_count()
        error_stats = error_logger.get_error_type_stats()
        
        # Hole NFC-Karten-Daten (alle Status für Übersicht)
        nfc_cards = []
        nfc_stats = {}
        
        try:
            # Hole alle Karten (alle Status)
            all_cards = nfc_raw_data_analyzer.get_all_cards(limit=100)
            nfc_cards = all_cards[:50]  # Begrenze auf 50 für Performance
            
            # Berechne NFC-Statistiken
            nfc_stats = {
                'total_unknown': len([c for c in all_cards if c['status'] == 'unknown']),
                'high_confidence': len([c for c in all_cards if c['confidence_score'] > 0.7]),
                'frequent_scans': len([c for c in all_cards if c['scan_count'] > 3]),
                'recent_scans': len([c for c in all_cards if 
                                   (datetime.now() - datetime.fromisoformat(c['last_seen'])).days < 7])
            }
        except Exception as nfc_err:
            logger.debug(f"NFC-Daten konnten nicht geladen werden: {nfc_err}")
            nfc_stats = {'total_unknown': 0, 'high_confidence': 0, 'frequent_scans': 0, 'recent_scans': 0}
        
        return render_template('fallback_log.html',
                             logs=logs,
                             total_count=total_count,
                             error_stats=error_stats,
                             nfc_cards=nfc_cards,
                             nfc_stats=nfc_stats)
                             
    except Exception as e:
        logger.error(f"Fehler beim Laden des Fallback-Logs: {e}")
        flash(f'Fehler beim Laden des Fallback-Logs: {str(e)}', 'error')
        return redirect(url_for('routes.dashboard'))


@bp.route("/fallback-log/api/export")
def fallback_log_export():
    """
    Exportiert Fallback-Logs als CSV-Datei.
    Für alle Benutzer zugänglich.
    """
    try:
        from app import error_logger
        from flask import Response
        
        # Parameter für Export
        limit = request.args.get('limit', 1000, type=int)
        
        # CSV-Export generieren
        csv_content = error_logger.export_fallback_logs_csv(limit=limit)
        
        # Response mit CSV-Content-Type
        response = Response(
            csv_content,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=fallback_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )
        
        logger.info(f"Fallback-Logs CSV-Export durchgeführt (limit={limit})")
        return response
        
    except Exception as e:
        logger.error(f"Fehler beim CSV-Export der Fallback-Logs: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route("/fallback-log/api/cleanup", methods=['POST'])
def fallback_log_cleanup():
    """
    Bereinigt alte Fallback-Logs (älter als X Tage).
    Für alle Benutzer zugänglich.
    """
    try:
        from app import error_logger
        
        # Parameter für Bereinigung
        days_to_keep = request.json.get('days_to_keep', 90) if request.json else 90
        
        # Validierung
        if not isinstance(days_to_keep, int) or days_to_keep < 1:
            return jsonify({
                "success": False,
                "error": "days_to_keep muss eine positive Ganzzahl sein"
            }), 400
        
        # Bereinigung durchführen
        deleted_count = error_logger.cleanup_old_logs(days_to_keep=days_to_keep)
        
        logger.info(f"Fallback-Logs Bereinigung durchgeführt: {deleted_count} Logs gelöscht (älter als {days_to_keep} Tage)")
        
        return jsonify({
            "success": True,
            "deleted_count": deleted_count,
            "days_to_keep": days_to_keep
        })
        
    except Exception as e:
        logger.error(f"Fehler bei der Bereinigung der Fallback-Logs: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route("/api/read-faulty-card", methods=['POST'])
@admin_required
def read_faulty_nfc_card():
    """
    Liest alle Rohdaten einer fehlerhaften NFC-Karte aus.
    Speichert die Daten strukturiert für spätere Analyse.
    """
    try:
        from app.nfc_reader import NFCReader
        import json
        from datetime import datetime

        # Erstelle NFC Reader Instanz
        reader = NFCReader()

        # Versuche die Karte zu lesen und alle verfügbaren Daten zu sammeln
        card_data = {}

        # Basis-Informationen
        card_info = reader.read_card()
        if card_info:
            card_data['basic_info'] = card_info

        # Versuche erweiterte Daten zu lesen (ATR, Speicherbereiche, etc.)
        try:
            # Hier könnten weitere Leseoperationen implementiert werden
            # z.B. verschiedene APDUs senden, um mehr Daten zu sammeln
            card_data['timestamp'] = datetime.now().isoformat()
            card_data['status'] = 'faulty_read'

            # Speichere in Datei
            faulty_cards_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'faulty_cards.json')

            # Lade bestehende Daten
            if os.path.exists(faulty_cards_file):
                with open(faulty_cards_file, 'r') as f:
                    faulty_cards = json.load(f)
            else:
                faulty_cards = []

            # Füge neue Karte hinzu
            faulty_cards.append(card_data)

            # Speichere zurück
            os.makedirs(os.path.dirname(faulty_cards_file), exist_ok=True)
            with open(faulty_cards_file, 'w') as f:
                json.dump(faulty_cards, f, indent=2)

            logger.info(f"Fehlerhafte Karte erfolgreich ausgelesen und gespeichert")

            return jsonify({
                "success": True,
                "message": "Karte erfolgreich ausgelesen",
                "card_data": card_data
            })

        except Exception as read_error:
            logger.error(f"Fehler beim erweiterten Kartenlesen: {read_error}")
            return jsonify({
                "success": False,
                "error": f"Konnte Kartendaten nicht vollständig lesen: {str(read_error)}"
            }), 500

    except Exception as e:
        logger.error(f"Fehler beim Lesen der fehlerhaften Karte: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route("/nfc-errors/export")
@login_required
def export_nfc_errors():
    """Vereinfachter Export für problematische NFC-Karten - speziell für Entwickler."""
    try:
        from app import error_logger
        
        # Hole die letzten 100 Fehler-Logs
        logs = error_logger.get_fallback_logs(limit=100)
        
        # Erstelle strukturierten Export nur mit relevanten Daten
        export_data = []
        for log in logs:
            raw_data = log.get('raw_data', '')
            
            # Suche nach PAN-Daten
            pan_match = re.search(r'PAN:\s*(\d+)', raw_data)
            pan = pan_match.group(1) if pan_match else 'Nicht gefunden'
            
            # Suche nach spezifischen Fehlern
            pse_success = 'PSE.*OK.*9000' in raw_data or 'german_contactless_pse.*OK' in raw_data
            aid_errors = re.findall(r'select.*aid.*([A-F0-9]+).*Fehler.*([6-9A-F][0-9A-F]{3})', raw_data, re.IGNORECASE)
            
            export_entry = {
                'timestamp': log.get('timestamp', ''),
                'pan': pan[:6] + '****' + pan[-4:] if len(pan) > 10 else pan,
                'full_pan': pan,  # Für Entwickler-Analyse
                'pse_success': pse_success,
                'aid_failures': len(aid_errors),
                'aid_error_codes': [error[1] for error in aid_errors],
                'error_type': log.get('error_type', ''),
                'raw_data_preview': raw_data[:500],  # Erste 500 Zeichen
                'full_raw_data': raw_data  # Vollständige Daten für Analyse
            }
            export_data.append(export_entry)
        
        # Als JSON-Response zurückgeben für einfache Analyse
        response = make_response(json.dumps(export_data, indent=2, ensure_ascii=False))
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=nfc_errors_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        
        return response
        
    except Exception as e:
        logger.error(f"Fehler beim NFC-Error-Export: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route("/webhook-logs")
@login_required
def webhook_logs():
    """
    Webhook-Logs Übersicht mit Statistiken und Filterung.
    """
    try:
        from app.safe_logging import safe_get_webhook_logs, safe_get_webhook_stats
        
        # Parameter aus Query String
        limit = int(request.args.get('limit', 50))
        webhook_type = request.args.get('type', None)
        hours_back = int(request.args.get('hours', 24))
        
        # Hole Webhook-Logs und Statistiken
        logs = safe_get_webhook_logs(limit=limit, webhook_type=webhook_type)
        stats = safe_get_webhook_stats(hours_back=hours_back)
        
        return render_template('webhook_logs.html',
                               logs=logs,
                               stats=stats,
                               current_filter=webhook_type,
                               hours_back=hours_back,
                               limit=limit)
        
    except Exception as e:
        logger.error(f"Fehler in webhook_logs Route: {e}")
        flash(f'Fehler beim Laden der Webhook-Logs: {e}', 'danger')
        return render_template('webhook_logs.html',
                               logs=[],
                               stats={'total_requests': 0, 'error': str(e), 'avg_response_time_ms': 0})

@bp.route("/webhook-logs/export")
@login_required
def webhook_logs_export():
    """
    Exportiert Webhook-Logs als CSV.
    """
    try:
        from app.webhook_logger import export_webhook_logs_csv
        
        hours_back = int(request.args.get('hours', 24))
        csv_content = export_webhook_logs_csv(hours_back=hours_back)
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=webhook_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return response
        
    except Exception as e:
        logger.error(f"Fehler beim Webhook-Log CSV-Export: {e}")
        flash(f'Fehler beim CSV-Export: {e}', 'danger')
        return redirect(url_for('routes.webhook_logs'))

@bp.route("/webhook-logs/cleanup", methods=["POST"])
@admin_required
def webhook_logs_cleanup():
    """
    Bereinigt alte Webhook-Logs.
    """
    try:
        from app.webhook_logger import cleanup_old_webhook_logs
        
        days_to_keep = int(request.form.get('days_to_keep', 30))
        deleted_count = cleanup_old_webhook_logs(days_to_keep=days_to_keep)
        
        if deleted_count > 0:
            flash(f'✅ {deleted_count} alte Webhook-Logs erfolgreich gelöscht.', 'success')
        else:
            flash('ℹ️ Keine alten Webhook-Logs zum Löschen gefunden.', 'info')
            
    except Exception as e:
        logger.error(f"Fehler beim Bereinigen der Webhook-Logs: {e}")
        flash(f'❌ Fehler beim Bereinigen: {e}', 'danger')
    
    return redirect(url_for('routes.webhook_logs'))


# =============================================================================
# NETWORK CONFIGURATION ROUTES
# =============================================================================

@bp.route("/api/current_ip")
@login_required
def get_current_ip():
    """Get the current IP address of the system."""
    try:
        ip_address = network_manager.get_current_ip()
        return jsonify({
            "success": True,
            "ip": ip_address
        })
    except Exception as e:
        logger.error(f"Failed to get current IP: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "ip": "Fehler"
        })

@bp.route("/api/network/interfaces")
@login_required
def get_network_interfaces():
    """Get all network interfaces and their configuration."""
    try:
        interfaces = network_manager.get_interfaces(force_refresh=True)
        return jsonify({
            "success": True,
            "interfaces": {
                name: {
                    "name": iface.name,
                    "ip_address": iface.ip_address,
                    "netmask": iface.netmask,
                    "gateway": iface.gateway,
                    "dns_servers": iface.dns_servers,
                    "is_dhcp": iface.is_dhcp,
                    "is_connected": iface.is_connected,
                    "mac_address": iface.mac_address,
                    "interface_type": iface.interface_type
                }
                for name, iface in interfaces.items()
            }
        })
    except Exception as e:
        logger.error(f"Failed to get network interfaces: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/network/config/<interface_name>")
@login_required
def get_network_config(interface_name):
    """Get network configuration for a specific interface."""
    try:
        config = network_manager.get_network_config(interface_name)
        return jsonify({
            "success": True,
            "interface": config.interface,
            "is_dhcp": config.is_dhcp,
            "static_ip": config.static_ip,
            "static_netmask": config.static_netmask,
            "static_gateway": config.static_gateway,
            "static_dns": config.static_dns
        })
    except Exception as e:
        logger.error(f"Failed to get network config for {interface_name}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/network/config", methods=["POST"])
@admin_required
def save_network_config():
    """Save network configuration for an interface."""
    try:
        data = request.json

        # Validate required fields
        interface_name = data.get('interface')
        if not interface_name:
            return jsonify({
                "success": False,
                "error": "Interface name is required"
            })

        is_dhcp = data.get('is_dhcp', True)

        # Create config object
        from app.models.network import NetworkConfig
        config = NetworkConfig(
            interface=interface_name,
            is_dhcp=is_dhcp
        )

        # If static configuration, validate and set static fields
        if not is_dhcp:
            static_ip = data.get('static_ip', '').strip()
            static_netmask = data.get('static_netmask', '').strip()
            static_gateway = data.get('static_gateway', '').strip()

            if not all([static_ip, static_netmask, static_gateway]):
                return jsonify({
                    "success": False,
                    "error": "Static IP, netmask, and gateway are required for static configuration"
                })

            config.static_ip = static_ip
            config.static_netmask = static_netmask
            config.static_gateway = static_gateway
            config.static_dns = data.get('static_dns', [])

        # Save configuration
        success = network_manager.save_network_config(config)

        if success:
            logger.info(f"Network configuration saved for interface {interface_name}")
            return jsonify({
                "success": True,
                "message": "Network configuration saved successfully",
                "reboot_required": True,
                "reboot_message": "Ein Neustart ist erforderlich, damit die Netzwerk-Änderungen wirksam werden."
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to save network configuration"
            })

    except Exception as e:
        logger.error(f"Failed to save network config: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/network/apply", methods=["POST"])
@admin_required
def apply_network_config():
    """Apply saved network configuration changes."""
    try:
        success = network_manager.apply_network_config()

        if success:
            logger.info("Network configuration applied successfully")
            return jsonify({
                "success": True,
                "message": "Network configuration applied successfully",
                "reboot_required": True,
                "reboot_message": "Ein System-Neustart ist erforderlich, um die Netzwerk-Konfiguration vollständig zu aktivieren."
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to apply network configuration"
            })

    except Exception as e:
        logger.error(f"Failed to apply network config: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/network/test_connectivity", methods=["POST"])
@login_required
def test_network_connectivity():
    """Test network connectivity."""
    try:
        host = request.json.get('host', '8.8.8.8') if request.json else '8.8.8.8'
        success = network_manager.test_connectivity(host)

        return jsonify({
            "success": success,
            "message": f"Connectivity test {'passed' if success else 'failed'} for {host}"
        })

    except Exception as e:
        logger.error(f"Connectivity test failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/network/diagnostics")
@login_required
def get_network_diagnostics():
    """Get network diagnostics information."""
    try:
        # Collect various network diagnostics
        diagnostics = []

        # Get route table
        try:
            result = subprocess.run(['ip', 'route'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                diagnostics.append("=== ROUTING TABLE ===")
                diagnostics.append(result.stdout)
        except Exception as e:
            diagnostics.append(f"Failed to get routing table: {e}")

        # Get interface details
        try:
            result = subprocess.run(['ip', 'addr'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                diagnostics.append("\n=== INTERFACE DETAILS ===")
                diagnostics.append(result.stdout)
        except Exception as e:
            diagnostics.append(f"Failed to get interface details: {e}")

        # Get DNS configuration
        try:
            if os.path.exists('/etc/resolv.conf'):
                with open('/etc/resolv.conf', 'r') as f:
                    diagnostics.append("\n=== DNS CONFIGURATION ===")
                    diagnostics.append(f.read())
        except Exception as e:
            diagnostics.append(f"Failed to read DNS config: {e}")

        # Test connectivity
        try:
            result = subprocess.run(['ping', '-c', '3', '8.8.8.8'],
                                  capture_output=True, text=True, timeout=15)
            diagnostics.append("\n=== CONNECTIVITY TEST (8.8.8.8) ===")
            diagnostics.append(result.stdout)
        except Exception as e:
            diagnostics.append(f"Failed to test connectivity: {e}")

        return jsonify({
            "success": True,
            "diagnostics": "\n".join(diagnostics)
        })

    except Exception as e:
        logger.error(f"Failed to get network diagnostics: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/network/restart", methods=["POST"])
@admin_required
def restart_networking():
    """Restart the networking service."""
    try:
        # Try to restart dhcpcd service
        result = subprocess.run(['sudo', 'systemctl', 'restart', 'dhcpcd'],
                               capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            logger.info("Networking service restarted successfully")
            return jsonify({
                "success": True,
                "message": "Networking service restarted successfully",
                "reboot_recommended": True,
                "reboot_message": "Ein vollständiger Neustart wird empfohlen für optimale Netzwerk-Konfiguration."
            })
        else:
            logger.error(f"Failed to restart networking: {result.stderr}")
            return jsonify({
                "success": False,
                "error": f"Failed to restart networking service: {result.stderr}"
            })

    except Exception as e:
        logger.error(f"Failed to restart networking: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/system/reboot", methods=["POST"])
@admin_required
def system_reboot():
    """Reboot the system."""
    try:
        # Schedule reboot in 5 seconds to allow response to be sent
        subprocess.Popen(['sudo', 'shutdown', '-r', '+0'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)

        logger.info("System reboot initiated")
        return jsonify({
            "success": True,
            "message": "System wird in 5 Sekunden neu gestartet..."
        })
    except Exception as e:
        logger.error(f"Failed to initiate system reboot: {e}")
        return jsonify({
            "success": False,
            "error": f"Neustart konnte nicht initiiert werden: {str(e)}"
        })

# ==================== TIME-BASED DOOR CONTROL API ENDPOINTS ====================

@bp.route("/api/door_status", methods=["GET"])
@login_required
def get_door_status():
    """Get simple door status for live display."""
    try:
        from app.models.door_control_simple import simple_door_control_manager as door_control_manager
        from app.gpio_control import get_gpio_state

        current_mode = door_control_manager.get_current_mode()
        next_change = door_control_manager.get_next_mode_change()
        gpio_status = get_gpio_state()

        return jsonify({
            "success": True,
            "current_mode": current_mode,
            "gpio_state": "HIGH" if gpio_status.get("state") == 1 else "LOW",
            "next_change": next_change
        })
    except Exception as e:
        logger.error(f"Failed to get door status: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/door_control/status", methods=["GET"])
@login_required
def get_door_control_status():
    """Get comprehensive door control status."""
    try:
        from app.models.door_control_simple import simple_door_control_manager as door_control_manager

        status = door_control_manager.get_status()

        logger.info("Door control status requested")
        return jsonify({
            "success": True,
            "status": status
        })
    except Exception as e:
        logger.error(f"Failed to get door control status: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/door_control/config", methods=["GET"])
@admin_required
def get_door_control_config():
    """Get door control configuration."""
    try:
        from app.models.door_control_simple import simple_door_control_manager as door_control_manager

        config = door_control_manager.get_config()

        logger.info("Door control configuration requested")
        return jsonify({
            "success": True,
            "config": config
        })
    except Exception as e:
        logger.error(f"Failed to get door control config: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/door_control/config", methods=["POST"])
@admin_required
def update_door_control_config():
    """Update door control configuration."""
    try:
        from app.models.door_control_simple import simple_door_control_manager as door_control_manager

        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
        else:
            # Convert form data to the expected format
            data = {
                "enabled": True,  # Always enabled for form submissions
                "mode": request.form.get("door_control_mode", "time_based"),  # Handle mode selection
                "modes": {
                    "always_open": {
                        "enabled": request.form.get("always_open_enabled") == "on",
                        "start_time": request.form.get("always_open_start", "08:00"),
                        "end_time": request.form.get("always_open_end", "16:00"),
                        "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                    },
                    "normal_operation": {
                        "enabled": request.form.get("normal_operation_enabled") == "on",
                        "start_time": request.form.get("normal_operation_start", "16:00"),
                        "end_time": request.form.get("normal_operation_end", "04:00"),
                        "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                    },
                    "access_blocked": {
                        "enabled": request.form.get("access_blocked_enabled") == "on",
                        "start_time": request.form.get("access_blocked_start", "04:00"),
                        "end_time": request.form.get("access_blocked_end", "08:00"),
                        "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                    }
                },
                "fail_safe": {
                    "qr_exit_always_enabled": True
                }
            }

        if not data:
            flash("Keine Konfigurationsdaten empfangen", "error")
            return redirect(url_for('routes.opening_hours'))

        # Get previous config for logging
        previous_config = door_control_manager.get_config()

        success = door_control_manager.update_config(data)

        if success:
            # Log door control configuration changes
            username = session.get('username', 'unknown')
            try:
                log_system(f"Door control configuration updated",
                          extra_context={
                              'changed_by': username,
                              'previous_mode': previous_config.get('mode', 'unknown'),
                              'new_mode': data.get('mode', 'unknown'),
                              'modes_config': data.get('modes', {}),
                              'change_time': datetime.now().isoformat(),
                              'is_json_request': request.is_json
                          })
            except:
                logging.info(f"Door control configuration updated by {username}")

            logger.info("Door control configuration updated successfully")
            if request.is_json:
                return jsonify({
                    "success": True,
                    "message": "Configuration updated successfully"
                })
            else:
                flash("Türsteuerungs-Konfiguration erfolgreich aktualisiert", "success")
                return redirect(url_for('routes.opening_hours'))
        else:
            if request.is_json:
                return jsonify({
                    "success": False,
                    "error": "Failed to update configuration"
                })
            else:
                flash("Fehler beim Aktualisieren der Konfiguration", "error")
                return redirect(url_for('routes.opening_hours'))

    except Exception as e:
        logger.error(f"Failed to update door control config: {e}")
        if request.is_json:
            return jsonify({
                "success": False,
                "error": str(e)
            })
        else:
            flash(f"Fehler: {str(e)}", "error")
            return redirect(url_for('routes.opening_hours'))

@bp.route("/api/door_control/override", methods=["POST"])
@admin_required
def set_door_control_override():
    """Set temporary door control mode override."""
    try:
        from app.models.door_control_simple import simple_door_control_manager as door_control_manager

        data = request.get_json()
        mode = data.get('mode')
        duration_hours = float(data.get('duration_hours', 1.0))

        valid_modes = ["always_open", "normal_operation", "access_blocked"]
        if mode not in valid_modes:
            return jsonify({
                "success": False,
                "error": f"Invalid mode. Must be one of: {valid_modes}"
            })

        success = door_control_manager.set_override(mode, duration_hours)

        if success:
            logger.info(f"Door control override set: {mode} for {duration_hours} hours")
            return jsonify({
                "success": True,
                "message": f"Override set to {mode} for {duration_hours} hours"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to set override"
            })

    except Exception as e:
        logger.error(f"Failed to set door control override: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/door_control/override", methods=["DELETE"])
@admin_required
def clear_door_control_override():
    """Clear any active door control mode override."""
    try:
        from app.models.door_control_simple import simple_door_control_manager as door_control_manager

        success = door_control_manager.clear_override()

        if success:
            logger.info("Door control override cleared")
            return jsonify({
                "success": True,
                "message": "Override cleared successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to clear override"
            })

    except Exception as e:
        logger.error(f"Failed to clear door control override: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/door_control/sync_gpio", methods=["POST"])
@admin_required
def sync_door_control_gpio():
    """Manually synchronize GPIO state with door control mode."""
    try:
        from app.gpio_control import sync_gpio_with_time_based_control

        success = sync_gpio_with_time_based_control()

        if success:
            logger.info("GPIO synchronized with door control mode")
            return jsonify({
                "success": True,
                "message": "GPIO synchronized successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to synchronize GPIO"
            })

    except Exception as e:
        logger.error(f"Failed to sync GPIO: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@bp.route("/api/door_control/test_access", methods=["POST"])
@admin_required
def test_door_control_access():
    """Test door access based on current mode (for debugging)."""
    try:
        from app.models.door_control_simple import simple_door_control_manager as door_control_manager

        data = request.get_json()
        scan_type = data.get('scan_type', 'nfc')  # 'nfc' or 'qr'
        is_exit = data.get('is_exit', False)

        current_mode = door_control_manager.get_current_mode()

        if scan_type == 'nfc':
            allowed, reason = door_control_manager.should_allow_nfc_access()
        elif scan_type == 'qr':
            allowed, reason = door_control_manager.should_allow_qr_access(is_exit)
        else:
            return jsonify({
                "success": False,
                "error": "Invalid scan_type. Must be 'nfc' or 'qr'"
            })

        logger.info(f"Access test: {scan_type} - {allowed} - {reason}")
        return jsonify({
            "success": True,
            "result": {
                "current_mode": current_mode,
                "scan_type": scan_type,
                "is_exit": is_exit,
                "access_allowed": allowed,
                "reason": reason
            }
        })

    except Exception as e:
        logger.error(f"Failed to test door access: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

