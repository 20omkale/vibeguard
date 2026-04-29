const API_BASE = 'http://localhost:7456/api';
let currentProvider = '';
let globalProjectPath = '';
let chatHistory = [];
let activeFileContent = ''; 
let activeFileName = '';
let isGuardActive = false;

// ── UI Persistence ──
function showMode(modeId) {
  document.querySelectorAll('.mode-view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  
  const target = document.getElementById('mode-' + modeId);
  if (target) target.classList.add('active');
  
  const navItem = document.querySelector(`[data-page="${modeId}"]`);
  if (navItem) navItem.classList.add('active');
  
  if (modeId === 'settings') loadSettings();
}

// ── Workspace: File Explorer ──
async function refreshExplorer() {
  const pathInput = document.getElementById('globalProjectPath');
  globalProjectPath = pathInput.value.trim();
  if (!globalProjectPath) return;

  const explorer = document.getElementById('fileExplorer');
  explorer.innerHTML = '<div class="loading">Reading project...</div>';

  try {
    const res = await fetch(`${API_BASE}/utils/files`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: globalProjectPath})
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    
    explorer.innerHTML = renderTree(data.files);
    document.getElementById('fileCount').innerText = countFiles(data.files);
    loadRecentProjects(); // Refresh recent list
  } catch (e) {
    explorer.innerHTML = `<div class="log-error">Error: ${e.message}</div>`;
  }
}

async function loadRecentProjects() {
  const res = await fetch(`${API_BASE}/utils/recent`);
  const data = await res.json();
  const list = document.getElementById('recentProjects');
  if (!list || !data.recent) return;
  
  list.innerHTML = data.recent.map(path => {
    const name = path.split(/[\\/]/).pop();
    return `
      <div class="recent-item" onclick="openRecent('${path.replace(/\\/g, '/')}')" title="${path}">
        <span style="opacity:0.5;font-size:10px">🕒</span> ${name}
      </div>
    `;
  }).join('');
}

function openRecent(path) {
  document.getElementById('globalProjectPath').value = path;
  globalProjectPath = path;
  refreshExplorer();
}


function countFiles(nodes) {
  let count = 0;
  nodes.forEach(n => {
    if (!n.is_dir) count++;
    if (n.children) count += countFiles(n.children);
  });
  return count;
}


function renderTree(nodes, depth = 0) {
  let html = '';
  nodes.forEach(node => {
    const padding = depth * 12;
    const icon = node.is_dir ? '📁' : '📄';
    const classes = node.is_dir ? 'explorer-item dir' : 'explorer-item';
    
    html += `
      <div class="${classes}" style="padding-left: ${padding + 12}px" onclick="${node.is_dir ? '' : `openFile('${node.path.replace(/\\/g, '/')}')`}">
        <span class="icon">${icon}</span>
        <span class="name">${node.name}</span>
      </div>
    `;
    if (node.is_dir && node.children) {
      html += renderTree(node.children, depth + 1);
    }
  });
  return html;
}

// ── Workspace: Code Viewer ──
async function openFile(relPath) {
  if (!globalProjectPath) return;
  
  const viewer = document.getElementById('codeViewer');
  const welcome = document.getElementById('welcomeScreen');
  const fileName = document.getElementById('activeFileName');
  
  fileName.innerText = `Loading ${relPath}...`;
  
  try {
    const res = await fetch(`${API_BASE}/utils/read-file`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({root: globalProjectPath, path: relPath})
    });
    const data = await res.json();
    
    welcome.style.display = 'none';
    viewer.style.display = 'block';
    viewer.textContent = data.content;
    activeFileContent = data.content;
    activeFileName = data.path;
    fileName.innerText = relPath;
    
    // Highlight the active file in explorer (simple)
    document.querySelectorAll('.explorer-item').forEach(el => {
      if (el.innerText.includes(data.name)) el.classList.add('active');
      else el.classList.remove('active');
    });
  } catch (e) {
    fileName.innerText = 'Error loading file';
  }
}

// ── Global Terminal ──
function clearTerminal() {
  document.getElementById('globalTerminal').innerHTML = '';
}

function logToTerminal(text, type = 'log') {
  const term = document.getElementById('globalTerminal');
  const div = document.createElement('div');
  if (type === 'step') div.className = 'log-step';
  else if (type === 'success') div.className = 'log-success';
  else if (type === 'error') div.className = 'log-error';
  
  div.innerHTML = type === 'step' ? `▶ ${text}` : text;
  term.appendChild(div);
  term.scrollTop = term.scrollHeight;
}

// ── Modified runStream for Global Terminal ──
function runGlobalStream(endpoint, payload, onComplete) {
  const term = document.getElementById('globalTerminal');
  logToTerminal(`Initializing ${endpoint}...`, 'step');
  
  fetch(`${API_BASE}/${endpoint}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  }).then(async response => {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    while(true) {
      const {done, value} = await reader.read();
      if (done) break;
      
      const lines = decoder.decode(value).split('\n');
      for (let line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = JSON.parse(line.replace('data: ', ''));
        
        if (data.type === 'ping') continue;
        if (data.type === 'log') logToTerminal(data.text);
        else if (data.type === 'step') logToTerminal(data.text, 'step');
        else if (data.type === 'success') logToTerminal(data.text, 'success');
        else if (data.type === 'error') logToTerminal(data.text, 'error');
        else if (data.type === 'result' || data.type === 'chat_reply') {
          if (onComplete) onComplete(data);
        }
      }
    }
  }).catch(e => logToTerminal(`Connection failed: ${e}`, 'error'));
}

// ── Chat Assistant ──
async function sendChatMessage() {
  const input = document.getElementById('chatInput');
  const chatMessages = document.getElementById('chatMessages');
  const text = input.value.trim();
  
  if (!text) return;

  chatMessages.innerHTML += `<div class="message-bubble user">${text}</div>`;
  chatHistory.push({role: "user", content: text});
  input.value = '';
  chatMessages.scrollTop = chatMessages.scrollHeight;

  const aiBubbleId = 'chat-' + Date.now();
  chatMessages.innerHTML += `
    <div class="message-bubble ai" id="${aiBubbleId}">
      <div class="chat-reply-body"><span class="spinner"></span> Working...</div>
    </div>
  `;
  chatMessages.scrollTop = chatMessages.scrollHeight;
  const aiBody = document.querySelector(`#${aiBubbleId} .chat-reply-body`);

  // Send message with Active File context if available
  runGlobalStream('chat', {
    messages: chatHistory, 
    path: globalProjectPath,
    activeFile: activeFileName,
    activeContent: activeFileContent
  }, (data) => {
    if (data.type === 'chat_reply') {
      aiBody.innerHTML = data.text.replace(/\n/g, '<br/>');
      chatHistory.push({role: "assistant", content: data.text});
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  });
}

// ── Genesis / Build / Upgrade Stubs (Simplified for Workspace) ──
async function genesisGetQuestions() {
  const idea = document.getElementById('genesisIdea').value;
  if (!idea) return;
  logToTerminal("Analyzing idea for blueprints...", "step");
  const res = await fetch(`${API_BASE}/genesis/questions`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({idea})
  });
  const data = await res.json();
  const qDiv = document.getElementById('genesisQuestions');
  qDiv.innerHTML = data.questions.map((q, i) => `
    <div style="margin-bottom:12px">
      <div style="font-size:12px;margin-bottom:4px">${q}</div>
      <input class="input-mini genesis-answer" data-q="${q}" placeholder="Your answer..."/>
    </div>
  `).join('');
  document.getElementById('genesisStep2').style.display = 'block';
}

function genesisRun() {
  const answers = {};
  document.querySelectorAll('.genesis-answer').forEach(input => {
    answers[input.dataset.q] = input.value;
  });
  runGlobalStream('genesis', {
    idea: document.getElementById('genesisIdea').value,
    answers: answers,
    path: globalProjectPath
  }, () => {
    refreshExplorer();
    logToTerminal("Genesis complete! Blueprints are in your project folder.", "success");
  });
}

function runUpgrade() {
  const instruction = document.getElementById('upgradeInstruction').value;
  if (!instruction || !globalProjectPath) return;
  runGlobalStream('upgrade', {
    path: globalProjectPath,
    instruction: instruction
  }, () => {
    refreshExplorer();
    logToTerminal("Upgrade complete! Changes materialized in the forge.", "success");
  });
}

function runBuild() {
  const prompt = document.getElementById('buildPrompt').value;
  if (!prompt || !globalProjectPath) return;
  runGlobalStream('build', {
    prompt: prompt,
    target_dir: globalProjectPath
  }, () => {
    refreshExplorer();
    logToTerminal("Build complete! Factory output delivered.", "success");
  });
}

function toggleGuard() {
  isGuardActive = !isGuardActive;
  const status = document.getElementById('guardStatus');
  const logs = document.getElementById('guardLogs');
  
  if (isGuardActive) {
    status.innerText = 'ACTIVE';
    status.className = 'status-value active';
    logs.innerHTML += `<div>[${new Date().toLocaleTimeString()}] Guard monitoring enabled...</div>`;
  } else {
    status.innerText = 'INACTIVE';
    status.className = 'status-value';
    logs.innerHTML += `<div>[${new Date().toLocaleTimeString()}] Guard disarmed.</div>`;
  }
}


function runDiagnostic() {
  if (!globalProjectPath) return;
  const resultDiv = document.getElementById('diagnoseResult');
  resultDiv.style.display = 'block';
  resultDiv.innerHTML = '<span class="spinner"></span> Analyzing project health...';
  
  runGlobalStream('diagnose', {path: globalProjectPath}, (data) => {
    // Show a summary in the sidebar result box
    resultDiv.innerHTML = `
      <div style="color:var(--accent-cyan);font-weight:700;margin-bottom:8px">System Health Report</div>
      <div class="diagnostic-text">${data.data.replace(/\n/g, '<br/>')}</div>
    `;
    logToTerminal("Diagnostic complete. See the Error Detective report.", "success");
  });
}


// ── Settings ──
async function loadSettings() {
  const res = await fetch(`${API_BASE}/config`);
  const data = await res.json();
  const grid = document.getElementById('providerGrid');
  grid.innerHTML = data.available_providers.map(p => `
    <div class="card ${p === data.provider ? 'active' : ''}" onclick="selectProvider('${p}')">
      ${p}
    </div>
  `).join('');
}

async function selectProvider(p) {
  await fetch(`${API_BASE}/config`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({provider: p})
  });
  loadSettings();
}

async function saveSettings() {
  const key = document.getElementById('apiKeyInput').value;
  await fetch(`${API_BASE}/config`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({api_key: key})
  });
  logToTerminal("Brain settings updated.", "success");
}

// ── Folder Picker Helper ──
async function selectFolder(inputId) {
  try {
    const res = await fetch(`${API_BASE}/utils/folder-picker`);
    const data = await res.json();
    if (data.path) {
      document.getElementById(inputId).value = data.path;
      globalProjectPath = data.path;
      refreshExplorer();
    }
  } catch(e) {}
}

// ── Init ──
window.onload = async () => {
  const res = await fetch(`${API_BASE}/status`);
  const data = await res.json();
  if (data.configured) {
    document.getElementById('providerStatus').innerHTML = `<div class="status-dot"></div><span>${data.provider_name}</span>`;
  }
  loadRecentProjects();
};

document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && document.activeElement.id === 'chatInput') {
    e.preventDefault();
    sendChatMessage();
  }
});
