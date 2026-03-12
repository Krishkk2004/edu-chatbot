const API = '';
let token = localStorage.getItem('token') || '';

const authPage = document.getElementById('authPage');
const chatPage = document.getElementById('chatPage');

function setStatus(id, msg, ok = true) {
  const el = document.getElementById(id);
  el.textContent = msg || '';
  el.style.color = ok ? '#0a7a26' : '#c11f1f';
}

function showPanel(panel) {
  document.getElementById('loginPanel').classList.toggle('hidden', panel !== 'login');
  document.getElementById('signupPanel').classList.toggle('hidden', panel !== 'signup');
}

function addMessage(role, text) {
  const box = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = role === 'user' ? 'msg user' : 'msg bot';
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function renderSidebarHistory(items) {
  const list = document.getElementById('historyList');
  list.innerHTML = '';
  items.forEach((item) => {
    const row = document.createElement('div');
    row.className = 'history-item';
    row.textContent = `${item.role === 'user' ? 'You' : 'Bot'}: ${item.message.slice(0, 60)}`;
    list.appendChild(row);
  });
}

async function loadResources() {
  const res = await fetch('/api/resources');
  const data = await res.json();
  const root = document.getElementById('resources');
  root.innerHTML = '';
  data.resources.forEach((r) => {
    const el = document.createElement('div');
    el.className = 'resource-item';
    const isImage = [".png", ".jpg", ".jpeg", ".webp"].includes((r.file_type || "").toLowerCase());
    const label = isImage ? "View/Download" : "Download";
    el.innerHTML = `<b>${r.title}</b> | ${r.subject} | ${r.category} <a href="${r.download_url}" target="_blank">${label}</a>`;
    root.appendChild(el);
  });
}

async function loadMe() {
  const res = await fetch('/api/me', { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return false;
  const data = await res.json();
  document.getElementById('userEmail').textContent = data.user.email;
  return true;
}

async function loadHistory() {
  const res = await fetch('/api/chat-history', { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return;
  const data = await res.json();
  const box = document.getElementById('chatMessages');
  box.innerHTML = '';
  data.history.forEach((h) => addMessage(h.role, h.message));
  renderSidebarHistory(data.history);
}

async function enterChat() {
  authPage.classList.add('hidden');
  chatPage.classList.remove('hidden');
  await loadMe();
  await loadResources();
  await loadHistory();
}

async function login() {
  const email = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value;
  const res = await fetch(`${API}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  const data = await res.json();
  if (!res.ok) return setStatus('loginStatus', data.error, false);
  token = data.token;
  localStorage.setItem('token', token);
  setStatus('loginStatus', `Welcome ${data.user.name}`);
  await enterChat();
}

async function signup() {
  const name = document.getElementById('signupName').value.trim();
  const email = document.getElementById('signupEmail').value.trim();
  const password = document.getElementById('signupPassword').value;
  const confirm_password = document.getElementById('signupConfirm').value;
  const res = await fetch(`${API}/api/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password, confirm_password })
  });
  const data = await res.json();
  setStatus('signupStatus', data.message || data.error, res.ok);
  if (res.ok) showPanel('login');
}

async function sendMessage() {
  const input = document.getElementById('chatInput');
  const message = input.value.trim();
  if (!message) return;

  addMessage('user', message);
  input.value = '';

  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ message })
  });

  const data = await res.json();
  if (res.ok) {
    addMessage('assistant', data.reply);
    await loadHistory();
  } else {
    addMessage('assistant', data.error || 'Something went wrong.');
  }
}

document.getElementById('showSignup').addEventListener('click', (e) => {
  e.preventDefault();
  showPanel('signup');
});

document.getElementById('showLogin').addEventListener('click', (e) => {
  e.preventDefault();
  showPanel('login');
});

document.getElementById('loginBtn').addEventListener('click', login);
document.getElementById('signupBtn').addEventListener('click', signup);
document.getElementById('sendBtn').addEventListener('click', sendMessage);

document.getElementById('uploadForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const res = await fetch('/api/upload-resource', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData
  });
  const data = await res.json();
  setStatus('uploadStatus', data.message || data.error, res.ok);
  if (res.ok) {
    e.target.reset();
    await loadResources();
  }
});



document.getElementById('syncBtn').addEventListener('click', async () => {
  const res = await fetch('/api/sync-resources', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` }
  });
  const data = await res.json();
  setStatus('uploadStatus', data.message || data.error, res.ok);
  if (res.ok) await loadResources();
});
(async () => {
  if (token) {
    const ok = await loadMe();
    if (ok) {
      await enterChat();
      return;
    }
  }
  showPanel('login');
})();
