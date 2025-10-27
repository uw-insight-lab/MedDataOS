// WebSocket connection
let ws = null;

// Session management
let sessionId = localStorage.getItem('meddata_session_id') || null;
let isProcessing = false;

// DOM elements
const chatContainer = document.getElementById('chat-container');
const connectionStatus = document.getElementById('connection-status');
const connectionText = document.getElementById('connection-text');
const sendBtn = document.getElementById('send-btn');
const clearBtn = document.getElementById('clear-btn');
const messageInput = document.getElementById('message-input');

// Connect to WebSocket
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
        updateConnectionStatus(true);
        updateSendButton();
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected');
        updateConnectionStatus(false);
        updateSendButton();
        // Attempt to reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

// Handle WebSocket messages
function handleWebSocketMessage(data) {
    // Skip initial connection messages
    if (data.type === 'system' && data.message === 'Connected to MedDataOS Monitor') {
        return;
    }

    // Add detailed log entries below the current chat messages
    addLogEntry(data);

    // If this is an assistant message, check if processing is complete
    if (data.type === 'assistant') {
        isProcessing = false;
        updateSendButton();

        // Add assistant response to chat
        addChatMessage('assistant', data.message);
    }
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

// Update send button state
function updateSendButton() {
    const isConnected = ws && ws.readyState === WebSocket.OPEN;
    const hasMessage = messageInput.value.trim().length > 0;
    sendBtn.disabled = !isConnected || isProcessing || !hasMessage;
}

// Add chat message to UI
function addChatMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}`;

    const label = role === 'user' ? 'You' : 'MedDataOS';

    messageDiv.innerHTML = `
        <div class="message-header">${escapeHtml(label)}</div>
        <div class="message-bubble">
            <div class="message-content">${escapeHtml(content)}</div>
        </div>
    `;

    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

// Add detailed log entry (for WebSocket streaming logs)
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

    chatContainer.appendChild(logEntry);
    scrollToBottom();
}

// Scroll to bottom of chat
function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
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

// Clear chat
function clearChat() {
    chatContainer.innerHTML = '';
    // Clear session and start fresh
    sessionId = null;
    localStorage.removeItem('meddata_session_id');
}

// Send message
async function sendMessage() {
    const message = messageInput.value.trim();

    if (!message) {
        return;
    }

    // Disable input while processing
    isProcessing = true;
    updateSendButton();
    messageInput.disabled = true;

    // Add user message to chat immediately
    addChatMessage('user', message);

    // Clear input
    messageInput.value = '';

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: sessionId,
                message: message
            })
        });

        const result = await response.json();

        if (result.status === 'processing') {
            // Store session ID
            if (result.session_id) {
                sessionId = result.session_id;
                localStorage.setItem('meddata_session_id', sessionId);
            }
            // Response will come via WebSocket
        } else if (result.status === 'error') {
            alert(result.message || 'Failed to send message');
            isProcessing = false;
            updateSendButton();
        }
    } catch (error) {
        console.error('Error sending message:', error);
        alert('Failed to communicate with server');
        isProcessing = false;
        updateSendButton();
    } finally {
        messageInput.disabled = false;
        messageInput.focus();
    }
}

// Event listeners
sendBtn.addEventListener('click', sendMessage);
clearBtn.addEventListener('click', clearChat);

// Update send button when typing
messageInput.addEventListener('input', updateSendButton);

// Allow Enter key to send (with Shift+Enter for new line)
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn.disabled) {
            sendMessage();
        }
    }
});

// Initialize WebSocket connection
connectWebSocket();
