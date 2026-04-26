// Shared helpers
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

function logLine(container, text, cls = '') {
  if (!container) return;
  const div = document.createElement('div');
  const ts = new Date().toTimeString().slice(0, 8);
  div.innerHTML = `<span class="ts">[${ts}]</span><span class="${cls}">${text}</span>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

async function api(url, body = null) {
  const opts = {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
  };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  return { status: r.status, data };
}

// Grab a JPEG frame from a <video>, return base64 (no data: prefix for small payloads, but with for readability)
function snapFrame(video, w = 480, h = 360, quality = 0.85) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const ctx = c.getContext('2d');
  // undo CSS mirror so server sees normal orientation
  ctx.save();
  ctx.translate(w, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, 0, 0, w, h);
  ctx.restore();
  return c.toDataURL('image/jpeg', quality);
}

async function startWebcam(videoEl, overlayEl) {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480, facingMode: 'user' },
      audio: false,
    });
    videoEl.srcObject = stream;
    await videoEl.play();
    if (overlayEl) {
      overlayEl.classList.remove('off');
      overlayEl.innerHTML = '<span class="live-dot"></span>CAM LIVE';
    }
    return stream;
  } catch (e) {
    if (overlayEl) {
      overlayEl.classList.add('off');
      overlayEl.textContent = 'CAM DENIED';
    }
    throw e;
  }
}

function stopWebcam(stream) {
  if (stream) stream.getTracks().forEach(t => t.stop());
}
