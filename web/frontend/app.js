// WebSocket connection
let ws = null;

// Session management
let sessionId = localStorage.getItem('meddata_session_id') || null;
let isProcessing = false;
let attachedFile = null;

// DOM elements
const chatContainer = document.getElementById('chat-container');
const connectionStatus = document.getElementById('connection-status');
const connectionText = document.getElementById('connection-text');
const sendBtn = document.getElementById('send-btn');
const clearBtn = document.getElementById('clear-btn');
const messageInput = document.getElementById('message-input');
const attachBtn = document.getElementById('attach-btn');
const fileInput = document.getElementById('file-input');
const fileAttachment = document.getElementById('file-attachment');
const fileName = document.getElementById('file-name');
const fileRemove = document.getElementById('file-remove');

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

    // Handle assistant messages - show as chat bubble only
    if (data.type === 'assistant') {
        isProcessing = false;
        updateSendButton();
        addChatMessage('assistant', data.message);
        return;
    }

    // Skip user messages - already shown as chat bubble when sent
    if (data.type === 'user') {
        return;
    }

    // Show only tool execution logs (tool_call, tool_result)
    // This shows the pipeline execution details without duplicating chat messages
    if (data.type === 'tool_call' || data.type === 'tool_result') {
        addLogEntry(data);
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
    attachBtn.disabled = !isConnected || isProcessing;
}

// Handle file selection
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Validate file type
    const fileNameLower = file.name.toLowerCase();
    if (!fileNameLower.endsWith('.csv') && !fileNameLower.endsWith('.xlsx')) {
        alert('Only CSV and Excel (.csv, .xlsx) files are allowed');
        fileInput.value = '';
        return;
    }

    attachedFile = file;
    fileName.textContent = file.name;
    fileAttachment.style.display = 'flex';
}

// Remove attached file
function removeFile() {
    attachedFile = null;
    fileInput.value = '';
    fileAttachment.style.display = 'none';
    fileName.textContent = '';
}

// Add chat message to UI
function addChatMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}`;

    const label = role === 'user' ? 'You' : 'MedDataOS';

    // Render markdown for assistant messages, plain text for user messages
    let messageContent;
    if (role === 'assistant') {
        // Parse markdown and sanitize for security
        const rawHtml = marked.parse(content);
        messageContent = DOMPurify.sanitize(rawHtml);
    } else {
        // User messages stay as plain text
        messageContent = escapeHtml(content);
    }

    messageDiv.innerHTML = `
        <div class="message-header">${escapeHtml(label)}</div>
        <div class="message-bubble">
            <div class="message-content">${messageContent}</div>
        </div>
    `;

    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

// Map tool names to friendly agent names
const agentNameMap = {
    'prepare_data_for_analysis': 'Preparation Agent',
    'prepare_analysis': 'Analysis Agent',
    'generate_analysis_report': 'Report Agent',
    'classify_chest_xray': 'Chest X-Ray Agent'
};

// Track the last agent that was called
let lastAgentName = '';

// Add detailed log entry (for WebSocket streaming logs)
function addLogEntry(data) {
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry ${data.type}`;

    const timestamp = formatTimestamp(data.timestamp);

    // Determine title based on type
    let title = '';
    let icon = '';

    if (data.type === 'tool_call') {
        // Extract tool name from header or message
        const toolName = data.header || data.message.split(':')[0] || '';
        const agentName = agentNameMap[toolName.trim()] || toolName;
        lastAgentName = agentName; // Track for matching with result
        icon = '🤖';
        title = `${icon} ${agentName}: Executing`;
    } else if (data.type === 'tool_result') {
        // Use the last agent name that was called
        icon = '✅';
        title = `${icon} ${lastAgentName}: Completed`;
    }

    logEntry.innerHTML = `
        <div class="log-header">
            <span class="log-title">${escapeHtml(title)}</span>
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
    // Clear attached file
    removeFile();
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
    attachBtn.disabled = true;

    // Build display message
    let displayMessage = message;
    if (attachedFile) {
        displayMessage += `\n\n📎 Attached: ${attachedFile.name}`;
    }

    // Add user message to chat immediately
    addChatMessage('user', displayMessage);

    // Clear input
    messageInput.value = '';

    try {
        // Prepare request body
        const formData = new FormData();
        formData.append('message', message);
        if (sessionId) {
            formData.append('session_id', sessionId);
        }
        if (attachedFile) {
            formData.append('file', attachedFile);
        }

        const response = await fetch('/api/chat', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.status === 'processing') {
            // Store session ID
            if (result.session_id) {
                sessionId = result.session_id;
                localStorage.setItem('meddata_session_id', sessionId);
            }
            // Clear attached file after successful send
            removeFile();
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
attachBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', handleFileSelect);
fileRemove.addEventListener('click', removeFile);

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
