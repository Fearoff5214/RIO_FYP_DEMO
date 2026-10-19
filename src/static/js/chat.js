/**
 * DefectScan AI – Chat UI logic
 * Handles: message rendering, file attachment, API calls, settings, samples, lightbox
 */

(function () {
  'use strict';

  // ── DOM references ──────────────────────────────────────────────
  const chatArea     = document.getElementById('chatArea');
  const fileInput    = document.getElementById('fileInput');
  const textInput    = document.getElementById('textInput');
  const sendBtn      = document.getElementById('sendBtn');
  const attachPreview= document.getElementById('attachPreview');
  const attachName   = document.getElementById('attachName');
  const attachRemove = document.getElementById('attachRemove');
  const confSlider   = document.getElementById('confSlider');
  const confVal      = document.getElementById('confVal');
  const esp32Url     = document.getElementById('esp32Url');
  const clearChatBtn = document.getElementById('clearChat');
  const lightbox     = document.getElementById('lightbox');
  const lightboxImg  = document.getElementById('lightboxImg');
  const lightboxClose= document.getElementById('lightboxClose');
  const sidebar      = document.getElementById('sidebar');
  const menuBtn      = document.getElementById('menuBtn');
  const sidebarToggle= document.getElementById('sidebarToggle');
  const navChat      = document.getElementById('navChat');
  const navSettings  = document.getElementById('navSettings');
  const settingsPanel= document.getElementById('settingsPanel');
  const mainEl       = document.getElementById('main');

  let selectedFile = null;
  let chatInner    = null;   // created on first render

  // ── Utilities ───────────────────────────────────────────────────

  function now() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function scrollBottom() {
    chatArea.scrollTo({ top: chatArea.scrollHeight, behavior: 'smooth' });
  }

  function ensureChatInner() {
    if (!chatInner) {
      chatInner = document.createElement('div');
      chatInner.className = 'chat-inner';
      chatArea.innerHTML = '';
      chatArea.appendChild(chatInner);
    }
  }

  // ── Welcome card ─────────────────────────────────────────────────

  function renderWelcome() {
    chatArea.innerHTML = `
      <div class="chat-inner">
        <div class="welcome-card">
          <div class="welcome-icon">⬡</div>
          <div class="welcome-title">DefectScan AI</div>
          <div class="welcome-sub">
            Attach a sheet-metal image or short video using the&nbsp;📎&nbsp;button,
            and I'll inspect it for surface defects using YOLOv8.
          </div>
          <div class="welcome-chips">
            <span class="welcome-chip">Crazing</span>
            <span class="welcome-chip">Inclusion</span>
            <span class="welcome-chip">Patches</span>
            <span class="welcome-chip">Pitted surface</span>
            <span class="welcome-chip">Rolled-in scale</span>
            <span class="welcome-chip">Scratches</span>
          </div>
        </div>
      </div>`;
    chatInner = chatArea.querySelector('.chat-inner');
  }

  renderWelcome();

  // ── Message builders ─────────────────────────────────────────────

  function appendMessage(role, content) {
    ensureChatInner();

    const row = document.createElement('div');
    row.className = `msg-row ${role}`;

    const avatarHtml = role === 'ai'
      ? `<div class="avatar ai">AI</div>`
      : `<div class="avatar user">You</div>`;

    row.innerHTML = `
      ${avatarHtml}
      <div class="bubble-wrap">
        <div class="bubble">${content}</div>
        <span class="msg-time">${now()}</span>
      </div>`;

    chatInner.appendChild(row);
    scrollBottom();
    return row;
  }

  function appendTyping() {
    ensureChatInner();
    const row = document.createElement('div');
    row.className = 'msg-row ai typing-row';
    row.innerHTML = `
      <div class="avatar ai">AI</div>
      <div class="typing-bubble">
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
      </div>`;
    chatInner.appendChild(row);
    scrollBottom();
    return row;
  }

  // Build user bubble: optional thumbnail + optional text
  function buildUserContent(text, previewSrc) {
    let html = '';
    if (previewSrc) {
      html += `<img src="${escapeHtml(previewSrc)}" class="user-thumb" alt="attachment" />`;
    }
    if (text) html += escapeHtml(text);
    return html || '📎 Sent a file';
  }

  // Build AI result bubble
  function buildResultContent(data) {
    const passClass = data.passed ? 'pass' : 'fail';
    const passIcon  = data.passed ? '✅' : '❌';
    const passLabel = data.passed ? 'PASS' : 'FAIL';

    let countsHtml = '';
    if (!data.passed && data.counts && Object.keys(data.counts).length) {
      const pills = Object.entries(data.counts)
        .map(([name, n]) =>
          `<span class="count-pill">
             <span class="count-pill-name">${escapeHtml(name)}</span>
             <span class="count-pill-n">×${n}</span>
           </span>`)
        .join('');
      countsHtml = `<div class="counts-grid">${pills}</div>`;
    }

    const imgHtml = data.annotated_b64
      ? `<img src="${data.annotated_b64}" class="annotated-img" alt="annotated frame" data-full="${data.annotated_b64}" />`
      : '';

    return `
      <div class="result-card">
        <span class="verdict-badge ${passClass}">
          <span class="verdict-icon">${passIcon}</span>${passLabel}
        </span>
        <p class="result-message">${escapeHtml(data.message)}</p>
        ${countsHtml}
        ${imgHtml}
      </div>`;
  }

  // ── Lightbox ─────────────────────────────────────────────────────

  function openLightbox(src) {
    lightboxImg.src = src;
    lightbox.classList.add('open');
  }

  lightboxClose.addEventListener('click', () => lightbox.classList.remove('open'));
  lightbox.addEventListener('click', e => {
    if (e.target === lightbox) lightbox.classList.remove('open');
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') lightbox.classList.remove('open');
  });

  // Delegate lightbox clicks from dynamically added images
  chatArea.addEventListener('click', e => {
    const img = e.target.closest('[data-full]');
    if (img) openLightbox(img.dataset.full);
  });

  // ── File attachment ───────────────────────────────────────────────

  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) {
      selectedFile = fileInput.files[0];
      attachName.textContent = selectedFile.name;
      attachPreview.style.display = 'flex';
    }
  });

  attachRemove.addEventListener('click', () => {
    selectedFile = null;
    fileInput.value = '';
    attachPreview.style.display = 'none';
  });

  // ── Sidebar & settings toggles ────────────────────────────────────

  function isMobile() { return window.innerWidth <= 768; }

  function toggleSidebar() {
    if (isMobile()) {
      sidebar.classList.toggle('open');
    } else {
      sidebar.classList.toggle('collapsed');
      mainEl.classList.toggle('expanded');
    }
  }

  menuBtn.addEventListener('click', toggleSidebar);
  sidebarToggle.addEventListener('click', toggleSidebar);

  navSettings.addEventListener('click', () => {
    const open = settingsPanel.classList.toggle('open');
    navSettings.classList.toggle('active', open);
    navChat.classList.toggle('active', !open);
  });

  navChat.addEventListener('click', () => {
    settingsPanel.classList.remove('open');
    navChat.classList.add('active');
    navSettings.classList.remove('active');
  });

  // Close sidebar on mobile when tapping outside
  document.addEventListener('click', e => {
    if (isMobile() && sidebar.classList.contains('open')) {
      if (!sidebar.contains(e.target) && !menuBtn.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    }
  });

  // ── Confidence slider ─────────────────────────────────────────────

  confSlider.addEventListener('input', () => {
    confVal.textContent = parseFloat(confSlider.value).toFixed(2);
  });

  // ── Clear chat ────────────────────────────────────────────────────

  clearChatBtn.addEventListener('click', () => {
    chatInner = null;
    renderWelcome();
  });

  // ── Bundled samples ───────────────────────────────────────────────

  document.querySelectorAll('.sample-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.name;
      sendSample(name);
      // Close sidebar on mobile after picking
      if (isMobile()) sidebar.classList.remove('open');
    });
  });

  async function sendSample(name) {
    // User bubble (no preview thumb for sample)
    appendMessage('user', `📎 Sent sample: <strong>${escapeHtml(name)}</strong>`);
    await runInference({ sample_name: name });
  }

  // ── Send logic ────────────────────────────────────────────────────

  async function handleSend() {
    const text = textInput.value.trim();

    if (!selectedFile && !text) return;

    // If only text (no file) — conversational fallback
    if (!selectedFile) {
      appendMessage('user', escapeHtml(text));
      textInput.value = '';
      appendMessage('ai', 'Please attach an image or video using the 📎 button so I can inspect it for defects.');
      return;
    }

    // Read file for thumbnail preview
    const previewSrc = await filePreview(selectedFile);
    appendMessage('user', buildUserContent(text, previewSrc));

    textInput.value = '';
    const fileToSend = selectedFile;
    selectedFile = null;
    fileInput.value = '';
    attachPreview.style.display = 'none';

    await runInference({ file: fileToSend });
  }

  async function runInference(payload) {
    sendBtn.disabled = true;
    const typingRow = appendTyping();

    try {
      const formData = new FormData();
      formData.append('confidence', confSlider.value);
      formData.append('esp32_url', esp32Url.value.trim());

      if (payload.file) {
        formData.append('file', payload.file);
      } else if (payload.sample_name) {
        formData.append('sample_name', payload.sample_name);
      }

      const resp = await fetch('/analyze', { method: 'POST', body: formData });
      const data = await resp.json();

      typingRow.remove();

      if (!resp.ok || data.error) {
        appendMessage('ai', `⚠️ ${escapeHtml(data.error || 'An error occurred.')} Please try again.`);
        return;
      }

      appendMessage('ai', buildResultContent(data));

    } catch (err) {
      typingRow.remove();
      appendMessage('ai', '⚠️ Network error — is the server running?');
    } finally {
      sendBtn.disabled = false;
    }
  }

  // Resolve a File object to a data-URI preview (shown in user bubble)
  function filePreview(file) {
    return new Promise(resolve => {
      const ext = file.name.split('.').pop().toLowerCase();
      const videoExts = ['mp4', 'avi', 'mov'];
      if (videoExts.includes(ext)) {
        // For videos use a video element to grab a thumbnail frame
        const video = document.createElement('video');
        video.muted = true;
        video.preload = 'auto';
        const url = URL.createObjectURL(file);
        video.src = url;
        video.addEventListener('loadeddata', () => {
          video.currentTime = 0;
        });
        video.addEventListener('seeked', () => {
          const canvas = document.createElement('canvas');
          canvas.width  = video.videoWidth  || 320;
          canvas.height = video.videoHeight || 240;
          canvas.getContext('2d').drawImage(video, 0, 0);
          URL.revokeObjectURL(url);
          resolve(canvas.toDataURL('image/jpeg', 0.7));
        });
        video.addEventListener('error', () => { URL.revokeObjectURL(url); resolve(null); });
        // fallback: seeked may never fire on some browsers for 0
        setTimeout(() => { try { video.currentTime = 0.01; } catch(_) {} }, 100);
      } else {
        const reader = new FileReader();
        reader.onload = e => resolve(e.target.result);
        reader.onerror = () => resolve(null);
        reader.readAsDataURL(file);
      }
    });
  }

  // ── Event listeners ───────────────────────────────────────────────

  sendBtn.addEventListener('click', handleSend);

  textInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

})();
