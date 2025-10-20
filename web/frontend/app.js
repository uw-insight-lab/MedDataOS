// WebSocket connection
let ws = null;

// DOM elements
const logsContainer = document.getElementById('logs-container');
const connectionStatus = document.getElementById('connection-status');
const connectionText = document.getElementById('connection-text');
const executeBtn = document.getElementById('execute-btn');
const clearBtn = document.getElementById('clear-btn');
const queryInput = document.getElementById('query-input');

// Connect to WebSocket
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
        updateConnectionStatus(true);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        // Only add actual log entries, skip system connection messages
        if (data.type !== 'system' || data.message.includes('Query') || data.message.includes('Response')) {
            addLogEntry(data);
        }
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected');
        updateConnectionStatus(false);
        // Attempt to reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

// Update connection status UI
function updateConnectionStatus(connected) {
    if (connected) {
        connectionStatus.className = 'status connected';
        connectionText.textContent = 'Connected';
    } else {
        connectionStatus.className = 'status disconnected';
        connectionText.textContent = 'Disconnected';
    }
}

// Add log entry to the UI
function addLogEntry(data) {
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry ${data.type}`;

    const timestamp = formatTimestamp(data.timestamp);
    const header = data.header || data.type.replace('_', ' ').toUpperCase();

    logEntry.innerHTML = `
        <div class="log-header">
            <span class="log-title">${escapeHtml(header)}</span>
            <span class="log-timestamp">${timestamp}</span>
        </div>
        <div class="log-message">${escapeHtml(data.message)}</div>
    `;

    logsContainer.appendChild(logEntry);

    // Auto-scroll to bottom
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

// Format timestamp
function formatTimestamp(isoString) {
    if (!isoString) return '--:--:--';
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', { hour12: false });
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Clear logs
function clearLogs() {
    logsContainer.innerHTML = '';
}

// Execute analysis
async function executeAnalysis() {
    const query = queryInput.value.trim();

    if (!query) {
        alert('Please enter a task description');
        return;
    }

    executeBtn.disabled = true;
    const originalText = executeBtn.querySelector('.btn-text').textContent;
    executeBtn.querySelector('.btn-text').textContent = 'Executing...';

    try {
        const response = await fetch('/api/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ query })
        });

        const result = await response.json();

        if (result.status === 'started') {
            // Query will be logged via WebSocket
            queryInput.value = '';
        } else if (result.status === 'error') {
            alert(result.message || 'Failed to start analysis');
        }
    } catch (error) {
        console.error('Error starting analysis:', error);
        alert('Failed to communicate with server');
    } finally {
        setTimeout(() => {
            executeBtn.disabled = false;
            executeBtn.querySelector('.btn-text').textContent = originalText;
        }, 2000);
    }
}

// Event listeners
executeBtn.addEventListener('click', executeAnalysis);
clearBtn.addEventListener('click', clearLogs);

// Allow Enter key to submit (with Shift+Enter for new line)
queryInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        executeAnalysis();
    }
});

// Initialize WebSocket connection
connectWebSocket();
