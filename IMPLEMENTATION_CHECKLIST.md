# 📋 Implementation Checklist for New Features

## 🔴 CRITICAL: Session Role Handling Pattern

### ⚠️ Known Issue & Solution
**Problem:** New admin features often aren't visible because templates check for `session['role']` at the root level, but the role might be nested inside `session['user']['role']`.

**Solution:** Always ensure the role is available at BOTH locations for backward compatibility.

---

## ✅ Standard Checklist for New Admin Features

### 1. **Backend Route Implementation**
- [ ] Route uses `@admin_required` decorator
- [ ] Alternative: Route uses `@permission_required('permission_name')` for granular control
- [ ] Route is registered in the blueprint
- [ ] Error handling is implemented

### 2. **Session Handling in Login Route**
```python
# REQUIRED: Set role at root level for template access
if user:
    session['user'] = user
    session['role'] = user.get('role', 'user')  # CRITICAL LINE
    session['username'] = username  # For convenience
    session.permanent = True
```

### 3. **Template Navigation Items**
```html
<!-- CORRECT: Check session.role (NOT session.user.role) -->
{% if session.role == 'admin' %}
<li class="nav-item{% if request.endpoint == 'routes.your_route' %} active{% endif %}">
    <a href="{{ url_for('routes.your_route') }}" class="nav-link">
        <i class="fas fa-your-icon"></i>
        <span>Your Feature</span>
    </a>
</li>
{% endif %}
```

### 4. **Template Access Control**
```html
<!-- In your feature template -->
{% if session.role != 'admin' %}
    <div class="alert alert-danger">Zugriff verweigert</div>
{% else %}
    <!-- Your feature content -->
{% endif %}
```

### 5. **Consistent Session Variable Usage**
- ✅ **USE:** `session.role` in templates
- ✅ **USE:** `session['role']` in Python code
- ❌ **DON'T USE:** `session.user.role` in templates
- ❌ **DON'T USE:** `session.get('user_role')` anywhere

---

## 🧪 Testing Checklist

### Before Committing:
- [ ] Test login with admin/admin credentials
- [ ] Verify menu item appears in sidebar
- [ ] Check that the route is accessible when logged in as admin
- [ ] Test that non-admin users get redirected
- [ ] Check browser console for JavaScript errors
- [ ] Verify no 404 or 500 errors

### After Git Pull on Production:
- [ ] Restart the service: `sudo systemctl restart qrverification`
- [ ] Clear browser cache
- [ ] Test all three core features remain accessible:
  - [ ] `/users` (Benutzerverwaltung)
  - [ ] `/opening_hours` (Öffnungszeiten)
  - [ ] `/whitelabel` (White-Label Configuration)
- [ ] Verify new feature is visible and functional

---

## 🔍 Debugging Session Issues

### Quick Debug Commands:
```python
# Add to any route to debug session:
import logging
logging.info(f"Session contents: {dict(session)}")
logging.info(f"Session role: {session.get('role')}")
logging.info(f"User role: {session.get('user', {}).get('role')}")
```

### Common Symptoms & Fixes:

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Menu items not visible | `session['role']` not set at root | Add `session['role'] = user.get('role')` in login |
| 403/Permission denied | Wrong decorator used | Use `@admin_required` or fix role check |
| Template error | Checking wrong session variable | Use `session.role` not `session.user.role` |
| Feature works locally but not in production | Session not persisting | Check `session.permanent = True` |

---

## 📝 Example Implementation

### New Feature: System Logs Viewer

1. **Route** (`app/routes.py`):
```python
@bp.route("/system_logs")
@admin_required
def system_logs():
    logs = get_system_logs()
    return render_template('system_logs.html', logs=logs)
```

2. **Navigation** (`app/templates/base.html`):
```html
{% if session.role == 'admin' %}
<li class="nav-item{% if request.endpoint == 'routes.system_logs' %} active{% endif %}">
    <a href="{{ url_for('routes.system_logs') }}" class="nav-link">
        <i class="fas fa-file-alt"></i>
        <span>System Logs</span>
    </a>
</li>
{% endif %}
```

3. **Template** (`app/templates/system_logs.html`):
```html
{% extends "base.html" %}
{% block title %}System Logs{% endblock %}
{% block content %}
<!-- Your content here -->
{% endblock %}
```

---

## ⚡ Quick Reference

### Files to Check/Update:
1. `app/routes.py` - Route definitions and session handling
2. `app/templates/base.html` - Navigation menu items
3. `app/auth.py` - Authentication helpers (use `session.get('role')`)
4. `app/models/user.py` - User role definitions

### Critical Lines to Verify:
```bash
# Check session role setting in login:
grep -n "session\['role'\]" app/routes.py

# Check template role checks:
grep -n "session.role" app/templates/*.html

# Find inconsistent patterns:
grep -n "session.get('user_role')" app/**/*
grep -n "session.user.role" app/templates/*.html
```

---

## 🚀 Deployment Commands

```bash
# On development machine:
git add .
git commit -m "feat: Add new admin feature with proper session handling"
git push origin test

# On Raspberry Pi:
cd /path/to/project
git pull origin test
sudo systemctl restart qrverification
sudo journalctl -u qrverification -f  # Monitor logs
```

---

## ⚠️ REMEMBER
**The #1 cause of "feature not visible" issues is session role misconfiguration.**
Always set `session['role']` at the root level in the login route!