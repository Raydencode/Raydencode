import { Graph } from "./graph.js";

/* ---------------------------------------------------------------------
 * Tunables — the one place to adjust turn-taking feel.
 * ------------------------------------------------------------------- */
const SILENCE_TIMEOUT_MS = 900;        // how long you can go quiet before a turn ends
const LEVEL_POLL_INTERVAL_MS = 80;     // setInterval, not requestAnimationFrame — RAF dies in a backgrounded tab
const MIN_LISTEN_MS = 400;             // ignore silence-detection for this long after pressing the mic
const SILENCE_LEVEL = 0.025;           // RMS below this counts as "quiet"
const INTERIM_TRANSCRIBE_INTERVAL_MS = 2600; // how often to refresh the live caption while listening
const HISTORY_TURNS = 10;
const EXAMPLE_PROMPT_ROTATE_MS = 5000;

const EXAMPLE_PROMPTS = [
  "What's the status on Northfield Roasters?",
  "Plan my day",
  "Brief me",
  "Remember that Kestrel wants sold-out states handled gracefully",
  "What does Shopify Plus cost?",
  "What about the second one?",
];

/* ---------------------------------------------------------------------
 * State
 * ------------------------------------------------------------------- */
const state = {
  reactorState: "idle", // idle | listening | thinking | speaking
  sessionActive: false,
  muted: false,
  history: [],
  status: null,
  audioEl: null,
  mic: null, // { stream, ctx, analyser, recorder, chunks, levelTimer, quietSince, startedAt, lastInterimAt }
};

const el = (id) => document.getElementById(id);

/* ---------------------------------------------------------------------
 * Boot
 * ------------------------------------------------------------------- */
async function boot() {
  bindButtons();
  rotateExamplePrompts();
  await loadStatus();
  await loadGraphAndUI();
  drawReactor();
}

async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    const status = await res.json();
    state.status = status;
    renderBadges(status);
  } catch (e) {
    showDegrade("Can't reach the ULTRON server. Is main.py running?");
  }
}

function renderBadges(status) {
  const wrap = el("badges");
  wrap.innerHTML = "";
  wrap.appendChild(badge(status.mode === "demo" ? "DEMO" : "LIVE", "demo"));
  wrap.appendChild(badge("MODEL", status.llm_available ? "on" : "off"));
  wrap.appendChild(badge("VOICE", status.elevenlabs_available ? "on" : "off"));
  if (!status.llm_available) {
    showDegrade("No model connected — routing falls back to keyword + file matching. Add ANTHROPIC_API_KEY to .env for real conversation.");
  }
  if (!status.elevenlabs_available) {
    showDegrade("Voice isn't configured — add ELEVENLABS_API_KEY to .env to talk to ULTRON.");
  }
}

function badge(text, cls) {
  const span = document.createElement("span");
  span.className = `badge ${cls}`;
  span.textContent = text;
  return span;
}

let degradeTimer = null;
function showDegrade(msg) {
  const b = el("degrade-banner");
  b.textContent = msg;
  b.classList.add("show");
  clearTimeout(degradeTimer);
  degradeTimer = setTimeout(() => b.classList.remove("show"), 6000);
}

/* ---------------------------------------------------------------------
 * Graph + side panels
 * ------------------------------------------------------------------- */
let graph = null;

async function loadGraphAndUI() {
  const res = await fetch("/api/graph");
  const payload = await res.json();
  graph = new Graph(el("graph-canvas"), { onFocus: onNodeFocus });
  graph.setData(payload);
  renderFilters();
  renderHubs();
}

function renderFilters() {
  const wrap = el("filters-list");
  wrap.innerHTML = "";
  const counts = graph.typeCounts();
  for (const type of Object.keys(counts).sort()) {
    const row = document.createElement("div");
    row.className = "filter-row";
    row.innerHTML = `
      <span class="swatch" style="background:${colorForType(type)}"></span>
      <span class="label">${capitalize(type)}</span>
      <span class="count">${counts[type]}</span>
    `;
    row.addEventListener("click", () => {
      const active = row.classList.toggle("off");
      graph.setTypeActive(type, !active);
    });
    wrap.appendChild(row);
  }
}

function renderHubs() {
  const list = el("hubs-list");
  list.innerHTML = "";
  for (const n of graph.topHubs(10)) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="swatch" style="background:${colorForType(n.type)}"></span><span>${n.title}</span><span class="n">${n.degree}</span>`;
    li.addEventListener("click", () => graph.focusById(n.id));
    list.appendChild(li);
  }
}

function colorForType(t) {
  const map = { client: "#ff7a33", project: "#4fb3ff", invoice: "#63d47a", note: "#a79bff", proposal: "#ffd166" };
  return map[t] || "#9aa0a8";
}
function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

async function onNodeFocus(node) {
  const res = await fetch(`/api/note?id=${encodeURIComponent(node.id)}`);
  if (!res.ok) return;
  const note = await res.json();
  el("inspector-empty").style.display = "none";
  const box = el("inspector-note");
  box.style.display = "block";
  box.innerHTML = `
    <span class="type-pill" style="background:${colorForType(note.type)}22;color:${colorForType(note.type)}">${note.type}</span>
    <h3>${escapeHtml(note.title)}</h3>
    <div class="meta">${note.root} · ${note.links_in.length} in · ${note.links_out.length} out</div>
    <div class="content">${escapeHtml(note.content.slice(0, 1800))}</div>
  `;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------------------------------------------------------------------
 * Reactor HUD
 * ------------------------------------------------------------------- */
function drawReactor() {
  const canvas = el("reactor-canvas");
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  canvas.width = 140 * dpr;
  canvas.height = 140 * dpr;
  ctx.scale(dpr, dpr);

  const colors = { idle: "#55555e", listening: "#ff7a33", thinking: "#4fb3ff", speaking: "#58d68d" };

  function frame(t) {
    const cx = 70, cy = 70;
    ctx.clearRect(0, 0, 140, 140);
    const color = colors[state.reactorState];
    const pulse = state.reactorState === "idle" ? 0 : 1;
    const breathe = 1 + Math.sin(t / 700) * (0.03 + pulse * 0.05);

    for (let i = 0; i < 3; i++) {
      const r = (30 + i * 14) * breathe;
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.globalAlpha = state.reactorState === "idle" ? 0.15 : 0.35 - i * 0.08;
      ctx.lineWidth = 1.4;
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
    }

    if (state.reactorState === "thinking") {
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.globalAlpha = 0.9;
      ctx.lineWidth = 2.5;
      const start = t / 400;
      ctx.arc(cx, cy, 44, start, start + 1.4);
      ctx.stroke();
    }

    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.fillStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = state.reactorState === "idle" ? 4 : 20;
    ctx.arc(cx, cy, 10 * breathe, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function setReactorState(s) {
  state.reactorState = s;
  const label = el("reactor-state");
  label.textContent = s;
  label.className = s;
}

/* ---------------------------------------------------------------------
 * Chat pipeline (shared by typed input and voice)
 * ------------------------------------------------------------------- */
async function sendMessage(text, { fromVoice = false } = {}) {
  if (!text.trim()) return;
  setCaption(fromVoice ? `“${text}”` : "", fromVoice);
  el("ask-input").value = "";
  pushHistory("user", text);
  setReactorState("thinking");

  let result;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: state.history }),
    });
    result = await res.json();
  } catch (e) {
    showDegrade("Lost the connection to the server.");
    setReactorState("idle");
    return;
  }

  if (result.error) {
    showDegrade(result.error);
    setReactorState("idle");
    return;
  }

  pushHistory("assistant", result.speech);
  showCard(result.tool, result.card);
  setCaption(result.speech, false);

  if (!state.muted && result.speech) {
    await speak(result.speech);
  } else {
    afterTurnEnds();
  }
}

function pushHistory(role, content) {
  state.history.push({ role, content });
  if (state.history.length > HISTORY_TURNS * 2) {
    state.history = state.history.slice(-HISTORY_TURNS * 2);
  }
}

function showCard(tool, card) {
  const panel = el("card-panel");
  if (!card) { panel.classList.remove("show"); return; }
  el("card-title").textContent = tool || "result";
  el("card-body").textContent = JSON.stringify(card, null, 2);
  panel.classList.add("show");
}

function setCaption(text, live) {
  const c = el("caption-line");
  c.textContent = text;
  c.classList.toggle("live", !!live);
}

/* ---------------------------------------------------------------------
 * Voice out
 * ------------------------------------------------------------------- */
async function speak(text) {
  setReactorState("speaking");
  let res;
  try {
    res = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  } catch (e) {
    showDegrade("Couldn't reach ElevenLabs for speech.");
    afterTurnEnds();
    return;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    showDegrade(body.error || "Text-to-speech failed.");
    afterTurnEnds();
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  state.audioEl = audio;
  audio.addEventListener("ended", () => { URL.revokeObjectURL(url); state.audioEl = null; afterTurnEnds(); });
  audio.addEventListener("error", () => { state.audioEl = null; afterTurnEnds(); });
  try {
    await audio.play();
  } catch (e) {
    afterTurnEnds();
  }
}

function bargeIn() {
  if (state.audioEl) {
    state.audioEl.pause();
    state.audioEl = null;
  }
  if (state.sessionActive) startListening();
  else setReactorState("idle");
}

function afterTurnEnds() {
  if (state.sessionActive) startListening();
  else setReactorState("idle");
}

/* ---------------------------------------------------------------------
 * Voice in — MediaRecorder + AnalyserNode, no Web Speech API.
 * ------------------------------------------------------------------- */
async function startListening() {
  if (state.mic) stopListening({ cancel: true });

  if (!navigator.mediaDevices?.getUserMedia) {
    showDegrade("This browser can't access the microphone (no getUserMedia).");
    endSession();
    return;
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    showDegrade("Microphone blocked — allow access in the browser and press the mic again.");
    endSession();
    return;
  }

  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  const ctx = new AudioCtx();
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);

  const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
    .find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t));
  if (!window.MediaRecorder || !mimeType) {
    showDegrade("This browser can't record audio (no MediaRecorder).");
    stream.getTracks().forEach((t) => t.stop());
    endSession();
    return;
  }

  const recorder = new MediaRecorder(stream, { mimeType });
  const chunks = [];
  recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };

  state.mic = {
    stream, ctx, analyser, recorder, chunks, mimeType,
    quietSince: null, startedAt: performance.now(), lastInterimAt: performance.now(),
  };

  recorder.start(250);
  setReactorState("listening");
  el("bars").classList.add("active");
  setCaption("Listening…", true);

  const buffer = new Float32Array(analyser.fftSize);
  state.mic.levelTimer = setInterval(() => {
    const mic = state.mic;
    if (!mic) return;
    mic.analyser.getFloatTimeDomainData(buffer);
    let sum = 0;
    for (let i = 0; i < buffer.length; i++) sum += buffer[i] * buffer[i];
    const rms = Math.sqrt(sum / buffer.length);
    updateBars(rms);

    const now = performance.now();
    const elapsed = now - mic.startedAt;

    if (rms < SILENCE_LEVEL) {
      if (mic.quietSince === null) mic.quietSince = now;
      else if (elapsed > MIN_LISTEN_MS && now - mic.quietSince >= SILENCE_TIMEOUT_MS) {
        finalizeTurn();
        return;
      }
    } else {
      mic.quietSince = null;
    }

    if (now - mic.lastInterimAt >= INTERIM_TRANSCRIBE_INTERVAL_MS && mic.chunks.length) {
      mic.lastInterimAt = now;
      refreshInterimCaption();
    }
  }, LEVEL_POLL_INTERVAL_MS);
}

function updateBars(rms) {
  const bars = el("bars").children;
  const level = Math.min(1, rms * 12);
  for (let i = 0; i < bars.length; i++) {
    const wobble = 0.5 + Math.abs(Math.sin(i * 1.7 + performance.now() / 180));
    const h = Math.max(3, level * 22 * wobble);
    bars[i].style.height = `${h}px`;
  }
}

async function refreshInterimCaption() {
  const mic = state.mic;
  if (!mic) return;
  const blob = new Blob(mic.chunks, { type: mic.mimeType });
  try {
    const res = await fetch("/api/listen", { method: "POST", headers: { "Content-Type": mic.mimeType }, body: blob });
    if (!res.ok) return;
    const { transcript } = await res.json();
    if (transcript && state.mic === mic) setCaption(`“${transcript}”…`, true);
  } catch (e) {
    // interim caption is best-effort — say nothing and keep listening
  }
}

function finalizeTurn() {
  const mic = state.mic;
  if (!mic) return;
  clearInterval(mic.levelTimer);
  el("bars").classList.remove("active");
  updateBars(0);

  mic.recorder.onstop = async () => {
    mic.stream.getTracks().forEach((t) => t.stop());
    mic.ctx.close();
    state.mic = null;

    const blob = new Blob(mic.chunks, { type: mic.mimeType });
    if (blob.size < 800) { // essentially silence — nothing worth sending
      afterTurnEnds();
      return;
    }
    setReactorState("thinking");
    setCaption("Transcribing…", true);
    let transcript = "";
    try {
      const res = await fetch("/api/listen", { method: "POST", headers: { "Content-Type": mic.mimeType }, body: blob });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        showDegrade(body.error || "Couldn't transcribe that.");
        afterTurnEnds();
        return;
      }
      const data = await res.json();
      transcript = (data.transcript || "").trim();
    } catch (e) {
      showDegrade("Couldn't reach ElevenLabs to transcribe.");
      afterTurnEnds();
      return;
    }

    if (!transcript) { afterTurnEnds(); return; }
    await sendMessage(transcript, { fromVoice: true });
  };
  mic.recorder.stop();
}

function stopListening({ cancel } = {}) {
  const mic = state.mic;
  if (!mic) return;
  clearInterval(mic.levelTimer);
  el("bars").classList.remove("active");
  if (cancel) {
    mic.recorder.onstop = () => {
      mic.stream.getTracks().forEach((t) => t.stop());
      mic.ctx.close();
    };
    mic.recorder.stop();
    state.mic = null;
  }
}

function endSession() {
  state.sessionActive = false;
  el("mic-btn").classList.remove("active");
  setReactorState("idle");
  setCaption("", false);
}

/* ---------------------------------------------------------------------
 * Buttons + keys
 * ------------------------------------------------------------------- */
function bindButtons() {
  el("ask-form").addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(el("ask-input").value);
  });

  el("mic-btn").addEventListener("click", onMicPress);

  el("mute-btn").addEventListener("click", () => {
    state.muted = !state.muted;
    el("mute-btn").classList.toggle("muted", state.muted);
    if (state.muted && state.audioEl) { state.audioEl.pause(); state.audioEl = null; }
  });

  el("brief-btn").addEventListener("click", () => sendMessage("brief me"));
  el("plan-btn").addEventListener("click", () => sendMessage("plan my day"));
  el("memory-btn").addEventListener("click", showMemory);
  el("card-close").addEventListener("click", () => el("card-panel").classList.remove("show"));

  window.addEventListener("keydown", (e) => {
    if (document.activeElement === el("ask-input")) {
      if (e.key === "Escape") el("ask-input").blur();
      return;
    }
    if (e.code === "Space") { e.preventDefault(); onMicPress(); }
    if (e.key === "Escape") { e.preventDefault(); hardStop(); }
  });
}

function onMicPress() {
  if (state.reactorState === "speaking") { bargeIn(); return; }
  if (state.sessionActive) {
    endSession();
    stopListening({ cancel: true });
  } else {
    state.sessionActive = true;
    el("mic-btn").classList.add("active");
    startListening();
  }
}

function hardStop() {
  if (state.audioEl) { state.audioEl.pause(); state.audioEl = null; }
  stopListening({ cancel: true });
  endSession();
}

async function showMemory() {
  const res = await fetch("/api/memory");
  const { memories } = await res.json();
  el("card-title").textContent = "memory";
  el("card-body").textContent = memories.length
    ? memories.map((m) => `${m.file}\n${m.fact}`).join("\n\n")
    : "Nothing remembered yet.";
  el("card-panel").classList.add("show");
}

function rotateExamplePrompts() {
  let i = 0;
  const input = el("ask-input");
  input.placeholder = EXAMPLE_PROMPTS[0];
  setInterval(() => {
    i = (i + 1) % EXAMPLE_PROMPTS.length;
    if (document.activeElement !== input) input.placeholder = EXAMPLE_PROMPTS[i];
  }, EXAMPLE_PROMPT_ROTATE_MS);
}

// exposed for debugging in devtools — not used by the app itself
window.ULTRON = { get graph() { return graph; }, state };

boot();
