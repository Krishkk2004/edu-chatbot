const API = '';
let token = localStorage.getItem('token') || '';

function setStatus(id, msg, good=true) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.style.color = good ? 'green' : 'crimson';
}

async function signup() {
  const name = document.getElementById('name').value;
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  const res = await fetch(`${API}/api/signup`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name,email,password})});
  const data = await res.json();
  setStatus('authStatus', data.message || data.error, res.ok);
}

async function login() {
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  const res = await fetch(`${API}/api/login`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email,password})});
  const data = await res.json();
  if (res.ok) {
    token = data.token;
    localStorage.setItem('token', token);
    setStatus('authStatus', `Welcome ${data.user.name}`);
    document.getElementById('resourceCard').classList.remove('hidden');
    document.getElementById('chatCard').classList.remove('hidden');
    loadHistory();
  } else {
    setStatus('authStatus', data.error, false);
  }
}

async function loadResources() {
  const res = await fetch('/api/resources');
  const data = await res.json();
  const root = document.getElementById('resources');
  root.innerHTML = '';
  data.resources.forEach(r => {
    const el = document.createElement('div');
    el.className = 'resource-item';
    el.innerHTML = `<b>${r.title}</b> - ${r.category} <a href="${r.download_url}">Download PDF</a>`;
    root.appendChild(el);
  });
}

document.getElementById('uploadForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const res = await fetch('/api/upload-resource', {method:'POST', headers:{Authorization:`Bearer ${token}`}, body: formData});
  const data = await res.json();
  setStatus('uploadStatus', data.message || data.error, res.ok);
  if (res.ok) loadResources();
});

function renderMsg(role, text) {
  const c = document.getElementById('chatHistory');
  const div = document.createElement('div');
  div.className = role === 'user' ? 'msg-user' : 'msg-assistant';
  div.textContent = text;
  c.appendChild(div);
  c.scrollTop = c.scrollHeight;
}

async function loadHistory() {
  const res = await fetch('/api/chat-history', {headers:{Authorization:`Bearer ${token}`}});
  if (!res.ok) return;
  const data = await res.json();
  const c = document.getElementById('chatHistory');
  c.innerHTML = '';
  data.history.forEach(h => renderMsg(h.role, h.message));
}

async function sendMessage() {
  const input = document.getElementById('message');
  const message = input.value.trim();
  if (!message) return;
  renderMsg('user', message);
  input.value = '';
  const res = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json', Authorization:`Bearer ${token}`}, body: JSON.stringify({message})});
  const data = await res.json();
  if (res.ok) renderMsg('assistant', data.reply);
}

loadResources();
if (token) {
  document.getElementById('resourceCard').classList.remove('hidden');
  document.getElementById('chatCard').classList.remove('hidden');
  loadHistory();
}
