// WebSocket connection
let ws = null;

// Session management
let sessionId = localStorage.getItem('meddata_session_id') || null;
let isProcessing = false;
let attachedFile = null;

// Sidebar state
let activePatientId = null;
let activeConversationId = null;
let patients = [];
let sidebarOpen = true;

// Insights panel state
let insightsOpen = false;
let patientPins = {};    // patient_id -> [{pin_id, citation}]
let modalCitation = null; // citation currently shown in modal
let currentModalPin = null; // full pin object for modal (or null if not pinned)
let lastUserQuery = '';     // last query text captured before sending

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
const citationPopup = document.getElementById('citation-popup');
const sidebarEl = document.getElementById('sidebar');
const sidebarContent = document.getElementById('sidebar-content');
const sidebarToggle = document.getElementById('sidebar-toggle');
const activePatientLabel = document.getElementById('active-patient-label');
const insightsPanel = document.getElementById('insights-panel');
const insightsContent = document.getElementById('insights-content');
const insightsToggle = document.getElementById('insights-toggle');
const modalPin = document.getElementById('modal-pin');
const modalAnnotationText = document.getElementById('modal-annotation-text');
const modalAnnotationTags = document.getElementById('modal-annotation-tags');
const modalInfoBtn = document.getElementById('modal-info-btn');
const modalAgentInfo = document.getElementById('modal-agent-info');
const modalProvenance = document.getElementById('modal-provenance');

// ─── Sidebar: Load Patients ─────────────────────────────────
async function loadPatients() {
    try {
        const res = await fetch('/api/patients');
        patients = await res.json();
        renderPatientList();

        // Auto-expand P0001 and load first conversation
        const firstPatient = document.querySelector('.sidebar-patient[data-patient-id="P0001"]');
        if (firstPatient) {
            await togglePatient(firstPatient);
            // Select the first conversation if one exists
            const firstConvo = firstPatient.querySelector('.conversation-item');
            if (firstConvo) {
                await switchConversation(firstConvo.dataset.patientId, firstConvo.dataset.sessionId);
            }
        }
    } catch (e) {
        console.error('Failed to load patients:', e);
    }
}

// ─── Patient Tooltip ────────────────────────────────────────
const patientTooltip = document.createElement('div');
patientTooltip.className = 'patient-tooltip';
document.body.appendChild(patientTooltip);
const patientDataMap = {};  // id -> full patient object
let patientTooltipShowTimer = null;
let patientTooltipHideTimer = null;

function showPatientTooltip(headerEl, patient) {
    clearTimeout(patientTooltipHideTimer);
    patientTooltipShowTimer = setTimeout(() => {
        // Build content
        const conditionsHTML = patient.conditions.length
            ? patient.conditions.map(c => `<span class="patient-tooltip-chip">${escapeHtml(c)}</span>`).join('')
            : '<span class="patient-tooltip-none">None recorded</span>';
        const allergiesHTML = patient.allergies.length
            ? patient.allergies.map(a => `<span class="patient-tooltip-chip allergy">${escapeHtml(a)}</span>`).join('')
            : '<span class="patient-tooltip-none">No known allergies</span>';
        const modsHTML = patient.modalities.map(m => `<span class="patient-tooltip-mod">${escapeHtml(m)}</span>`).join('');

        patientTooltip.innerHTML = `
            <div class="patient-tooltip-header">
                <span class="patient-tooltip-name">${escapeHtml(patient.name)}</span>
                <span class="patient-tooltip-demo">${patient.age} · ${patient.sex}${patient.blood_type ? ' · ' + patient.blood_type : ''}</span>
            </div>
            <div class="patient-tooltip-section">
                <span class="patient-tooltip-label">Conditions</span>
                <div class="patient-tooltip-chips">${conditionsHTML}</div>
            </div>
            <div class="patient-tooltip-section">
                <span class="patient-tooltip-label">Allergies</span>
                <div class="patient-tooltip-chips">${allergiesHTML}</div>
            </div>
            ${modsHTML ? `<div class="patient-tooltip-section">
                <span class="patient-tooltip-label">Data</span>
                <div class="patient-tooltip-modalities">${modsHTML}</div>
            </div>` : ''}
        `;

        // Position to right of sidebar
        const rect = headerEl.getBoundingClientRect();
        const sidebarRect = sidebarEl.getBoundingClientRect();
        let top = rect.top;
        let left = sidebarRect.right + 8;

        // Ensure it doesn't overflow the bottom of the viewport
        patientTooltip.classList.add('visible');
        const tooltipHeight = patientTooltip.offsetHeight;
        if (top + tooltipHeight > window.innerHeight - 12) {
            top = window.innerHeight - tooltipHeight - 12;
        }
        if (top < 12) top = 12;

        patientTooltip.style.top = top + 'px';
        patientTooltip.style.left = left + 'px';
    }, 200);
}

function hidePatientTooltip() {
    clearTimeout(patientTooltipShowTimer);
    patientTooltipHideTimer = setTimeout(() => {
        patientTooltip.classList.remove('visible');
    }, 150);
}

function renderPatientList() {
    sidebarContent.innerHTML = '';
    patients.forEach(p => {
        patientDataMap[p.id] = p;
        const div = document.createElement('div');
        div.className = 'sidebar-patient';
        div.dataset.patientId = p.id;
        div.dataset.patientName = p.name;

        div.innerHTML = `
            <div class="sidebar-patient-header">
                <span class="sidebar-patient-arrow">▶</span>
                <span class="sidebar-patient-name">${escapeHtml(p.name)}</span>
                <span class="sidebar-patient-meta">${p.age}, ${p.sex}</span>
            </div>
            <div class="sidebar-patient-body">
                <div class="conversation-list"></div>
                <button class="btn-new-conversation" data-patient-id="${p.id}">+ New</button>
            </div>
        `;

        // Tooltip hover handlers
        const header = div.querySelector('.sidebar-patient-header');
        header.addEventListener('mouseenter', () => showPatientTooltip(header, p));
        header.addEventListener('mouseleave', hidePatientTooltip);

        sidebarContent.appendChild(div);
    });
}

// Keep tooltip open when hovering over it
patientTooltip.addEventListener('mouseenter', () => clearTimeout(patientTooltipHideTimer));
patientTooltip.addEventListener('mouseleave', hidePatientTooltip);

// ─── Sidebar: Toggle ────────────────────────────────────────
function toggleSidebar() {
    sidebarOpen = !sidebarOpen;
    sidebarEl.classList.toggle('collapsed', !sidebarOpen);
}

// ─── Insights Panel ─────────────────────────────────────────
function toggleInsights() {
    insightsOpen = !insightsOpen;
    insightsPanel.classList.toggle('collapsed', !insightsOpen);
}

async function fetchPins(patientId) {
    try {
        const res = await fetch(`/api/patients/${patientId}/pins`);
        patientPins[patientId] = await res.json();
    } catch (e) {
        console.error('Failed to fetch pins:', e);
        patientPins[patientId] = [];
    }
}

async function addPin(patientId, pinData) {
    try {
        const body = { ...pinData };
        if (body.type === 'citation') body.query = lastUserQuery;
        await fetch(`/api/patients/${patientId}/pins`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        await fetchPins(patientId);
        renderInsightsPanel();
        highlightPinnedText();
    } catch (e) {
        console.error('Failed to add pin:', e);
    }
}

async function removePin(patientId, pinId) {
    try {
        await fetch(`/api/patients/${patientId}/pins/${pinId}`, { method: 'DELETE' });
        await fetchPins(patientId);
        renderInsightsPanel();
        highlightPinnedText();
    } catch (e) {
        console.error('Failed to remove pin:', e);
    }
}

function isPinned(patientId, citation) {
    return !!findPinId(patientId, citation);
}

function findPinId(patientId, citation) {
    const pins = patientPins[patientId] || [];
    const match = pins.find(p =>
        p.type !== 'text' && p.citation &&
        p.citation.agent === citation.agent && p.citation.web_path === citation.web_path
    );
    return match ? match.pin_id : null;
}

function isTextPinned(patientId, text) {
    return !!findTextPinId(patientId, text);
}

function findTextPinId(patientId, text) {
    const pins = patientPins[patientId] || [];
    const match = pins.find(p => p.type === 'text' && p.text === text);
    return match ? match.pin_id : null;
}

function buildPinPreview(citation) {
    const type = getCitationType(citation.file);
    if (type === 'image') {
        const isSvg = citation.file.endsWith('.svg');
        return `<div class="pinned-card-preview"><img src="${citation.web_path}" alt="" style="${isSvg ? 'background:#f8f5f0;object-fit:contain;' : ''}"></div>`;
    } else if (type === 'video') {
        return '<div class="pinned-card-preview"><span class="pinned-card-preview-icon">&#x1F3AC;</span></div>';
    } else if (type === 'audio') {
        return '<div class="pinned-card-preview"><span class="pinned-card-preview-icon">&#x23E6;</span></div>';
    } else {
        return '<div class="pinned-card-preview"><span class="pinned-card-preview-icon">&#x1F4C4;</span></div>';
    }
}

function renderInsightsPanel() {
    const pins = (activePatientId && patientPins[activePatientId]) || [];
    if (pins.length === 0) {
        insightsContent.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#x1F4CC;</div><div class="empty-state-text">No pinned citations</div></div>';
        return;
    }
    insightsContent.innerHTML = '';
    pins.forEach(p => {
        const card = document.createElement('div');
        card.className = 'pinned-card';
        card.dataset.pinId = p.pin_id;

        if (p.type === 'text') {
            card.dataset.pinType = 'text';
            card.dataset.text = p.text;
            card.dataset.source = p.source || '';
            card.innerHTML = `
                <div class="pinned-card-agent">Pinned Text</div>
                <div class="pinned-card-summary">${escapeHtml(p.text)}</div>
                ${p.source ? `<span class="pinned-card-source" data-session-id="${escapeHtml(p.source)}" title="Go to source">View in chat &#x2192;</span>` : ''}
                <button class="btn-unpin" title="Unpin">&times;</button>
            `;
        } else {
            card.dataset.pinType = 'citation';
            card.dataset.citation = JSON.stringify(p.citation);
            card.dataset.source = p.source || '';
            const agentLabel = agentCardLabels[p.citation.agent] || p.citation.agent.replace(/_/g, ' ');
            const previewHTML = buildPinPreview(p.citation);
            const annotationText = p.annotations && p.annotations.text ? p.annotations.text : '';
            const annotationTags = p.annotations && p.annotations.tags && p.annotations.tags.length > 0 ? p.annotations.tags : [];
            card.innerHTML = `
                <div class="pinned-card-agent">${escapeHtml(agentLabel)}</div>
                ${previewHTML}
                <div class="pinned-card-summary">${escapeHtml(p.citation.summary)}</div>
                ${annotationText ? `<div class="pinned-card-annotation">${escapeHtml(annotationText.slice(0, 60))}${annotationText.length > 60 ? '…' : ''}</div>` : ''}
                ${annotationTags.length > 0 ? `<div class="pinned-card-tags">${annotationTags.map(t => `<span class="pinned-card-tag">${escapeHtml(t)}</span>`).join('')}</div>` : ''}
                ${p.source ? `<span class="pinned-card-source" data-session-id="${escapeHtml(p.source)}" title="Go to source">View in chat &#x2192;</span>` : ''}
                <button class="btn-unpin" title="Unpin">&times;</button>
            `;
        }
        insightsContent.appendChild(card);
    });
}

// Insights panel event delegation
insightsContent.addEventListener('click', (e) => {
    // Unpin button
    const unpinBtn = e.target.closest('.btn-unpin');
    if (unpinBtn) {
        e.stopPropagation();
        const card = unpinBtn.closest('.pinned-card');
        if (card && activePatientId) {
            removePin(activePatientId, card.dataset.pinId);
        }
        return;
    }

    // Source link click → navigate to conversation
    const sourceLink = e.target.closest('.pinned-card-source');
    if (sourceLink) {
        e.stopPropagation();
        const sid = sourceLink.dataset.sessionId;
        const card = sourceLink.closest('.pinned-card');
        const text = card ? card.dataset.text : '';
        if (sid && activePatientId) {
            switchConversation(activePatientId, sid).then(() => {
                if (text) scrollToTextInChat(text);
            });
        }
        return;
    }

    // Preview click → open citation modal
    const preview = e.target.closest('.pinned-card-preview');
    if (preview) {
        e.stopPropagation();
        const card = preview.closest('.pinned-card');
        if (card && card.dataset.pinType === 'citation') {
            const citation = JSON.parse(card.dataset.citation);
            const pinId = card.dataset.pinId;
            const pin = (patientPins[activePatientId] || []).find(p => p.pin_id === pinId) || null;
            openCitationModal(citation, pin);
        }
        return;
    }

    // Card click → navigate to source conversation
    const card = e.target.closest('.pinned-card');
    if (card) {
        const sid = card.dataset.source;
        if (card.dataset.pinType === 'text') {
            const text = card.dataset.text;
            if (sid && activePatientId) {
                switchConversation(activePatientId, sid).then(() => {
                    scrollToTextInChat(text);
                });
            }
        } else {
            // Citation card click → navigate to source chat
            if (sid && activePatientId) {
                switchConversation(activePatientId, sid);
            }
        }
    }
});

insightsToggle.addEventListener('click', toggleInsights);

// ─── Sidebar: Expand / Collapse Patient ─────────────────────
async function togglePatient(patientEl) {
    const wasExpanded = patientEl.classList.contains('expanded');

    // Collapse all
    document.querySelectorAll('.sidebar-patient.expanded').forEach(el => {
        el.classList.remove('expanded');
    });

    if (!wasExpanded) {
        patientEl.classList.add('expanded');
        // Load conversations for this patient
        const pid = patientEl.dataset.patientId;
        await loadConversations(pid, patientEl);
    }
}

async function loadConversations(patientId, patientEl) {
    try {
        const res = await fetch(`/api/patients/${patientId}/conversations`);
        const convos = await res.json();
        const listEl = patientEl.querySelector('.conversation-list');
        listEl.innerHTML = '';
        convos.forEach(c => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            if (c.session_id === activeConversationId) {
                item.classList.add('active');
            }
            item.dataset.sessionId = c.session_id;
            item.dataset.patientId = patientId;
            item.textContent = c.preview || 'New conversation';
            listEl.appendChild(item);
        });
    } catch (e) {
        console.error('Failed to load conversations:', e);
    }
}

// ─── Sidebar: Switch Conversation ───────────────────────────
async function switchConversation(patientId, sid) {
    const changingPatient = activePatientId !== patientId;
    activePatientId = patientId;
    activeConversationId = sid;
    sessionId = sid;
    localStorage.setItem('meddata_session_id', sid);

    // Update active patient label with name
    const patientEl = document.querySelector(`.sidebar-patient[data-patient-id="${patientId}"]`);
    const patientName = patientEl ? patientEl.dataset.patientName : patientId;
    activePatientLabel.textContent = `— ${patientName}`;

    // Highlight active conversation in sidebar
    document.querySelectorAll('.conversation-item').forEach(el => {
        el.classList.toggle('active', el.dataset.sessionId === sid);
    });

    // Only re-fetch pins when switching to a different patient;
    // within the same patient the local cache is authoritative and
    // a fresh fetch would race with any in-flight PATCH requests.
    if (changingPatient) {
        await fetchPins(patientId);
    }
    renderInsightsPanel();

    // Clear chat and load history
    chatContainer.innerHTML = '';
    try {
        const res = await fetch(`/api/session/${sid}`);
        const data = await res.json();
        if (data.status === 'success' && data.history) {
            data.history.forEach(msg => {
                addChatMessage(msg.role, msg.content);
            });
        }
    } catch (e) {
        console.error('Failed to load session:', e);
    }
    highlightPinnedText();
}

// ─── Sidebar: Create New Conversation ───────────────────────
async function createNewConversation(patientId) {
    try {
        const res = await fetch(`/api/patients/${patientId}/conversations`, { method: 'POST' });
        const data = await res.json();
        // Refresh conversation list
        const patientEl = document.querySelector(`.sidebar-patient[data-patient-id="${patientId}"]`);
        if (patientEl) {
            await loadConversations(patientId, patientEl);
        }
        // Switch to new conversation
        await switchConversation(patientId, data.session_id);
    } catch (e) {
        console.error('Failed to create conversation:', e);
    }
}

// ─── Sidebar: Refresh active patient's conversation list ────
async function refreshSidebarConversations() {
    if (!activePatientId) return;
    const patientEl = document.querySelector(`.sidebar-patient[data-patient-id="${activePatientId}"]`);
    if (patientEl) {
        await loadConversations(activePatientId, patientEl);
    }
}

// ─── Sidebar: Event Delegation ──────────────────────────────
sidebarContent.addEventListener('click', async (e) => {
    // New conversation button
    const newBtn = e.target.closest('.btn-new-conversation');
    if (newBtn) {
        await createNewConversation(newBtn.dataset.patientId);
        return;
    }

    // Conversation item click
    const convoItem = e.target.closest('.conversation-item');
    if (convoItem) {
        await switchConversation(convoItem.dataset.patientId, convoItem.dataset.sessionId);
        return;
    }

    // Patient header click (expand/collapse)
    const header = e.target.closest('.sidebar-patient-header');
    if (header) {
        const patientEl = header.closest('.sidebar-patient');
        await togglePatient(patientEl);
    }
});

sidebarToggle.addEventListener('click', toggleSidebar);

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
        // Refresh sidebar to update conversation preview
        refreshSidebarConversations();
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

// Agent ID → short display label for citation badges
const agentBadgeLabels = {
    'clinical_notes': 'Notes',
    'chest_xray':     'X-Ray',
    'ecg':            'ECG',
    'heart_sounds':   'Heart Sounds',
    'echo':           'Echo',
    'lab_results':    'Labs',
    'medication':     'Meds',
};

// Agent ID → full display name for citation card header
const agentCardLabels = {
    'clinical_notes': 'Findings from Clinical Notes',
    'chest_xray':     'Findings from Chest X-Ray',
    'ecg':            'Findings from ECG',
    'heart_sounds':   'Findings from Heart Sounds',
    'echo':           'Findings from Echocardiogram',
    'lab_results':    'Findings from Lab Results',
    'medication':     'Findings from Medications',
};

// Agent info for tooltip (per agent type)
const agentInfo = {
    'clinical_notes': { analyzes: 'Clinical text notes and physician documentation', output: 'Text summary' },
    'chest_xray':     { analyzes: 'Chest X-ray images (PNG)', output: 'Image + findings' },
    'ecg':            { analyzes: '12-lead ECG waveforms from HL7 source data', output: 'SVG waveform + findings' },
    'heart_sounds':   { analyzes: 'Heart auscultation audio recordings', output: 'Audio + findings' },
    'echo':           { analyzes: 'Echocardiogram video recordings', output: 'Video + findings' },
    'lab_results':    { analyzes: 'Laboratory results from HL7v2 source data', output: 'Chart image + findings' },
    'medication':     { analyzes: 'Medication history and prescriptions', output: 'CSV table + findings' },
};

// Replace [cite:X] tokens with hoverable <sup> badges
function renderWithCitations(html, citations) {
    const citationMap = {};
    citations.forEach(c => { citationMap[c.id] = c; });

    return html.replace(/\[cite:(\w+)\]/g, (match, id) => {
        const citation = citationMap[id];
        if (!citation) return match;
        const data = encodeURIComponent(JSON.stringify(citation));
        const label = agentBadgeLabels[citation.agent] || citation.agent.replace(/_/g, ' ');
        return `<sup class="citation" data-citation="${data}">${escapeHtml(label)}</sup>`;
    });
}

// Derive modality type from file extension
function getCitationType(file) {
    const ext = file.split('.').pop().toLowerCase();
    return { png: 'image', jpg: 'image', jpeg: 'image', svg: 'image',
             csv: 'csv', txt: 'text', mp4: 'video', wav: 'audio' }[ext] || 'text';
}

// Convert plain text to reflowed HTML paragraphs (collapse hard line-wraps)
function plainTextToHTML(text) {
    return text
        .split(/\n\s*\n/)                          // split on blank lines → paragraphs
        .map(p => p.replace(/\s*\n\s*/g, ' ').trim()) // collapse single newlines
        .filter(Boolean)
        .map(p => `<p>${escapeHtml(p)}</p>`)
        .join('');
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
    const agentLabel = agentCardLabels[citation.agent] || citation.agent.replace(/_/g, ' ');

    // Build initial content (immediate for media, loading state for text/csv)
    let contentHTML = '';
    if (type === 'image') {
        const isSvg = citation.file.endsWith('.svg');
        contentHTML = `<img class="card-image${isSvg ? ' card-image-svg' : ''}" src="${citation.web_path}" alt="${escapeHtml(agentLabel)}">`;
    } else if (type === 'video') {
        contentHTML = `<video class="card-video" src="${citation.web_path}" controls></video>`;
    } else if (type === 'audio') {
        contentHTML = `<div class="card-audio-wrap"><audio class="card-audio" src="${citation.web_path}" controls></audio></div>`;
    } else {
        contentHTML = `<div class="card-loading">Loading…</div>`;
    }

    const pinBtnHTML = activePatientId
        ? `<button class="btn-pin-card${isPinned(activePatientId, citation) ? ' pinned' : ''}" data-citation="${encodeURIComponent(JSON.stringify(citation))}" title="Pin citation">&#x1F4CC;</button>`
        : '';

    citationPopup.innerHTML = `
        <div class="card-header">
            <span class="card-agent">${escapeHtml(agentLabel)}</span>
            ${pinBtnHTML}
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
                    : `<div class="card-text">${plainTextToHTML(text.slice(0, 600))}${text.length > 600 ? '<p>…</p>' : ''}</div>`;
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

// Format ISO date string for display
function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });
}

// Debounce utility
function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// Split summary text into checklist items; returns null if < 2 items
function parseSummaryToChecklist(text) {
    const parts = text.split(/\.\s+|\n+/)
        .map(s => s.replace(/\.$/, '').trim())
        .filter(s => s.length >= 20);
    if (parts.length < 2) return null;
    return parts.slice(0, 8);
}

// Build checklist UL element from items + saved state
function renderModalChecklist(items, checklist_state) {
    const ul = document.createElement('ul');
    ul.className = 'findings-checklist';
    items.forEach((item, i) => {
        const li = document.createElement('li');
        const checked = checklist_state[String(i)] || false;
        if (checked) li.classList.add('checked');
        li.innerHTML = `
            <input type="checkbox" id="chk-${i}"${checked ? ' checked' : ''}>
            <label for="chk-${i}">${escapeHtml(item)}</label>
        `;
        ul.appendChild(li);
    });
    return ul;
}

// PATCH a pin's annotations or checklist_state; updates local cache
async function patchPin(patientId, pinId, data) {
    try {
        await fetch(`/api/patients/${patientId}/pins/${pinId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        // Update local cache directly
        const pins = patientPins[patientId] || [];
        const pin = pins.find(p => p.pin_id === pinId);
        if (pin) {
            if (data.annotations !== undefined) pin.annotations = data.annotations;
            if (data.checklist_state !== undefined) pin.checklist_state = data.checklist_state;
        }
    } catch (e) {
        console.error('Failed to patch pin:', e);
    }
}

const debouncedPatchAnnotations = debounce((patientId, pinId, annotations) => {
    patchPin(patientId, pinId, { annotations });
}, 500);

const debouncedPatchChecklist = debounce((patientId, pinId, checklist_state) => {
    patchPin(patientId, pinId, { checklist_state });
}, 500);

// Clear chat
function clearChat() {
    chatContainer.innerHTML = '';
    // Clear session and start fresh
    sessionId = null;
    activeConversationId = null;
    activePatientId = null;
    activePatientLabel.textContent = '';
    localStorage.removeItem('meddata_session_id');
    // Clear attached file
    removeFile();
    // Remove active highlight from sidebar
    document.querySelectorAll('.conversation-item.active').forEach(el => {
        el.classList.remove('active');
    });
    // Clear insights panel
    renderInsightsPanel();
}

// Send message
async function sendMessage() {
    const message = messageInput.value.trim();

    if (!message) {
        return;
    }

    // Capture query for provenance before clearing input
    lastUserQuery = message;

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
        if (activePatientId) {
            formData.append('patient_id', activePatientId);
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
                activeConversationId = result.session_id;
                localStorage.setItem('meddata_session_id', sessionId);
            }
            // Clear attached file after successful send
            removeFile();
            // Refresh sidebar to show conversation preview
            refreshSidebarConversations();
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

// Pin button on hover card
citationPopup.addEventListener('click', async (e) => {
    const pinBtn = e.target.closest('.btn-pin-card');
    if (!pinBtn || !activePatientId) return;
    e.stopPropagation();
    const citation = JSON.parse(decodeURIComponent(pinBtn.dataset.citation));
    const existingPinId = findPinId(activePatientId, citation);
    if (existingPinId) {
        await removePin(activePatientId, existingPinId);
        pinBtn.classList.remove('pinned');
    } else {
        await addPin(activePatientId, { type: 'citation', citation, source: getActiveSessionId() });
        pinBtn.classList.add('pinned');
    }
});

// ─── Citation Detail Modal ──────────────────────────────────
const citationBackdrop = document.getElementById('citation-backdrop');
const citationModal = document.getElementById('citation-modal');
const modalAgent = document.getElementById('modal-agent');
const modalBody = document.getElementById('modal-body');
const modalSummary = document.getElementById('modal-summary');
const modalClose = document.getElementById('modal-close');

// Build modal table from CSV (larger version — all columns)
function csvToModalHTML(csv, maxRows = 200) {
    const lines = csv.trim().split('\n').filter(l => l.trim());
    const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));

    let html = '<div class="modal-table-wrap"><table><thead><tr>';
    headers.forEach(h => html += `<th>${escapeHtml(h)}</th>`);
    html += '</tr></thead><tbody>';

    lines.slice(1, maxRows + 1).forEach(line => {
        const cells = line.split(',').map(c => c.trim().replace(/^"|"$/g, ''));
        html += '<tr>';
        cells.forEach(cell => html += `<td>${escapeHtml(cell)}</td>`);
        html += '</tr>';
    });
    html += '</tbody></table></div>';
    return html;
}

async function openCitationModal(citation, pin = null) {
    modalCitation = citation;

    // Look up pin if not provided
    if (!pin && activePatientId) {
        const pins = patientPins[activePatientId] || [];
        pin = pins.find(p =>
            p.type !== 'text' && p.citation &&
            p.citation.agent === citation.agent && p.citation.web_path === citation.web_path
        ) || null;
    }
    currentModalPin = pin;

    const type = getCitationType(citation.file);
    const agentLabel = agentCardLabels[citation.agent] || citation.agent.replace(/_/g, ' ');

    modalAgent.textContent = agentLabel;

    // Remove zoom state from previous open
    citationModal.classList.remove('zoomed');

    // Update modal pin button state
    if (activePatientId) {
        modalPin.style.display = '';
        modalPin.classList.toggle('pinned', isPinned(activePatientId, citation));
    } else {
        modalPin.style.display = 'none';
    }

    // ── Agent info tooltip ──────────────────────────────────
    const info = agentInfo[citation.agent];
    if (info) {
        modalAgentInfo.innerHTML = `
            <div class="agent-info-tooltip-body">
                <div class="agent-info-tooltip-row">
                    <span class="agent-info-tooltip-label">Analyzes</span>
                    <span class="agent-info-tooltip-value">${escapeHtml(info.analyzes)}</span>
                </div>
                <div class="agent-info-tooltip-row">
                    <span class="agent-info-tooltip-label">Output</span>
                    <span class="agent-info-tooltip-value">${escapeHtml(info.output)}</span>
                </div>
                <div class="agent-info-tooltip-row">
                    <span class="agent-info-tooltip-label">Model</span>
                    <span class="agent-info-tooltip-value">Gemini 3.1 Pro</span>
                </div>
            </div>
            <div class="agent-info-tooltip-disclaimer">AI-generated — requires clinical verification</div>
        `;
        modalInfoBtn.style.display = '';
    } else {
        modalInfoBtn.style.display = 'none';
    }

    // ── Provenance ──────────────────────────────────────────
    let provenanceHTML = '';
    if (pin && pin.query) {
        const q = pin.query.length > 80 ? pin.query.slice(0, 77) + '…' : pin.query;
        provenanceHTML += `<div>Asked: "${escapeHtml(q)}"</div>`;
    }
    if (pin && pin.created_at) {
        provenanceHTML += `<div>Generated: ${formatDate(pin.created_at)}</div>`;
    }
    modalProvenance.innerHTML = provenanceHTML;

    // ── Annotations ─────────────────────────────────────────
    const annotations = pin ? (pin.annotations || { text: '', tags: [] }) : { text: '', tags: [] };
    modalAnnotationText.value = annotations.text || '';
    modalAnnotationText.style.height = 'auto';
    setTimeout(() => {
        modalAnnotationText.style.height = modalAnnotationText.scrollHeight + 'px';
    }, 0);
    renderAnnotationTags(annotations.tags || []);

    // ── Build body content ───────────────────────────────────
    let contentHTML = '';
    if (type === 'image') {
        const isSvg = citation.file.endsWith('.svg');
        contentHTML = `<img src="${citation.web_path}" alt="${escapeHtml(agentLabel)}"${isSvg ? ' class="modal-image-svg"' : ''}>`;
    } else if (type === 'video') {
        contentHTML = `<video src="${citation.web_path}" controls autoplay></video>`;
    } else if (type === 'audio') {
        contentHTML = `<div class="modal-audio-wrap"><audio src="${citation.web_path}" controls></audio></div>`;
    } else {
        contentHTML = '<div class="modal-loading">Loading\u2026</div>';
    }
    modalBody.innerHTML = contentHTML;

    // ── Summary or Checklist ─────────────────────────────────
    const checklistItems = parseSummaryToChecklist(citation.summary);
    if (checklistItems) {
        const checklist_state = pin ? (pin.checklist_state || {}) : {};
        modalSummary.innerHTML = '';
        modalSummary.style.padding = '0';
        const ul = renderModalChecklist(checklistItems, checklist_state);
        modalSummary.appendChild(ul);
        // Checkbox change handlers
        ul.querySelectorAll('input[type="checkbox"]').forEach((cb, i) => {
            cb.addEventListener('change', async () => {
                const li = cb.closest('li');
                li.classList.toggle('checked', cb.checked);
                if (!activePatientId) return;
                if (!currentModalPin && !(await ensurePinned())) return;
                currentModalPin.checklist_state = currentModalPin.checklist_state || {};
                currentModalPin.checklist_state[String(i)] = cb.checked;
                debouncedPatchChecklist(activePatientId, currentModalPin.pin_id,
                    { ...currentModalPin.checklist_state });
            });
        });
    } else {
        modalSummary.style.padding = '';
        modalSummary.textContent = citation.summary;
    }

    // Show modal
    citationBackdrop.classList.add('open');
    citationModal.classList.add('open');

    // Fetch text-based content
    if (type === 'csv' || type === 'text') {
        try {
            const text = await fetch(citation.web_path).then(r => r.text());
            modalBody.innerHTML = type === 'csv'
                ? csvToModalHTML(text)
                : `<div class="modal-text">${plainTextToHTML(text)}</div>`;
        } catch {
            modalBody.innerHTML = '<div class="modal-text" style="color: var(--critical);">Could not load content.</div>';
        }
    }
}

// Pin the current modal citation if not already pinned; returns true on success
async function ensurePinned() {
    if (currentModalPin) return true;
    if (!activePatientId || !modalCitation) return false;
    await addPin(activePatientId, { type: 'citation', citation: modalCitation, source: getActiveSessionId() });
    const pins = patientPins[activePatientId] || [];
    currentModalPin = pins.find(p =>
        p.type !== 'text' && p.citation &&
        p.citation.agent === modalCitation.agent && p.citation.web_path === modalCitation.web_path
    ) || null;
    if (currentModalPin) modalPin.classList.add('pinned');
    return !!currentModalPin;
}

// Render predefined tag chips with active state
function renderAnnotationTags(activeTags) {
    const predefinedTags = ['#follow-up', '#critical', '#reviewed', '#discuss', '#normal'];
    modalAnnotationTags.innerHTML = '';
    predefinedTags.forEach(tag => {
        const btn = document.createElement('button');
        btn.className = 'annotation-tag' + (activeTags.includes(tag) ? ' active' : '');
        btn.textContent = tag;
        btn.addEventListener('click', async () => {
            if (!activePatientId) return;
            if (!currentModalPin && !(await ensurePinned())) return;
            const ann = currentModalPin.annotations = currentModalPin.annotations || { text: '', tags: [] };
            const tags = ann.tags || [];
            const idx = tags.indexOf(tag);
            if (idx === -1) tags.push(tag); else tags.splice(idx, 1);
            ann.tags = tags;
            renderAnnotationTags(tags);
            renderInsightsPanel();
            patchPin(activePatientId, currentModalPin.pin_id, { annotations: { ...ann } });
        });
        modalAnnotationTags.appendChild(btn);
    });
}

function closeCitationModal() {
    citationBackdrop.classList.remove('open');
    citationModal.classList.remove('open');
    citationModal.classList.remove('zoomed');
    // Stop any playing media
    modalBody.querySelectorAll('video, audio').forEach(el => { el.pause(); el.src = ''; });
    modalBody.innerHTML = '';
    currentModalPin = null;
}

// Click citation → open modal
chatContainer.addEventListener('click', (e) => {
    const target = e.target.closest('.citation');
    if (!target) return;
    e.preventDefault();
    // Hide hover card
    citationPopup.style.display = 'none';
    clearTimeout(hideTimeout);
    const citation = JSON.parse(decodeURIComponent(target.dataset.citation));
    openCitationModal(citation);
});

modalClose.addEventListener('click', closeCitationModal);
citationBackdrop.addEventListener('click', closeCitationModal);

// Modal pin button (citation pins only — text pins navigate directly)
modalPin.addEventListener('click', async () => {
    if (!activePatientId || !modalCitation) return;
    const existingPinId = findPinId(activePatientId, modalCitation);
    if (existingPinId) {
        await removePin(activePatientId, existingPinId);
        modalPin.classList.remove('pinned');
    } else {
        await addPin(activePatientId, { type: 'citation', citation: modalCitation, source: getActiveSessionId() });
        modalPin.classList.add('pinned');
    }
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && citationModal.classList.contains('open')) {
        if (citationModal.classList.contains('zoomed')) {
            citationModal.classList.remove('zoomed');
        } else {
            closeCitationModal();
        }
    }
});

// Image zoom toggle
modalBody.addEventListener('click', (e) => {
    if (e.target.tagName === 'IMG') {
        citationModal.classList.toggle('zoomed');
    }
});

// Agent info tooltip hover (button + tooltip both keep it visible)
let tooltipHideTimeout = null;
modalInfoBtn.addEventListener('mouseenter', () => {
    clearTimeout(tooltipHideTimeout);
    modalAgentInfo.classList.add('visible');
});
modalInfoBtn.addEventListener('mouseleave', () => {
    tooltipHideTimeout = setTimeout(() => modalAgentInfo.classList.remove('visible'), 100);
});
modalAgentInfo.addEventListener('mouseenter', () => clearTimeout(tooltipHideTimeout));
modalAgentInfo.addEventListener('mouseleave', () => modalAgentInfo.classList.remove('visible'));

// Annotation textarea: auto-grow + debounced save (auto-pins if needed)
modalAnnotationText.addEventListener('input', async () => {
    modalAnnotationText.style.height = 'auto';
    modalAnnotationText.style.height = modalAnnotationText.scrollHeight + 'px';
    if (!activePatientId) return;
    if (!currentModalPin && !(await ensurePinned())) return;
    currentModalPin.annotations = currentModalPin.annotations || { text: '', tags: [] };
    currentModalPin.annotations.text = modalAnnotationText.value;
    debouncedPatchAnnotations(activePatientId, currentModalPin.pin_id,
        { ...currentModalPin.annotations });
});

// ─── Pinned Text Highlighting ────────────────────────────────
function clearPinnedHighlights() {
    chatContainer.querySelectorAll('mark.pinned-highlight').forEach(mark => {
        const parent = mark.parentNode;
        parent.replaceChild(document.createTextNode(mark.textContent), mark);
        parent.normalize();
    });
}

function highlightPinnedText() {
    clearPinnedHighlights();
    if (!activePatientId) return;
    const pins = patientPins[activePatientId] || [];
    const textPins = pins.filter(p => p.type === 'text').map(p => p.text);
    if (textPins.length === 0) return;

    const bubbles = chatContainer.querySelectorAll('.chat-message.assistant .message-content');
    bubbles.forEach(bubble => {
        textPins.forEach(pinText => {
            highlightTextInNode(bubble, pinText);
        });
    });
}

function highlightTextInNode(root, searchText) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const matches = [];

    while (walker.nextNode()) {
        const node = walker.currentNode;
        const idx = node.textContent.indexOf(searchText);
        if (idx !== -1) {
            matches.push({ node, idx });
        }
    }

    // Process in reverse to avoid invalidating offsets
    for (let i = matches.length - 1; i >= 0; i--) {
        const { node, idx } = matches[i];
        const range = document.createRange();
        range.setStart(node, idx);
        range.setEnd(node, idx + searchText.length);
        const mark = document.createElement('mark');
        mark.className = 'pinned-highlight';
        range.surroundContents(mark);
    }
}

function scrollToTextInChat(text) {
    if (!text) return;
    const marks = chatContainer.querySelectorAll('mark.pinned-highlight');
    for (const mark of marks) {
        if (mark.textContent === text) {
            mark.scrollIntoView({ behavior: 'smooth', block: 'center' });
            // Brief flash effect
            mark.style.transition = 'background 0.3s';
            mark.style.background = 'rgba(166, 120, 48, 0.35)';
            setTimeout(() => { mark.style.background = ''; }, 1200);
            return;
        }
    }
    // Fallback: search text nodes directly
    const bubbles = chatContainer.querySelectorAll('.chat-message.assistant .message-content');
    for (const bubble of bubbles) {
        if (bubble.textContent.includes(text)) {
            bubble.closest('.chat-message').scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }
    }
}

// ─── Text Selection Pin Button ──────────────────────────────
const textSelectPin = document.createElement('button');
textSelectPin.className = 'text-select-pin';
textSelectPin.innerHTML = '&#x1F4CC;<span class="text-select-pin-label">Pin</span>';
document.body.appendChild(textSelectPin);

function getActiveSessionId() {
    return activeConversationId || sessionId || '';
}

function hideTextSelectPin() {
    textSelectPin.style.display = 'none';
}

chatContainer.addEventListener('mouseup', (e) => {
    // Ignore if clicking on citation badges or the pin button itself
    if (e.target.closest('.citation') || e.target.closest('.text-select-pin')) return;
    if (!activePatientId) return;

    const sel = window.getSelection();
    const text = sel.toString().trim();
    if (!text) { hideTextSelectPin(); return; }

    // Check if selection is inside an assistant message bubble
    if (!sel.anchorNode) { hideTextSelectPin(); return; }
    const bubble = sel.anchorNode.nodeType === Node.TEXT_NODE
        ? sel.anchorNode.parentElement.closest('.chat-message.assistant .message-bubble')
        : sel.anchorNode.closest('.chat-message.assistant .message-bubble');
    if (!bubble) { hideTextSelectPin(); return; }

    // Position above selection
    const range = sel.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    textSelectPin.style.display = 'block';
    const btnW = textSelectPin.offsetWidth;
    let left = rect.left + (rect.width / 2) - (btnW / 2);
    left = Math.max(8, Math.min(left, window.innerWidth - btnW - 8));
    let top = rect.top - 36;
    if (top < 8) top = rect.bottom + 8;
    textSelectPin.style.left = `${left}px`;
    textSelectPin.style.top = `${top}px`;
});

textSelectPin.addEventListener('mousedown', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const sel = window.getSelection();
    const text = sel.toString().trim();
    if (!text || !activePatientId) return;

    const sourceSessionId = getActiveSessionId();
    hideTextSelectPin();
    await addPin(activePatientId, { type: 'text', text, source: sourceSessionId });
    sel.removeAllRanges();
});

document.addEventListener('mousedown', (e) => {
    if (e.target.closest('.text-select-pin')) return;
    hideTextSelectPin();
});

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

// Initialize
connectWebSocket();
loadPatients();
