import json
import os
import base64
from typing import Dict, Optional
from ..config import DATA_DIR
from ..logger import log_system, log_error

WHITELABEL_FILE = os.path.join(DATA_DIR, "whitelabel.json")
LOGO_DIR = os.path.join(DATA_DIR, "logos")

class WhitelabelManager:
    """Manages white-label configuration for customizing the application's appearance."""

    def __init__(self):
        """Initialize the WhitelabelManager and load configuration."""
        self.config = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load white-label configuration from the JSON file."""
        try:
            if os.path.exists(WHITELABEL_FILE):
                with open(WHITELABEL_FILE, 'r') as f:
                    self.config = json.load(f)
                log_system("White-label configuration loaded successfully")
            else:
                # Default configuration
                self.config = {
                    "enabled": False,
                    "company_name": "SentraAI Entrance",
                    "logo_path": None,
                    "logo_data": None,  # Base64 encoded logo
                    "primary_color": "#0d6efd",  # Bootstrap primary blue
                    "secondary_color": "#6c757d",  # Bootstrap secondary gray
                    "accent_color": "#28a745",  # Bootstrap success green
                    "danger_color": "#dc3545",  # Bootstrap danger red
                    "warning_color": "#ffc107",  # Bootstrap warning yellow
                    "info_color": "#17a2b8",  # Bootstrap info cyan
                    "header_bg_color": "#343a40",  # Dark gray
                    "sidebar_bg_color": "#212529",  # Darker gray
                    "font_family": "Inter, sans-serif",
                    "custom_css": "",
                    "footer_text": "",
                    "login_page_title": "SentraAI Entrance Login",
                    "login_page_subtitle": "Bitte melden Sie sich an",
                    "dashboard_title": "Dashboard",
                    "favicon_path": None,
                    "favicon_data": None  # Base64 encoded favicon
                }
                self._save_config()
                log_system("Default white-label configuration created")
        except Exception as e:
            log_error(f"Error loading white-label configuration: {str(e)}")
            self.config = {"enabled": False}

    def _save_config(self) -> bool:
        """Save white-label configuration to the JSON file."""
        try:
            os.makedirs(os.path.dirname(WHITELABEL_FILE), exist_ok=True)
            with open(WHITELABEL_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
            log_system("White-label configuration saved successfully")
            return True
        except Exception as e:
            log_error(f"Error saving white-label configuration: {str(e)}")
            return False

    def get_config(self) -> Dict:
        """Get the current white-label configuration."""
        return self.config.copy()

    def update_config(self, updates: Dict) -> bool:
        """
        Update the white-label configuration.

        Args:
            updates: Dictionary with configuration updates

        Returns:
            True if successful, False otherwise
        """
        try:
            # Handle logo upload if present
            if 'logo_file' in updates:
                logo_data = updates.pop('logo_file')
                if logo_data:
                    # Convert to base64 for storage
                    self.config['logo_data'] = base64.b64encode(logo_data).decode('utf-8')
                    self.config['logo_path'] = None  # Clear file path when using data

            # Handle favicon upload if present
            if 'favicon_file' in updates:
                favicon_data = updates.pop('favicon_file')
                if favicon_data:
                    # Convert to base64 for storage
                    self.config['favicon_data'] = base64.b64encode(favicon_data).decode('utf-8')
                    self.config['favicon_path'] = None  # Clear file path when using data

            # Update other configuration
            self.config.update(updates)
            self._save_config()
            log_system("White-label configuration updated successfully")
            return True
        except Exception as e:
            log_error(f"Error updating white-label configuration: {str(e)}")
            return False

    def reset_to_defaults(self) -> bool:
        """
        Reset the white-label configuration to defaults.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.config = {
                "enabled": False,
                "company_name": "SentraAI Entrance",
                "logo_path": None,
                "logo_data": None,
                "primary_color": "#0d6efd",
                "secondary_color": "#6c757d",
                "accent_color": "#28a745",
                "danger_color": "#dc3545",
                "warning_color": "#ffc107",
                "info_color": "#17a2b8",
                "header_bg_color": "#343a40",
                "sidebar_bg_color": "#212529",
                "font_family": "Inter, sans-serif",
                "custom_css": "",
                "footer_text": "",
                "login_page_title": "SentraAI Entrance Login",
                "login_page_subtitle": "Bitte melden Sie sich an",
                "dashboard_title": "Dashboard",
                "favicon_path": None,
                "favicon_data": None
            }
            self._save_config()
            log_system("White-label configuration reset to defaults")
            return True
        except Exception as e:
            log_error(f"Error resetting white-label configuration: {str(e)}")
            return False

    def get_css_variables(self) -> str:
        """
        Generate CSS custom properties based on the configuration.

        Returns:
            CSS string with custom properties
        """
        if not self.config.get('enabled', False):
            return ""

        css_vars = """
        <style>
            :root {
                --primary-color: %(primary_color)s;
                --secondary-color: %(secondary_color)s;
                --accent-color: %(accent_color)s;
                --danger-color: %(danger_color)s;
                --warning-color: %(warning_color)s;
                --info-color: %(info_color)s;
                --header-bg-color: %(header_bg_color)s;
                --sidebar-bg-color: %(sidebar_bg_color)s;
                --font-family: %(font_family)s;
            }

            body {
                font-family: var(--font-family);
            }

            .btn-primary {
                background-color: var(--primary-color);
                border-color: var(--primary-color);
            }

            .btn-secondary {
                background-color: var(--secondary-color);
                border-color: var(--secondary-color);
            }

            .btn-success {
                background-color: var(--accent-color);
                border-color: var(--accent-color);
            }

            .btn-danger {
                background-color: var(--danger-color);
                border-color: var(--danger-color);
            }

            .btn-warning {
                background-color: var(--warning-color);
                border-color: var(--warning-color);
            }

            .btn-info {
                background-color: var(--info-color);
                border-color: var(--info-color);
            }

            .bg-primary {
                background-color: var(--primary-color) !important;
            }

            .text-primary {
                color: var(--primary-color) !important;
            }

            .topbar {
                background-color: var(--header-bg-color);
            }

            .sidebar {
                background: var(--sidebar-bg-color);
            }

            .sidebar-header {
                background: var(--header-bg-color);
            }

            .sidebar .nav-link:hover {
                background: var(--primary-color);
            }

            .sidebar .nav-item.active .nav-link {
                background: var(--primary-color);
            }

            %(custom_css)s
        </style>
        """ % {
            'primary_color': self.config.get('primary_color', '#0d6efd'),
            'secondary_color': self.config.get('secondary_color', '#6c757d'),
            'accent_color': self.config.get('accent_color', '#28a745'),
            'danger_color': self.config.get('danger_color', '#dc3545'),
            'warning_color': self.config.get('warning_color', '#ffc107'),
            'info_color': self.config.get('info_color', '#17a2b8'),
            'header_bg_color': self.config.get('header_bg_color', '#343a40'),
            'sidebar_bg_color': self.config.get('sidebar_bg_color', '#212529'),
            'font_family': self.config.get('font_family', 'Inter, sans-serif'),
            'custom_css': self.config.get('custom_css', '')
        }

        return css_vars

    def get_logo_url(self) -> Optional[str]:
        """
        Get the logo URL or base64 data URI.

        Returns:
            Logo URL or data URI, or None if no logo is configured
        """
        if self.config.get('logo_data'):
            return f"data:image/png;base64,{self.config['logo_data']}"
        elif self.config.get('logo_path'):
            return self.config['logo_path']
        return None

    def get_favicon_url(self) -> Optional[str]:
        """
        Get the favicon URL or base64 data URI.

        Returns:
            Favicon URL or data URI, or None if no favicon is configured
        """
        if self.config.get('favicon_data'):
            return f"data:image/x-icon;base64,{self.config['favicon_data']}"
        elif self.config.get('favicon_path'):
            return self.config['favicon_path']
        return None

# Create a singleton instance
whitelabel_manager = WhitelabelManager()