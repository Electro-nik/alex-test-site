'use strict';

const $ = (selector) => document.querySelector(selector);
const clientId = (() => {
  let id = localStorage.getItem('lan-hub-client');
  if (!id) {
    id = 'device_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem('lan-hub-client', id);
  }
  return id;
})();

const nickname = $('#nickname');
nickname.value = localStorage.getItem('lan-hub-name') || '';
nickname.addEventListener('input', () => localStorage.setItem('lan-hub-name', nickname.value));

let seenMessages = '';
let loading = false;
let toastTimeout;

function toast(message, isError = false) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.toggle('error', isError);
  el.classList.add('visible');
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => el.classList.remove('visible'), 2700);
}

async function api(endpoint, payload) {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const json = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(json.error || 'Помилка сервера.');
  return json;
}

function displayTime(isoTime) {
  const date = new Date(isoTime);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' });
}

function renderMessages(messages) {
  const signature = messages.map(m => m.id).join(',');
  if (signature === seenMessages) return;
  const feed = $('#chat-feed');
  const scrollBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 100;
  const initial = seenMessages === '';
  seenMessages = signature;
  feed.replaceChildren();
  if (messages.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'loading-state';
    empty.textContent = 'Поки порожньо. Напиши перше повідомлення!';
    feed.append(empty);
    return;
  }
  for (const msg of messages) {
    const row = document.createElement('div');
    row.className = 'chat-item';
    const avatar = document.createElement('div');
    avatar.className = 'chat-avatar accent-' + (msg.id % 4);
    avatar.textContent = [...msg.name][0].toUpperCase();
    const content = document.createElement('div');
    content.className = 'chat-item-body';
    const details = document.createElement('div');
    details.className = 'chat-details';
    const name = document.createElement('strong');
    name.textContent = msg.name;
    const time = document.createElement('time');
    time.textContent = displayTime(msg.created_at);
    const bubble = document.createElement('div');
    bubble.className = 'chat-text';
    bubble.textContent = msg.body; // textContent захищає від HTML/JS у повідомленнях
    details.append(name, time);
    content.append(details, bubble);
    row.append(avatar, content);
    feed.append(row);
  }
  if (initial || scrollBottom) feed.scrollTop = feed.scrollHeight;
}

function renderPoll(votes, myVote) {
  const total = Object.values(votes).reduce((sum, value) => sum + value, 0);
  $('#vote-total').textContent = total + ' голосів загалом';
  for (const item of document.querySelectorAll('.poll-option')) {
    const n = votes[item.dataset.choice] || 0;
    item.querySelector('.vote-count').textContent = n;
    item.querySelector('.poll-fill').style.width = (total ? n / total * 100 : 0) + '%';
    item.classList.toggle('selected', myVote === item.dataset.choice);
  }
}

function renderReactions(reactions) {
  for (const button of document.querySelectorAll('.reaction')) {
    button.querySelector('b').textContent = reactions[button.dataset.emoji] || 0;
  }
}

async function loadState() {
  if (loading || document.hidden) return;
  loading = true;
  try {
    const response = await fetch('/api/state?client_id=' + encodeURIComponent(clientId), { cache: 'no-store' });
    if (!response.ok) throw new Error('Сервер недоступний');
    const state = await response.json();
    renderMessages(state.messages);
    renderPoll(state.votes, state.my_vote);
    renderReactions(state.reactions);
    $('#online-count').textContent = state.online;
    $('#connection-dot').classList.remove('offline');
    $('#connection-text').textContent = 'Мережа онлайн';
  } catch {
    $('#connection-dot').classList.add('offline');
    $('#connection-text').textContent = 'Немає зв’язку';
  } finally {
    loading = false;
  }
}

async function ping() {
  try { await api('/api/ping', { client_id: clientId }); } catch { /* loadState покаже стан підключення */ }
}

$('#chat-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('#send-button');
  const name = nickname.value.trim();
  const body = $('#message').value.trim();
  if (!name || !body) return;
  button.disabled = true;
  try {
    await api('/api/message', { name, body });
    $('#message').value = '';
    await loadState();
    toast('Повідомлення надіслано ✨');
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    $('#message').focus();
  }
});

for (const button of document.querySelectorAll('.poll-option')) {
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      await api('/api/vote', { client_id: clientId, choice: button.dataset.choice });
      await loadState();
      toast('Твій голос враховано!');
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
}

for (const button of document.querySelectorAll('.reaction')) {
  button.addEventListener('click', async () => {
    try {
      await api('/api/reaction', { emoji: button.dataset.emoji });
      button.classList.remove('pop');
      void button.offsetWidth;
      button.classList.add('pop');
      await loadState();
    } catch (error) {
      toast(error.message, true);
    }
  });
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) { ping(); loadState(); }
});

ping().then(loadState);
setInterval(loadState, 2500);
setInterval(() => { if (!document.hidden) ping(); }, 10000);
