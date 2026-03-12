let token = localStorage.getItem('token') || '';
let currentUser = null;

const byId = (id) => document.getElementById(id);

function setStatus(id, msg, good = true) {
  const el = byId(id);
  el.textContent = msg;
  el.style.color = good ? '#1d7d39' : '#c62828';
}

function showView(name) {
  byId('loginView').classList.toggle('hidden', name !== 'login');
  byId('signupView').classList.toggle('hidden', name !== 'signup');
  byId('chatView').classList.toggle('hidden', name !== 'chat');
}

function escapeHtml(text) {
  return text.replace(/[&<>'"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[ch]));
}

function withLinks(text) {
  return escapeHtml(text).replace(/(\/files\/[\w.-]+)/g, '<a href="$1" target="_blank">Download</a>');
}

function renderMsg(role, text) {
  const wrap = byId('chatHistory');
  const div = document.createElement('div');
  div.className = role === 'user' ? 'msg user' : 'msg bot';
  div.innerHTML = withLinks(text);
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
}

async function signup() {
  const name = byId('signupName').value.trim();
  const email = byId('signupEmail').value.trim();
  const password = byId('signupPassword').value;
  const confirm = byId('signupConfirm').value;

  if (password !== confirm) {
    setStatus('signupStatus', 'Password and confirm password must match', false);
    return;
  }

  const res = await fetch('/api/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  });
  const data = await res.json();
  setStatus('signupStatus', data.message || data.error, res.ok);
  if (res.ok) showView('login');
}

async function login() {
  const email = byId('loginEmail').value.trim();
  const password = byId('loginPassword').value;
  const res = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();

  if (!res.ok) {
    setStatus('loginStatus', data.error || 'Login failed', false);
    return;
  }

  token = data.token;
  currentUser = data.user;
  localStorage.setItem('token', token);
  byId('userEmail').textContent = currentUser.email;
  showView('chat');
  await loadHistory();
}

async function loadHistory() {
  const res = await fetch('/api/chat-history', { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    logout();
    return;
  }
  const data = await res.json();
  byId('chatHistory').innerHTML = '';
  byId('chatSessions').innerHTML = '';

  const userPrompts = [];
  data.history.forEach((h) => {
    renderMsg(h.role, h.message);
    if (h.role === 'user') userPrompts.push(h.message);
  });

  userPrompts.slice(-15).reverse().forEach((msg, idx) => {
    const item = document.createElement('div');
    item.className = 'session-item';
    item.textContent = `${idx + 1}. ${msg.slice(0, 40)}`;
    byId('chatSessions').appendChild(item);
  });
}

async function sendMessage() {
  const input = byId('message');
  const message = input.value.trim();
  if (!message) return;

  input.value = '';
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  });
  const data = await res.json();
  if (res.ok) {
    await loadHistory();
  } else {
    renderMsg('assistant', data.error || 'Unable to send message now.');
  }
}

async function bootstrapAuth() {
  if (!token) {
    showView('login');
    return;
  }

  const res = await fetch('/api/me', { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    logout();
    showView('login');
    return;
  }
  const data = await res.json();
  currentUser = data.user;
  byId('userEmail').textContent = currentUser.email;
  showView('chat');
  await loadHistory();
}

function logout() {
  localStorage.removeItem('token');
  token = '';
  currentUser = null;
  showView('login');
}

function toggleSidebar() {
  byId('sidebar').classList.toggle('collapsed');
}

byId('gotoSignup').addEventListener('click', (e) => { e.preventDefault(); showView('signup'); });
byId('gotoLogin').addEventListener('click', (e) => { e.preventDefault(); showView('login'); });
byId('signupBtn').addEventListener('click', signup);
byId('loginBtn').addEventListener('click', login);
byId('sendBtn').addEventListener('click', sendMessage);
byId('message').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendMessage(); });
byId('logoutBtn').addEventListener('click', logout);
byId('toggleSidebarBtn').addEventListener('click', toggleSidebar);

bootstrapAuth();
