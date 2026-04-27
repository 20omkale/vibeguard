const API_BASE = 'http://localhost:7456/api';
let currentProvider = '';

// ── UI Navigation ──
function showPage(pageId) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-' + pageId).classList.add('active');
  document.querySelector(`[data-page="${pageId}"]`).classList.add('active');
  
  if (pageId === 'settings') loadSettings();
}

// ── Init ──
window.onload = async () => {
  try {
    const res = await fetch(`${API_BASE}/status`);
    const data = await res.json();
    currentProvider = data.provider;
    
    if (data.configured) {
      document.getElementById('providerStatus').innerHTML = `
        <div class="status-dot"></div>
        <span id="providerName"><b>${data.provider_name}</b></span>
      `;
      document.getElementById('homeStatus').innerHTML = `<span style="color:var(--accent-cyan)">✅ Connected to ${data.provider_name}. Factory online.</span>`;
    } else {
      document.getElementById('providerStatus').innerHTML = `
        <div class="status-dot" style="background:var(--warn);box-shadow:0 0 10px var(--warn)"></div>
        <span id="providerName">Offline</span>
      `;
      document.getElementById('homeStatus').innerHTML = `<span style="color:var(--warn)">⚠️ No AI provider configured. <a href="#" onclick="showPage('settings')" style="color:var(--accent-cyan)">Configure Brain →</a></span>`;
      showPage('settings');
    }
  } catch(e) {
    document.getElementById('providerBadge').innerHTML = `<span style="color:var(--danger)">Server offline</span>`;
  }
};

// ── SSE Helper ──
function runStream(endpoint, payload, termId, resId, onComplete) {
  const term = document.getElementById(termId);
  const resBox = document.getElementById(resId);
  term.style.display = 'block';
  term.innerHTML = '';
  resBox.style.display = 'none';
  
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
        
        if (data.type === 'log') {
          term.innerHTML += `<div>${data.text}</div>`;
        } else if (data.type === 'step') {
          term.innerHTML += `<div class="log-step">▶ ${data.text}</div>`;
        } else if (data.type === 'success') {
          term.innerHTML += `<div class="log-success">${data.text}</div>`;
        } else if (data.type === 'error') {
          term.innerHTML += `<div class="log-error">✗ ${data.text}</div>`;
          resBox.className = 'result-box error';
          resBox.innerHTML = `<h3>❌ Error</h3><p>${data.text}</p>`;
          resBox.style.display = 'block';
        } else if (data.type === 'result') {
          if (onComplete) onComplete(data.data, resBox);
        }
        term.scrollTop = term.scrollHeight;
      }
    }
  }).catch(e => {
    term.innerHTML += `<div class="log-error">Connection failed: ${e}</div>`;
  });
}

// ── Genesis ──
let genesisAnswers = {};

async function genesisGetQuestions() {
  const idea = document.getElementById('genesisIdea').value;
  if(!idea) return;
  
  const btn = event.target;
  btn.innerHTML = '<span class="spinner"></span> Analyzing...';
  btn.disabled = true;
  
  try {
    const res = await fetch(`${API_BASE}/genesis/questions`, {
      method: 'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({idea})
    });
    const data = await res.json();
    
    let html = '';
    data.questions.forEach(q => {
      html += `
        <label class="field-label" style="margin-top:12px;color:var(--primary)">${q.question}</label>
        <input class="input" id="q_${q.id}" placeholder="${q.default || ''}"/>
      `;
    });
    
    document.getElementById('genesisQuestions').innerHTML = html;
    document.getElementById('genesis-step1').style.display = 'none';
    document.getElementById('genesis-step2').style.display = 'block';
  } catch(e) {
    genesisRun(); // fallback to running without questions
  }
}

function genesisSkip() {
  genesisAnswers = {};
  genesisRun();
}

function genesisRun() {
  const idea = document.getElementById('genesisIdea').value;
  const inputs = document.getElementById('genesisQuestions').querySelectorAll('input');
  
  inputs.forEach(inp => {
    const label = inp.previousElementSibling.innerText;
    if (inp.value.trim()) genesisAnswers[label] = inp.value.trim();
  });
  
  document.getElementById('genesis-step2').style.display = 'none';
  
  runStream('genesis', {idea, answers: genesisAnswers}, 'genesis-output', 'genesis-result', (data, resBox) => {
    resBox.className = 'result-box';
    resBox.innerHTML = `
      <h3 style="color:var(--success);margin-bottom:8px">✅ Blueprint Complete!</h3>
      <p style="margin-bottom:12px">Your 7 documents have been generated in:</p>
      <div style="background:rgba(0,0,0,0.2);padding:12px;border-radius:4px;font-family:monospace;margin-bottom:16px">${data.output_dir}</div>
      <p><b>Next Steps:</b></p>
      <ol style="margin-left:20px;margin-top:8px;color:var(--text-secondary)">
        <li>Read PRD.md to understand the scope</li>
        <li>Open AI_PROMPTS.md and paste Prompt #1 into Cursor/ChatGPT</li>
        <li>Or go to the Build tab here and I'll code it for you.</li>
      </ol>
    `;
    resBox.style.display = 'block';
  });
}

// ── Build ──
function runBuild() {
  const prompt = document.getElementById('buildPrompt').value;
  const target = document.getElementById('buildTarget').value;
  if(!prompt) return;
  
  runStream('build', {prompt, target_dir: target}, 'build-output', 'build-result', (data, resBox) => {
    resBox.className = 'result-box';
    resBox.innerHTML = `
      <h3 style="color:var(--success);margin-bottom:8px">✅ Build Complete!</h3>
      <p>Project generated in: <br/><code style="background:#000;padding:4px">${data.output_dir}</code></p>
      ${data.run_command ? `<p style="margin-top:12px">To run it:<br/><code style="background:#000;padding:4px;color:var(--primary)">${data.run_command}</code></p>` : ''}
    `;
    resBox.style.display = 'block';
  });
}

// ── Upgrade ──
function runUpgrade() {
  const path = document.getElementById('upgradePath').value;
  const instruction = document.getElementById('upgradeInstruction').value;
  if(!path || !instruction) return;
  
  runStream('upgrade', {path, instruction}, 'upgrade-output', 'upgrade-result', (data, resBox) => {
    resBox.className = 'result-box';
    resBox.innerHTML = `
      <h3 style="color:var(--accent-cyan);margin-bottom:8px">🚀 Upgrade Complete!</h3>
      <p>I have scanned and upgraded the project at: <br/><code style="background:#000;padding:4px">${data.path}</code></p>
      <p style="margin-top:12px"><b>Tasks performed:</b></p>
      <ul style="margin-left:20px;margin-top:8px;color:var(--text-secondary)">
        <li>Memory Engine updated</li>
        <li>Bugs identified and fixed</li>
        <li>Production optimizations applied</li>
      </ul>
    `;
    resBox.style.display = 'block';
  });
}

// ── Diagnose ──
function runDiagnose() {
  const error = document.getElementById('diagnoseError').value;
  const path = document.getElementById('diagnosePath').value;
  if(!error) return;
  
  runStream('diagnose', {error, project_path: path}, 'diagnose-output', 'diagnose-result', (data, resBox) => {
    // Diagnose doesn't return structured result yet, just outputs to terminal
  });
}

// ── Protect ──
function protectBefore() {
  const path = document.getElementById('protectPath').value;
  runStream('protect/before', {path}, 'protect-output', 'protect-result', (data, resBox) => {
    resBox.className = 'result-box';
    resBox.innerHTML = `
      <h3 style="color:var(--success);margin-bottom:8px">📸 Snapshot Saved</h3>
      <ul style="margin-left:20px;color:var(--text-secondary)">
        <li>Files scanned: ${data.files}</li>
        <li>Functions tracked: ${data.functions}</li>
        <li>API Routes: ${data.routes}</li>
      </ul>
      <p style="margin-top:16px;color:var(--text-main)">Now go do your AI coding session. Come back and click Check Changes when done.</p>
    `;
    resBox.style.display = 'block';
  });
}

function protectAfter() {
  const path = document.getElementById('protectPath').value;
  runStream('protect/after', {path}, 'protect-output', 'protect-result', (data, resBox) => {
    if (data.is_clean) {
      resBox.className = 'result-box';
      resBox.innerHTML = `<h3 style="color:var(--success)">✅ ALL CLEAR</h3><p>No functions, classes, or routes were deleted by the AI.</p>`;
    } else {
      resBox.className = 'result-box warn';
      let html = `<h3 style="color:var(--warn);margin-bottom:8px">⚠️ RISK DETECTED (${data.severity})</h3>`;
      html += `<p>The AI removed existing code. Review below:</p>`;
      
      if(data.deleted_functions.length > 0) {
        html += `<h4 style="margin-top:16px;color:var(--danger)">🗑️ Deleted Functions</h4><ul style="margin-left:20px;font-family:monospace;font-size:12px">`;
        data.deleted_functions.forEach(f => html += `<li>${f.name} (Line ${f.line}) in ${f.file}</li>`);
        html += `</ul>`;
      }
      
      html += `<div style="margin-top:20px;background:#000;padding:12px;border-radius:4px;border:1px solid var(--primary)"><b style="color:var(--primary)">🤖 Restore Prompt (Paste to AI):</b><br/><br/>
      <pre style="white-space:pre-wrap;font-size:12px;color:#a1a1aa">CRITICAL: Some code was accidentally removed. Restore these functions exactly where they belong:\n\n${data.deleted_functions.map(f => `- Function ${f.name} in ${f.file} (was at line ${f.line})`).join('\n')}</pre></div>`;
      
      resBox.innerHTML = html;
    }
    resBox.style.display = 'block';
  });
}

// ── Settings ──
let selProvider = '';

async function loadSettings() {
  const res = await fetch(`${API_BASE}/config`);
  const data = await res.json();
  
  selProvider = data.config.provider || 'groq';
  
  const providers = [
    {id: 'groq', name: 'Groq', badge: 'FREE', bclass: 'badge-free', hint: 'Get key at <a href="https://console.groq.com" target="_blank">console.groq.com</a>'},
    {id: 'gemini', name: 'Google Gemini', badge: 'FREE', bclass: 'badge-free', hint: 'Get key at <a href="https://aistudio.google.com" target="_blank">aistudio.google.com</a>'},
    {id: 'openai', name: 'OpenAI', badge: 'PAID', bclass: 'badge-paid', hint: 'Requires credits at platform.openai.com'},
    {id: 'anthropic', name: 'Anthropic Claude', badge: 'PAID', bclass: 'badge-paid', hint: 'Requires credits at console.anthropic.com'},
    {id: 'ollama', name: 'Local Ollama', badge: 'OFFLINE', bclass: 'badge-offline', hint: 'Make sure Ollama is running (`ollama serve`)'}
  ];
  
  let html = '';
  providers.forEach(p => {
    html += `
      <div class="provider-btn ${selProvider === p.id ? 'selected' : ''}" onclick="selectProvider('${p.id}', '${p.hint}')">
        <span class="p-badge ${p.bclass}">${p.badge}</span>
        <div class="p-name">${p.name}</div>
      </div>
    `;
    if (selProvider === p.id) {
      document.getElementById('apiKeyHint').innerHTML = p.hint;
      if (p.id === 'ollama') {
        document.getElementById('apiKeySection').style.display = 'none';
      } else {
        document.getElementById('apiKeySection').style.display = 'block';
        document.getElementById('apiKeyInput').value = (data.config.api_keys && data.config.api_keys[p.id]) ? '********' : '';
      }
    }
  });
  
  document.getElementById('providerGrid').innerHTML = html;
}

function selectProvider(id, hint) {
  selProvider = id;
  document.querySelectorAll('.provider-btn').forEach(b => b.classList.remove('selected'));
  event.currentTarget.classList.add('selected');
  
  document.getElementById('apiKeyHint').innerHTML = hint;
  if (id === 'ollama') {
    document.getElementById('apiKeySection').style.display = 'none';
  } else {
    document.getElementById('apiKeySection').style.display = 'block';
    document.getElementById('apiKeyInput').value = '';
  }
}

async function saveSettings() {
  const apiKey = document.getElementById('apiKeyInput').value;
  const msg = document.getElementById('settings-msg');
  
  if (selProvider !== 'ollama' && (!apiKey || apiKey === '********')) {
    if(apiKey !== '********') {
      msg.innerHTML = '<span style="color:var(--danger)">Please enter an API key</span>';
      return;
    }
  }
  
  const btn = event.target;
  btn.innerHTML = '<span class="spinner"></span> Validating...';
  
  try {
    const res = await fetch(`${API_BASE}/config`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        provider: selProvider,
        api_key: apiKey === '********' ? '' : apiKey
      })
    });
    const data = await res.json();
    
    if (data.ok) {
      msg.innerHTML = '<span style="color:var(--success)">✅ Saved & Validated! VibeGuard is ready.</span>';
      setTimeout(() => window.location.reload(), 1500);
    } else {
      msg.innerHTML = `<span style="color:var(--danger)">❌ Validation failed: ${data.error}</span>`;
    }
  } catch(e) {
    msg.innerHTML = `<span style="color:var(--danger)">Error: ${e}</span>`;
  }
  
  btn.innerHTML = 'Save & Validate ✓';
}
