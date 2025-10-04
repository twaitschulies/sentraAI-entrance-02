// Vereinfachte WebSocket-Simulation für Dashboard
// Direkt in Fallback-Modus, da WebSocket-Funktionalität entfernt wurde

class GuardWebSocket {
    constructor() {
        this.connected = false;
        this.fallbackMode = true;
        this.pollingActive = true;
        this.initializeFallback();
    }

    initializeFallback() {
        console.log('🚀 GuardWebSocket Fallback Mode gestartet');
        
        // Sofort Fallback-Status setzen
        setTimeout(() => {
            const wsStatus = document.getElementById('websocket-status');
            if (wsStatus) {
                wsStatus.className = 'badge bg-success';
                wsStatus.textContent = 'Live';
                wsStatus.title = 'Auto-Update aktiv (5s Intervall)';
            }
            
            // Zeige "Letztes Update" korrekt an
            this.updateTimestamp();
            
            // Erste vollständige Aktualisierung
            this.fullDashboardUpdate();
        }, 100);
        
        // Starte Fallback-Updates alle 5 Sekunden
        this.startFallbackUpdates();
    }

    startFallbackUpdates() {
        console.log('⏰ Starte Auto-Update Timer (5s Intervall)');
        setInterval(() => {
            if (this.pollingActive) {
                console.log('🔄 Auto-Update ausgeführt:', new Date().toLocaleTimeString());
                this.updateTimestamp();
                this.fullDashboardUpdate();
            }
        }, 5000);
    }

    updateTimestamp() {
        const lastUpdate = document.getElementById('last-update');
        if (lastUpdate) {
            const now = new Date();
            lastUpdate.textContent = now.toLocaleString('de-DE');
        }
    }

    fullDashboardUpdate() {
        console.log('📊 Starte vollständige Dashboard-Aktualisierung');
        
        // 1. Dashboard-Daten laden (System + NFC + Statistiken)
        this.updateDashboardData();
        
        // 2. Türstatus laden
        this.updateDoorStatus();
        
        // 3. Live-Scans laden
        this.checkForNewScans();
    }

    updateDashboardData() {
        fetch('/api/dashboard_data')
            .then(response => response.json())
            .then(result => {
                console.log('📡 Dashboard-Daten erhalten:', result);
                
                if (result.success && result.data) {
                    // System-Status aktualisieren
                    if (result.data.system) {
                        const system = result.data.system;
                        this.updateElement('cpu-usage', system.cpu_usage);
                        this.updateElement('ram-usage', system.ram_usage);
                        this.updateElement('system-uptime', system.uptime);
                        
                        console.log('💻 System-Status aktualisiert:', system);
                    }
                    
                    // NFC-Status aktualisieren
                    if (result.data.nfc) {
                        const nfcBadge = document.getElementById('nfc-status-badge');
                        
                        if (nfcBadge) {
                            nfcBadge.textContent = result.data.nfc.status;
                            nfcBadge.className = `badge badge-sm ${result.data.nfc.status === 'Bereit' ? 'bg-success' : 'bg-warning'}`;
                        }
                        
                        console.log('💳 NFC-Status aktualisiert:', result.data.nfc.status);
                    }
                    
                    // Statistiken aktualisieren
                    if (result.data.statistics) {
                        const stats = result.data.statistics;
                        this.updateElement('scans-today', stats.scans_today || 0);
                        this.updateElement('card-scans-today', stats.card_scans_today || 0);
                        this.updateElement('scans-30-days', stats.scans_30_days || 0);
                        this.updateElement('card-scans-30-days', stats.card_scans_30_days || 0);
                        
                        console.log('📈 Statistiken aktualisiert:', stats);
                    }
                }
            })
            .catch(error => {
                console.error('❌ Dashboard-Daten Fehler:', error);
                this.showOfflineStatus();
            });
    }

    updateDoorStatus() {
        fetch('/gpio_status')
            .then(response => response.json())
            .then(data => {
                const status = document.getElementById('dashboard-door-status');
                if (status) {
                    if (data.gpio_state) {
                        status.textContent = 'Geöffnet';
                        status.className = 'badge bg-success badge-sm';
                    } else {
                        status.textContent = 'Geschlossen';
                        status.className = 'badge bg-danger badge-sm';
                    }
                    console.log('🚪 Türstatus aktualisiert:', data.gpio_state ? 'Geöffnet' : 'Geschlossen');
                }
            })
            .catch(error => {
                console.error('❌ Türstatus Fehler:', error);
            });
    }

    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element && value !== undefined && value !== null) {
            element.textContent = value;
            
            // Kurze Highlight-Animation für Änderungen
            element.style.transition = 'background-color 0.3s ease';
            element.style.backgroundColor = '#d4edda';
            setTimeout(() => {
                element.style.backgroundColor = '';
            }, 300);
        }
    }

    showOfflineStatus() {
        const wsStatus = document.getElementById('websocket-status');
        if (wsStatus) {
            wsStatus.className = 'badge bg-danger';
            wsStatus.textContent = 'Offline';
            wsStatus.title = 'Verbindung unterbrochen';
        }
    }

    checkForNewScans() {
        console.log('🔍 Checking for new scans...');
        fetch('/api/recent_scans?limit=10')
            .then(response => response.json())
            .then(result => {
                console.log('📡 Scan API Response:', result);
                if (result.success && result.scans) {
                    console.log(`📊 Found ${result.scans.length} scans (${result.barcode_count || 0} barcode + ${result.nfc_count || 0} NFC)`);
                    this.updateLiveScansTable(result.scans);
                } else {
                    console.log('⚠️ No scans in response');
                }
            })
            .catch(error => {
                console.error('❌ Fehler beim Laden neuer Scans:', error);
            });
    }

    updateLiveScansTable(scans) {
        const nfcTableBody = document.getElementById('recent-nfc-scans-table');
        const barcodeTableBody = document.getElementById('recent-barcode-scans-table');

        if (!nfcTableBody) {
            console.error('❌ NFC Table Element nicht gefunden!');
        }
        if (!barcodeTableBody) {
            console.error('❌ Barcode Table Element nicht gefunden!');
        }

        console.log(`📝 Updating tables with ${scans.length} scans`);

        // Scans nach Typ trennen
        const nfcScans = [];
        const barcodeScans = [];

        scans.forEach(scan => {
            console.log(`Scan details: type=${scan.type}, pan=${scan.pan}, card_type=${scan.card_type}`);

            // Improved NFC scan detection - check 'type' field first
            if (scan.type === 'NFC' || scan.type === 'nfc') {
                nfcScans.push(scan);
            } else if (scan.pan || scan.card_type) {
                // Fallback: if it has pan or card_type, it's likely NFC
                nfcScans.push(scan);
            } else {
                barcodeScans.push(scan);
            }
        });

        console.log(`📊 Aufgeteilte Scans: ${nfcScans.length} NFC, ${barcodeScans.length} Barcode`);

        // Update NFC-Tabelle (if table exists)
        if (nfcTableBody) {
            this.updateSpecificTable(nfcTableBody, nfcScans.slice(0, 10), 'nfc');
        }

        // Update Barcode-Tabelle (if table exists and is visible)
        if (barcodeTableBody) {
            this.updateSpecificTable(barcodeTableBody, barcodeScans.slice(0, 10), 'barcode');
        }
    }

    updateSpecificTable(tableBody, scans, tableType) {
        // Always remove "Warte auf Scans" message when we have data
        const waitingRow = tableBody.querySelector('td[colspan="4"]');

        if (scans.length === 0) {
            console.log(`📭 No ${tableType} scans to display`);
            // If no scans and no waiting message, add "Keine Scans vorhanden" message
            if (!waitingRow && tableBody.children.length === 0) {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td colspan="4" class="text-center text-muted">
                        Keine ${tableType === 'nfc' ? 'NFC' : 'Barcode'}-Scans vorhanden
                    </td>
                `;
                tableBody.appendChild(row);
            }
            return;
        }

        // Remove waiting message if we have scans to show
        if (waitingRow) {
            console.log(`🗑️ Removing waiting message from ${tableType} table`);
            waitingRow.parentElement.remove();
        }
        
        // Zeige nur die neuesten Scans für diese Tabelle
        scans.forEach((scan, index) => {
            // Use pan_hash for NFC scans, timestamp+code for barcode scans to avoid duplicates
            const scanId = scan.pan_hash ? `nfc-${scan.pan_hash}` :
                          (scan.code ? `barcode-${scan.timestamp}-${scan.code}` :
                          (scan.id || scan.timestamp || `scan-${index}`));
            const existingRow = document.querySelector(`tr[data-scan-id="${scanId}"]`);
            
            if (!existingRow) {
                console.log(`➕ Adding new scan: ${scanId}`);
                const row = document.createElement('tr');
                row.setAttribute('data-scan-id', scanId);
                row.className = 'table-row-fade-in';
                
                const statusClass = this.getStatusClass(scan.status);
                
                // Zeitstempel kürzen - ensure HH:MM format
                let shortTime = 'N/A';
                if (scan.timestamp) {
                    // Handle both full timestamp and time-only formats
                    if (scan.timestamp.includes(' ')) {
                        // Full timestamp format: "YYYY-MM-DD HH:MM:SS"
                        shortTime = scan.timestamp.split(' ')[1]?.substring(0, 5) || scan.timestamp;
                    } else if (scan.timestamp.includes(':')) {
                        // Already time-only format
                        shortTime = scan.timestamp.substring(0, 5);
                    } else {
                        shortTime = scan.timestamp;
                    }
                }

                // Unterschiedliche HTML für NFC und Barcode Tabellen
                if (tableType === 'nfc') {
                    // PCI DSS COMPLIANT: Consistent masked PAN display
                    let maskedPanHTML = '<span class="masked-pan">';
                    if (scan.pan_last4) {
                        maskedPanHTML += '<span class="pan-mask">****</span><span class="pan-separator">-</span>' +
                                         '<span class="pan-visible">' + scan.pan_last4 + '</span>';
                    } else if (scan.pan && scan.pan.length > 4) {
                        const last4 = scan.pan.slice(-4);
                        maskedPanHTML += '<span class="pan-mask">****</span><span class="pan-separator">-</span>' +
                                         '<span class="pan-visible">' + last4 + '</span>';
                    } else if (scan.pan) {
                        maskedPanHTML += '<span class="pan-mask">****</span><span class="pan-separator">-</span>' +
                                         '<span class="pan-visible">' + scan.pan + '</span>';
                    } else {
                        maskedPanHTML += '<span class="pan-mask">****</span><span class="pan-separator">-</span>' +
                                         '<span class="pan-mask">****</span>';
                    }
                    maskedPanHTML += '</span>';

                    // Get the appropriate badge color for card type
                    const cardType = scan.card_type || scan.type || 'NFC';
                    let cardBadgeClass = 'bg-secondary';
                    if (cardType.includes('Mastercard')) {
                        cardBadgeClass = 'bg-warning';
                    } else if (cardType.includes('MIFARE')) {
                        cardBadgeClass = 'bg-info';
                    } else if (cardType.includes('Girocard')) {
                        cardBadgeClass = 'bg-primary';
                    } else if (cardType.includes('Sparkasse')) {
                        cardBadgeClass = 'bg-danger';
                    } else if (cardType.includes('Visa')) {
                        cardBadgeClass = 'bg-primary';
                    }

                    row.innerHTML = `
                        <td class="small">${shortTime}</td>
                        <td><span class="badge badge-sm ${cardBadgeClass}">${cardType}</span></td>
                        <td class="small">${maskedPanHTML}</td>
                        <td><span class="badge badge-sm ${this.getStatusClass(this.getDisplayStatus(scan.status))}">${this.getDisplayStatus(scan.status)}</span></td>
                    `;
                } else {
                    // Barcode Tabelle
                    let displayCode = scan.code || scan.barcode || 'Unbekannt';
                    if (displayCode.length > 20) {
                        displayCode = displayCode.substring(0, 17) + '...';
                    }
                    
                    row.innerHTML = `
                        <td class="small">${shortTime}</td>
                        <td><span class="badge badge-sm bg-info">${scan.type || 'Barcode'}</span></td>
                        <td class="small">${displayCode}</td>
                        <td><span class="badge badge-sm ${this.getStatusClass(this.getDisplayStatus(scan.status))}">${this.getDisplayStatus(scan.status)}</span></td>
                    `;
                }
                
                // Füge neue Scans oben ein
                tableBody.insertBefore(row, tableBody.firstChild);
                
                // Update Live-Scan-Counter  
                const counter = document.getElementById('live-scans-count');
                if (counter) {
                    const currentCount = parseInt(counter.textContent.match(/\d+/)?.[0] || 0);
                    counter.textContent = `${currentCount + 1} Live-Scans`;
                    console.log(`📊 Updated counter to: ${currentCount + 1}`);
                }
            } else {
                console.log(`⏭️ Scan already exists: ${scanId}`);
            }
        });

        // Begrenze auf maximal 10 Zeilen
        const allRows = tableBody.querySelectorAll('tr');
        if (allRows.length > 10) {
            console.log(`✂️ Trimming table to 10 rows (was ${allRows.length})`);
            for (let i = 10; i < allRows.length; i++) {
                allRows[i].remove();
            }
        }
    }

    getStatusClass(status) {
        switch (status) {
            case 'Permanent': return 'bg-success';
            case 'Temporär': return 'bg-success';
            case 'Gesperrt': return 'bg-danger';
            case 'Erfolgreich': return 'bg-success';
            case 'Gültig': return 'bg-success';
            case 'Ungültig': return 'bg-danger';
            case 'Valid': return 'bg-success';
            case 'Invalid': return 'bg-danger';
            case 'Fehlgeschlagen': return 'bg-danger';
            default: return 'bg-danger';
        }
    }

    getDisplayStatus(status) {
        // Convert raw status values to human-readable "Gültig" or "Ungültig"
        switch (status) {
            case 'Permanent':
            case 'Temporär':
            case 'Erfolgreich':
            case true:
            case 'true':
            case 'success':
                return 'Gültig';
            case 'Gesperrt':
            case 'Fehlgeschlagen':
            case false:
            case 'false':
            case 'error':
            case 'invalid':
                return 'Ungültig';
            default:
                // If status contains "Verweigert" or similar negative keywords
                if (typeof status === 'string' &&
                    (status.toLowerCase().includes('verweigert') ||
                     status.toLowerCase().includes('fehlgeschlagen') ||
                     status.toLowerCase().includes('error'))) {
                    return 'Ungültig';
                }
                // If it's a positive status
                if (typeof status === 'string' &&
                    (status.toLowerCase().includes('permanent') ||
                     status.toLowerCase().includes('temporär') ||
                     status.toLowerCase().includes('erlaubt') ||
                     status.toLowerCase().includes('erfolgreich'))) {
                    return 'Gültig';
                }
                return 'Ungültig';
        }
    }

    // Live-Polling steuern
    togglePolling() {
        this.pollingActive = !this.pollingActive;
        const wsStatus = document.getElementById('websocket-status');
        
        if (this.pollingActive) {
            wsStatus.className = 'badge bg-success';
            wsStatus.textContent = 'Live';
            console.log('▶️ Auto-Update wieder aktiviert');
        } else {
            wsStatus.className = 'badge bg-warning';
            wsStatus.textContent = 'Pausiert';
            console.log('⏸️ Auto-Update pausiert');
        }
    }

    // Dummy-Methoden für Kompatibilität
    handleNewScan(data) {
        // Wird vom Dashboard überschrieben
    }
}

// Global verfügbar machen
window.GuardWebSocket = GuardWebSocket;

// Automatisch initialisieren
document.addEventListener('DOMContentLoaded', function() {
    console.log('🎯 Initialisiere GuardWebSocket...');
    window.guardWS = new GuardWebSocket();
    
    // Toggle-Funktion global verfügbar machen
    window.toggleLiveScans = function() {
        if (window.guardWS) {
            window.guardWS.togglePolling();
        }
    };
}); 