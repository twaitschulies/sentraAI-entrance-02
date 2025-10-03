# Barcode Visibility Synchronization Feature

## Overview
This feature provides synchronized visibility control for all barcode/QR-related UI elements across the dashboard. When the sentrasupport user disables QR functionality, all related UI elements are consistently hidden system-wide.

## Implementation Details

### 1. Settings Control (sentrasupport only)
- **Location**: Settings > Door Settings
- **Control**: "Barcode-Funktionalität aktiviert" checkbox
- **Access**: Only visible to users logged in as 'sentrasupport'
- **File**: `app/templates/settings.html` (lines 100-118)

### 2. Dashboard Synchronization
- **Barcode Column**: Wrapped in `{% if barcode_visibility_enabled %}` conditional
- **NFC Column Width**: Dynamically adjusts between col-md-6 (when barcodes visible) and col-md-12 (when hidden)
- **File**: `app/templates/dashboard.html` (lines 183, 209-234)

### 3. Navigation Menu
- **Barcodes Link**: Hidden when barcode visibility is disabled
- **File**: `app/templates/base.html` (line 331)

### 4. Global Availability
- **Context Processor**: Makes `barcode_visibility_enabled` available to all templates
- **File**: `app/routes.py` (lines 31-34)

## Configuration

The visibility setting is stored in `config.json` at the root directory:

```json
{
  "barcode_visibility_enabled": true  // or false
}
```

Default value: `true` (barcode features are visible)

## Testing

### Automated Tests
Run the test script to verify implementation:

```bash
python3 test_barcode_visibility_sync.py
```

This tests:
- Template conditionals are properly implemented
- Context processor provides global availability
- Column width responsiveness

### Interactive Testing
Use the toggle script to test visibility changes:

```bash
python3 test_visibility_toggle.py
```

This allows you to:
- Toggle the visibility setting
- View expected UI changes
- Verify configuration state

### Manual Testing Steps

1. **Login as sentrasupport**
   - Username: sentrasupport
   - Navigate to Settings > Door Settings

2. **Toggle Visibility**
   - Find "Barcode-Funktionalität aktiviert" checkbox
   - Uncheck to hide barcode features
   - Save settings

3. **Verify Dashboard**
   - Navigate to Dashboard
   - With visibility OFF: Only NFC column visible (full width)
   - With visibility ON: Both NFC and Barcode columns visible (half width each)

4. **Verify Navigation**
   - Check sidebar menu
   - "Barcodes" link should appear/disappear based on setting

5. **Verify Settings**
   - "Allow All Barcodes" option should be hidden when visibility is OFF

## UI Behavior Summary

### When `barcode_visibility_enabled = true`:
- ✅ Dashboard shows both NFC (col-md-6) and Barcode (col-md-6) columns
- ✅ Navigation menu shows "Barcodes" link
- ✅ Settings shows "Allow All Barcodes" option
- ✅ All barcode-related API endpoints are active

### When `barcode_visibility_enabled = false`:
- ❌ Dashboard hides Barcode column
- ✅ Dashboard shows NFC column at full width (col-md-12)
- ❌ Navigation menu hides "Barcodes" link
- ❌ Settings hides "Allow All Barcodes" option
- ❌ Barcode-related API endpoints return 403 Forbidden

## Files Modified

1. **app/templates/dashboard.html**
   - Added conditional visibility for barcode column
   - Made NFC column width responsive

2. **Test Files Created**
   - `test_barcode_visibility_sync.py` - Automated testing
   - `test_visibility_toggle.py` - Interactive testing
   - `BARCODE_VISIBILITY_SYNC.md` - This documentation

## Notes

- Only the 'sentrasupport' user can control this setting
- Changes require a page refresh to take effect
- The setting persists across application restarts
- Default behavior shows all barcode features (backward compatible)