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
const demoBtn = document.getElementById('demo-btn');
const messageInput = document.getElementById('message-input');
const attachBtn = document.getElementById('attach-btn');
const fileInput = document.getElementById('file-input');
const fileAttachment = document.getElementById('file-attachment');
const fileName = document.getElementById('file-name');
const fileRemove = document.getElementById('file-remove');
const citationPopup = document.getElementById('citation-popup');

// Demo dialog data
const DEMO_DIALOG = {
    user: "Patient P0001 is a 58-year-old male presenting to the clinic today. He has been complaining of chest discomfort. I have uploaded all available patient data. Can you give me a full clinical summary and flag any concerns?",
    assistant: {
        response: "**Clinical Summary — Patient P0001**\n\nThe patient presents with a 2–3 week history of exertional, pressure-like chest discomfort (4/10), resolving within 5 minutes of rest, accompanied by mild dyspnea on exertion and increased fatigue [cite:1]. There is no rest pain, palpitations, or syncope reported [cite:1].\n\nThe chest radiograph is clear with no acute cardiopulmonary findings and a normal cardiac silhouette [cite:2]. However, the ECG shows a sinus rhythm with subtle ST changes in the lateral leads [cite:3], and auscultation reveals an S4 gallop with a soft systolic murmur [cite:4], raising concern for impaired ventricular compliance. Echocardiogram confirms mildly reduced left ventricular function with regional wall motion abnormalities in the lateral wall [cite:5].\n\n⚠️ **Critical flag — Electrolytes:** Potassium has exceeded 5.5 mmol/L on three separate occasions over the past 4 months, with a peak of 6.2 mmol/L in late December [cite:6]. This is a significant safety concern given the patient is currently on Lisinopril 20mg — an ACE inhibitor known to elevate potassium [cite:7]. Immediate review of ACE inhibitor dosing is recommended.\n\n**Current medications** include Lisinopril 20mg and Amlodipine 5mg for hypertension, Atorvastatin 20mg, Aspirin 81mg for ASCVD prevention, Metformin and Semaglutide for Type 2 Diabetes, and Albuterol inhaler PRN for asthma [cite:7].\n\n**Assessment:** The clinical picture is consistent with stable exertional angina in the context of known cardiovascular risk factors (hypertension, hyperlipidemia, Type 2 diabetes). The lateral wall motion abnormality on echo may indicate underlying coronary artery disease. The recurrent hyperkalemia on ACE inhibitor therapy requires urgent attention.",
        citations: [
            { id: "1", agent: "clinical_notes",  file: "clinical-notes.txt",     web_path: "/multimodal-data/clinical-notes.txt",     summary: "58-year-old male with 2–3 week history of exertional chest pressure and dyspnea" },
            { id: "2", agent: "chest_xray",       file: "chest-x-ray.png",        web_path: "/multimodal-data/chest-x-ray.png",        summary: "No acute cardiopulmonary abnormality, normal cardiac silhouette" },
            { id: "3", agent: "ecg",              file: "ecg.svg",                web_path: "/multimodal-data/ecg.svg",                summary: "Sinus rhythm, ST changes in lateral leads V4–V6" },
            { id: "4", agent: "heart_sounds",     file: "heart-sounds.wav",       web_path: "/multimodal-data/heart-sounds.wav",       summary: "S4 gallop present, grade 2/6 systolic murmur" },
            { id: "5", agent: "echo",             file: "echocardiogram.mp4",     web_path: "/multimodal-data/echocardiogram.mp4",     summary: "Mildly reduced LV ejection fraction, lateral wall motion abnormality" },
            { id: "6", agent: "lab_results",      file: "hl7-v2.png",             web_path: "/multimodal-data/hl7-v2.png",             summary: "Recurrent hyperkalemia: peaks at 5.9, 6.2, 5.8 mmol/L over Oct 2025–Jan 2026" },
            { id: "7", agent: "medication",       file: "medication-history.csv", web_path: "/multimodal-data/medication-history.csv", summary: "Active medications include Lisinopril 20mg — ACE inhibitor contributing to elevated potassium" }
        ]
    }
};

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

// Replace [cite:X] tokens with hoverable <sup> badges
function renderWithCitations(html, citations) {
    const citationMap = {};
    citations.forEach(c => { citationMap[c.id] = c; });

    return html.replace(/\[cite:(\w+)\]/g, (match, id) => {
        const citation = citationMap[id];
        if (!citation) return match;
        const data = encodeURIComponent(JSON.stringify(citation));
        return `<sup class="citation" data-citation="${data}">${id}</sup>`;
    });
}

// Derive modality type from file extension
function getCitationType(file) {
    const ext = file.split('.').pop().toLowerCase();
    return { png: 'image', jpg: 'image', jpeg: 'image', svg: 'image',
             csv: 'csv', txt: 'text', mp4: 'video', wav: 'audio' }[ext] || 'text';
}

// Parse CSV text into an HTML table (first maxRows rows, first maxCols columns)
function csvToHTML(csv, maxRows = 100, maxCols = 5) {
    const lines = csv.trim().split('\n').filter(l => l.trim());
    const allHeaders = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
    const headers = allHeaders.slice(0, maxCols);
    const truncated = allHeaders.length > maxCols;

    let html = '<div class="card-table-wrap"><table class="card-table"><thead><tr>';
    headers.forEach(h => html += `<th>${escapeHtml(h)}</th>`);
    if (truncated) html += `<th class="dim">+${allHeaders.length - maxCols}</th>`;
    html += '</tr></thead><tbody>';

    lines.slice(1, maxRows + 1).forEach(line => {
        const cells = line.split(',').map(c => c.trim().replace(/^"|"$/g, ''));
        html += '<tr>';
        cells.slice(0, maxCols).forEach(cell => html += `<td>${escapeHtml(cell)}</td>`);
        if (truncated) html += '<td class="dim">…</td>';
        html += '</tr>';
    });
    html += '</tbody></table></div>';
    return html;
}

// Position popup near anchor, flip up if near bottom of screen
function positionPopup(anchor) {
    const rect = anchor.getBoundingClientRect();
    const h = citationPopup.offsetHeight;
    const top = (window.innerHeight - rect.bottom > h + 12)
        ? rect.bottom + 8
        : rect.top - h - 8;
    citationPopup.style.left = `${Math.min(rect.left, window.innerWidth - 360)}px`;
    citationPopup.style.top = `${Math.max(8, top)}px`;
}

let hideTimeout = null;

async function showCitationPopup(anchor, citation) {
    clearTimeout(hideTimeout);

    const type = getCitationType(citation.file);
    const agentLabel = escapeHtml(citation.agent.replace(/_/g, ' '));
    const fileLabel = escapeHtml(citation.file);

    // Build initial content (immediate for media, loading state for text/csv)
    let contentHTML = '';
    if (type === 'image') {
        const isSvg = citation.file.endsWith('.svg');
        contentHTML = `<img class="card-image${isSvg ? ' card-image-svg' : ''}" src="${citation.web_path}" alt="${fileLabel}">`;
    } else if (type === 'video') {
        contentHTML = `<video class="card-video" src="${citation.web_path}" controls></video>`;
    } else if (type === 'audio') {
        contentHTML = `<div class="card-audio-wrap"><audio class="card-audio" src="${citation.web_path}" controls></audio></div>`;
    } else {
        contentHTML = `<div class="card-loading">Loading…</div>`;
    }

    citationPopup.innerHTML = `
        <div class="card-header">
            <span class="card-agent">${agentLabel}</span>
            <span class="card-file">${fileLabel}</span>
        </div>
        <div class="card-content" id="card-content-inner">${contentHTML}</div>
        <div class="card-summary">${escapeHtml(citation.summary)}</div>
    `;

    citationPopup.style.display = 'block';
    positionPopup(anchor);

    // Fetch and render text-based content
    if (type === 'csv' || type === 'text') {
        try {
            const text = await fetch(citation.web_path).then(r => r.text());
            const inner = document.getElementById('card-content-inner');
            if (inner) {
                inner.innerHTML = type === 'csv'
                    ? csvToHTML(text)
                    : `<div class="card-text">${escapeHtml(text.slice(0, 600))}${text.length > 600 ? '…' : ''}</div>`;
                positionPopup(anchor);
            }
        } catch {
            const inner = document.getElementById('card-content-inner');
            if (inner) inner.innerHTML = `<div class="card-text card-error">Could not load content.</div>`;
        }
    }
}

// Add chat message to UI
function addChatMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}`;

    const label = role === 'user' ? 'You' : 'MedDataOS';

    // Render markdown for assistant messages, plain text for user messages
    let messageContent;
    if (role === 'assistant') {
        // Detect citation JSON format {response, citations}
        let responseText = content;
        let citations = [];
        try {
            const parsed = JSON.parse(content);
            if (parsed.response && parsed.citations) {
                responseText = parsed.response;
                citations = parsed.citations;
            }
        } catch (e) { /* plain text, use as-is */ }

        const rawHtml = marked.parse(responseText);
        const safeHtml = DOMPurify.sanitize(rawHtml);
        messageContent = citations.length > 0 ? renderWithCitations(safeHtml, citations) : safeHtml;
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

// Load hardcoded demo dialog
function loadDemo() {
    addChatMessage('user', DEMO_DIALOG.user);
    addChatMessage('assistant', JSON.stringify(DEMO_DIALOG.assistant));
}

// Citation hover — event delegation on chat container
chatContainer.addEventListener('mouseover', (e) => {
    const target = e.target.closest('.citation');
    if (!target) return;
    const citation = JSON.parse(decodeURIComponent(target.dataset.citation));
    showCitationPopup(target, citation);
});

chatContainer.addEventListener('mouseout', (e) => {
    if (!e.target.closest('.citation')) return;
    hideTimeout = setTimeout(() => { citationPopup.style.display = 'none'; }, 150);
});

// Keep card open when mouse moves onto it (needed for audio/video interaction)
citationPopup.addEventListener('mouseenter', () => clearTimeout(hideTimeout));
citationPopup.addEventListener('mouseleave', () => { citationPopup.style.display = 'none'; });

// Event listeners
sendBtn.addEventListener('click', sendMessage);
clearBtn.addEventListener('click', clearChat);
demoBtn.addEventListener('click', loadDemo);
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
