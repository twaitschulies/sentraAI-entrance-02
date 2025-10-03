import json
import os
import datetime
import time
from collections import defaultdict, deque
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session, request
from app.config import USERS_FILE, DEFAULT_ADMIN, MAX_LOGIN_ATTEMPTS, LOGIN_ATTEMPT_WINDOW, LOCKOUT_DURATION, SESSION_TIMEOUT

# ===============================================================
# ADMIN LOGIN: admin/admin ist PERMANENT im Code fest definiert!
# 
# Das Admin-Login funktioniert IMMER, unabhängig von:
# - users.json Datei-Status
# - Hash-Funktionen
# - Neustart des Systems
# - Datei-Löschungen
#
# Der admin/admin Login ist in der authenticate() Methode
# als direkter String-Vergleich implementiert.
# ===============================================================

class Auth:
    def __init__(self):
        self.users_file = USERS_FILE
        self.login_attempts = defaultdict(deque)  # IP -> Timestamps
        self.lockouts = {}  # IP -> lockout_until_timestamp
        self.ensure_users_file_exists()
    
    def ensure_users_file_exists(self):
        """Stellt sicher, dass die Benutzerdatei existiert (admin/admin funktioniert immer im Code)."""
        os.makedirs(os.path.dirname(self.users_file), exist_ok=True)
        
        # admin/admin ist jetzt im Code fest integriert - users.json nur für andere Benutzer
        if not os.path.exists(self.users_file):
            # Erstelle leere users.json für andere Benutzer
            empty_data = {"users": []}
            with open(self.users_file, 'w') as f:
                json.dump(empty_data, f, indent=4)
            
            from app.logger import system_logger
            system_logger.info("users.json erstellt - admin/admin ist im Code fest definiert")
    
    def load_users(self):
        """Lädt alle Benutzer aus der Datei (admin/admin ist im Code fest definiert)."""
        try:
            with open(self.users_file, 'r') as f:
                data = json.load(f)
                return data.get("users", [])
        except (FileNotFoundError, json.JSONDecodeError):
            # Erstelle leere Datei wenn nicht vorhanden
            self.ensure_users_file_exists()
            return []
    
    def save_users(self, users):
        """Speichert Benutzer in der Datei."""
        with open(self.users_file, 'w') as f:
            json.dump({"users": users}, f, indent=4)
    
    def authenticate(self, username, password):
        """Authentifiziert einen Benutzer mit Rate Limiting."""
        # IP-Adresse für Rate Limiting
        ip_address = request.remote_addr or '127.0.0.1'
        
        # Prüfe ob IP gesperrt ist
        if self.is_ip_locked_out(ip_address):
            from app.logger import log_system
            log_system(f"Login-Versuch von gesperrter IP: {ip_address}")
            return False
        
        # ========================================
        # PERMANENT ADMIN LOGIN: admin/admin
        # Funktioniert IMMER, bei jedem Neustart!
        # ========================================
        if username == "admin" and password == "admin":
            # Erfolgreiche Authentifizierung für admin
            self.record_login_attempt(ip_address, success=True)
            
            # Erstelle eine Login-Session
            session['user_id'] = username
            session['user_role'] = "admin"
            session['logged_in'] = True
            session['login_time'] = datetime.datetime.now().isoformat()
            session['ip_address'] = ip_address
            
            # Protokollieren des Logins
            self.log_login(username)
            return True
        
        # Fallback: Prüfe andere Benutzer aus der Datei
        users = self.load_users()
        
        for user in users:
            if user["username"] == username and user["username"] != "admin":  # admin schon oben geprüft
                if check_password_hash(user["password"], password):
                    # Erfolgreiche Authentifizierung
                    self.record_login_attempt(ip_address, success=True)
                    
                    # Erstelle eine Login-Session
                    session['user_id'] = username
                    session['user_role'] = user["role"]
                    session['logged_in'] = True
                    session['login_time'] = datetime.datetime.now().isoformat()
                    session['ip_address'] = ip_address
                    
                    # Protokollieren des Logins
                    self.log_login(username)
                    return True
        
        # Fehlgeschlagene Authentifizierung
        self.record_login_attempt(ip_address, success=False)
        return False
    
    def log_login(self, username):
        """Protokolliert einen Login-Vorgang."""
        from app.logger import system_logger
        system_logger.info(f"Benutzeranmeldung: {username}")
    
    def is_logged_in(self):
        """Prüft, ob ein Benutzer angemeldet ist und Session gültig ist."""
        if not session.get('logged_in', False):
            return False
        
        # Session-Hijacking-Schutz: IP-Adresse prüfen
        current_ip = request.remote_addr or '127.0.0.1'
        session_ip = session.get('ip_address', '')
        
        if current_ip != session_ip:
            from app.logger import log_system
            log_system(f"Möglicher Session-Hijacking-Versuch: Session IP {session_ip}, Aktuelle IP {current_ip}")
            self.logout()  # Session invalidieren
            return False
        
        # Session-Timeout prüfen
        login_time_str = session.get('login_time')
        if login_time_str:
            login_time = datetime.datetime.fromisoformat(login_time_str)
            if (datetime.datetime.now() - login_time).total_seconds() > SESSION_TIMEOUT:
                from app.logger import log_system
                log_system(f"Session-Timeout für Benutzer {session.get('user_id')}")
                self.logout()
                return False
        
        return True
    
    def is_admin(self):
        """Prüft, ob der angemeldete Benutzer ein Administrator ist."""
        return session.get('role') == 'admin'  # Fixed to use consistent session.role
    
    def get_current_user(self):
        """Gibt den aktuellen Benutzer zurück."""
        return session.get('user_id')
    
    def logout(self):
        """Meldet den Benutzer ab."""
        session.pop('user_id', None)
        session.pop('user_role', None)
        session.pop('logged_in', None)
    
    def create_user(self, username, password, role="user"):
        """Erstellt einen neuen Benutzer."""
        if not self.is_admin():
            return False, "Nur Administratoren können Benutzer anlegen"
        
        users = self.load_users()
        
        # Prüfe, ob der Benutzername bereits existiert
        if any(user["username"] == username for user in users):
            return False, "Benutzername existiert bereits"
        
        # Erstelle neuen Benutzer
        new_user = {
            "username": username,
            "password": generate_password_hash(password),
            "role": role,
            "created_at": datetime.datetime.now().isoformat()
        }
        
        users.append(new_user)
        self.save_users(users)
        
        # Protokollieren der Benutzererstellung
        from app.logger import system_logger
        system_logger.info(f"Neuer Benutzer erstellt: {username} (Rolle: {role})")
        
        return True, "Benutzer erfolgreich erstellt"
    
    def delete_user(self, username):
        """Löscht einen Benutzer."""
        if not self.is_admin():
            return False, "Nur Administratoren können Benutzer löschen"
        
        # Verhindere das Löschen des Default-Admin
        if username == DEFAULT_ADMIN['username']:
            return False, "Der Standard-Administrator kann nicht gelöscht werden"
        
        users = self.load_users()
        initial_count = len(users)
        
        users = [user for user in users if user["username"] != username]
        
        if len(users) < initial_count:
            self.save_users(users)
            
            # Protokollieren der Benutzerlöschung
            from app.logger import system_logger
            system_logger.info(f"Benutzer gelöscht: {username}")
            
            return True, "Benutzer erfolgreich gelöscht"
        
        return False, "Benutzer nicht gefunden"
    
    def get_all_users(self):
        """Gibt alle Benutzer zurück (admin + andere aus Datei)."""
        if not self.is_admin():
            return []
        
        users = self.load_users()
        
        # Füge admin hinzu (immer verfügbar)
        admin_user = {
            "username": "admin",
            "role": "admin",
            "created_at": "Fest im Code definiert",
            "source": "Code (immer aktiv)"
        }
        
        # Entferne Passwörter aus anderen Benutzern
        for user in users:
            user.pop('password', None)
            user["source"] = "users.json"
        
        # Admin an den Anfang setzen
        all_users = [admin_user] + users
        
        return all_users
    
    def is_ip_locked_out(self, ip_address):
        """Prüft, ob eine IP-Adresse gesperrt ist."""
        if ip_address in self.lockouts:
            lockout_until = self.lockouts[ip_address]
            if time.time() < lockout_until:
                return True
            else:
                # Lockout abgelaufen
                del self.lockouts[ip_address]
        return False
    
    def record_login_attempt(self, ip_address, success=False):
        """Zeichnet einen Login-Versuch auf."""
        current_time = time.time()
        
        if success:
            # Bei erfolgreichem Login, alle Versuche löschen
            if ip_address in self.login_attempts:
                del self.login_attempts[ip_address]
            if ip_address in self.lockouts:
                del self.lockouts[ip_address]
        else:
            # Fehlgeschlagenen Versuch aufzeichnen
            attempts = self.login_attempts[ip_address]
            attempts.append(current_time)
            
            # Alte Versuche entfernen (außerhalb des Zeitfensters)
            while attempts and attempts[0] < current_time - LOGIN_ATTEMPT_WINDOW:
                attempts.popleft()
            
            # Prüfen ob Limit überschritten
            if len(attempts) >= MAX_LOGIN_ATTEMPTS:
                self.lockouts[ip_address] = current_time + LOCKOUT_DURATION
                from app.logger import log_system
                log_system(f"IP-Adresse {ip_address} nach {len(attempts)} fehlgeschlagenen Login-Versuchen gesperrt")

# Erstelle eine globale Instanz zur Verwendung in der Anwendung
auth = Auth() 