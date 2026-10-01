const state = {
  sounds: [],
  selected: [],
  mixVoices: [],
  bufferCache: new Map(),
  mixRestartTimer: null,
};

const list = document.querySelector("#audio-list");
const template = document.querySelector("#audio-card-template");
const status = document.querySelector("#status");
const empty = document.querySelector("#empty");
const filter = document.querySelector("#filter");
const recipeLayers = document.querySelector("#recipe-layers");
const layerCount = document.querySelector("#layer-count");
const downloadRecipe = document.querySelector("#download-recipe");
const intent = document.querySelector("#intent");
const previewMixButton = document.querySelector("#preview-mix");
const stopMixButton = document.querySelector("#stop-mix");

const AudioContextClass = window.AudioContext || window.webkitAudioContext;
const audioContext = new AudioContextClass();

function formatDuration(ms) {
  const seconds = ms / 1000;
  return (seconds < 10 ? seconds.toFixed(2) : seconds.toFixed(1)) + "s";
}

function escapeRecipeId(value) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "sound-effect";
}

function stopIndividualAuditions() {
  document.querySelectorAll("audio").forEach(function (audio) {
    audio.pause();
    audio.currentTime = 0;
  });
  document.querySelectorAll(".play").forEach(function (button) {
    button.textContent = "▶ Play";
  });
}

function stopMix() {
  if (state.mixRestartTimer) {
    clearTimeout(state.mixRestartTimer);
    state.mixRestartTimer = null;
  }

  state.mixVoices.forEach(function (voice) {
    try {
      voice.source.stop();
    } catch (error) {
      // Already stopped.
    }
  });
  state.mixVoices = [];
  previewMixButton.textContent = "▶ Preview mix";
  stopMixButton.disabled = true;
}

function stopAll() {
  stopIndividualAuditions();
  stopMix();
}

async function getAudioBuffer(url) {
  if (!state.bufferCache.has(url)) {
    const promise = fetch(url)
      .then(function (response) {
        if (!response.ok) throw new Error("Could not load " + url);
        return response.arrayBuffer();
      })
      .then(function (arrayBuffer) {
        return audioContext.decodeAudioData(arrayBuffer);
      });
    state.bufferCache.set(url, promise);
  }
  return state.bufferCache.get(url);
}

async function drawWaveform(canvas, url) {
  if (canvas.dataset.loaded === "true") return;
  canvas.dataset.loaded = "true";

  try {
    const buffer = await getAudioBuffer(url);
    const data = buffer.getChannelData(0);
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    const middle = height / 2;
    const bucket = Math.max(1, Math.floor(data.length / width));

    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = "#cceb67";
    ctx.lineWidth = 1;
    ctx.beginPath();

    for (let x = 0; x < width; x += 1) {
      const start = x * bucket;
      let peak = 0;
      for (let i = start; i < Math.min(start + bucket, data.length); i += 1) {
        peak = Math.max(peak, Math.abs(data[i]));
      }
      const amplitude = peak * (height * 0.42);
      ctx.moveTo(x + 0.5, middle - amplitude);
      ctx.lineTo(x + 0.5, middle + amplitude);
    }
    ctx.stroke();
  } catch (error) {
    canvas.dataset.loaded = "error";
  }
}

const waveformObserver = new IntersectionObserver(function (entries) {
  entries.forEach(function (entry) {
    if (!entry.isIntersecting) return;
    const canvas = entry.target;
    drawWaveform(canvas, canvas.dataset.url);
    waveformObserver.unobserve(canvas);
  });
}, { rootMargin: "220px" });

function hasSoloLayer() {
  return state.selected.some(function (layer) {
    return layer.solo;
  });
}

function isLayerAudible(layer) {
  if (layer.muted) return false;
  return !hasSoloLayer() || layer.solo;
}

function effectiveGain(layer) {
  return isLayerAudible(layer) ? layer.gain : 0;
}

function applyLiveGains() {
  state.mixVoices.forEach(function (voice) {
    const layer = state.selected.find(function (candidate) {
      return candidate.sound.relative_path === voice.path;
    });
    if (!layer) return;
    voice.gainNode.gain.setTargetAtTime(
      effectiveGain(layer),
      audioContext.currentTime,
      0.01
    );
  });
}

async function previewMix() {
  if (state.selected.length === 0) return;

  stopIndividualAuditions();
  stopMix();
  await audioContext.resume();

  previewMixButton.disabled = true;
  previewMixButton.textContent = "Loading…";

  try {
    const loaded = await Promise.all(
      state.selected.map(async function (layer) {
        return {
          layer: layer,
          buffer: await getAudioBuffer(layer.sound.url),
        };
      })
    );

    const startAt = audioContext.currentTime + 0.05;
    state.mixVoices = loaded.map(function (entry) {
      const source = audioContext.createBufferSource();
      const gainNode = audioContext.createGain();
      source.buffer = entry.buffer;
      gainNode.gain.value = effectiveGain(entry.layer);
      source.connect(gainNode);
      gainNode.connect(audioContext.destination);
      source.start(startAt + entry.layer.offset_ms / 1000);

      const voice = {
        path: entry.layer.sound.relative_path,
        source: source,
        gainNode: gainNode,
      };
      source.onended = function () {
        state.mixVoices = state.mixVoices.filter(function (candidate) {
          return candidate.source !== source;
        });
        if (state.mixVoices.length === 0) {
          previewMixButton.textContent = "▶ Preview mix";
          stopMixButton.disabled = true;
        }
      };
      return voice;
    });

    previewMixButton.textContent = "↻ Replay mix";
    stopMixButton.disabled = false;
  } catch (error) {
    status.textContent = "Mix preview failed: " + error.message;
    stopMix();
  } finally {
    previewMixButton.disabled = state.selected.length === 0;
  }
}

function scheduleMixRestart() {
  if (state.mixVoices.length === 0) return;
  if (state.mixRestartTimer) clearTimeout(state.mixRestartTimer);
  state.mixRestartTimer = setTimeout(function () {
    state.mixRestartTimer = null;
    previewMix();
  }, 120);
}

function makeLayer(sound) {
  return {
    sound: sound,
    gain: 1.0,
    offset_ms: 0,
    muted: false,
    solo: false,
  };
}

function renderSounds(sounds) {
  list.replaceChildren();

  sounds.forEach(function (sound) {
    const node = template.content.cloneNode(true);
    const card = node.querySelector(".audio-card");
    const audio = node.querySelector("audio");
    const play = node.querySelector(".play");
    const add = node.querySelector(".add");
    const canvas = node.querySelector(".waveform");

    node.querySelector(".file-name").textContent = sound.name;
    node.querySelector(".file-path").textContent = sound.relative_path;
    node.querySelector(".duration").textContent = formatDuration(sound.duration_ms);
    node.querySelector(".meta").textContent =
      String(sound.sample_rate) + " Hz · " + String(sound.channels) + "ch";
    audio.src = sound.url;
    canvas.dataset.url = sound.url;

    play.addEventListener("click", async function () {
      if (!audio.paused) {
        audio.pause();
        audio.currentTime = 0;
        play.textContent = "▶ Play";
        return;
      }

      stopAll();
      await audioContext.resume();
      await audio.play();
      play.textContent = "■ Stop";
    });

    audio.addEventListener("ended", function () {
      play.textContent = "▶ Play";
    });

    add.addEventListener("click", function () {
      const exists = state.selected.some(function (layer) {
        return layer.sound.relative_path === sound.relative_path;
      });
      if (exists || state.selected.length >= 4) return;
      state.selected.push(makeLayer(sound));
      renderRecipe();
    });

    card.dataset.search = (sound.name + " " + sound.relative_path).toLowerCase();
    list.appendChild(node);
    waveformObserver.observe(list.lastElementChild.querySelector(".waveform"));
  });

  empty.hidden = sounds.length !== 0;
}

function addControlLabel(text) {
  const label = document.createElement("span");
  label.textContent = text;
  return label;
}

function renderLayer(layer) {
  const row = document.createElement("div");
  row.className = "recipe-layer";

  const head = document.createElement("div");
  head.className = "layer-head";

  const name = document.createElement("strong");
  name.className = "layer-name";
  name.textContent = layer.sound.name;
  name.title = layer.sound.relative_path;

  const actions = document.createElement("div");
  actions.className = "layer-actions";

  const mute = document.createElement("button");
  mute.className = "toggle" + (layer.muted ? " active" : "");
  mute.type = "button";
  mute.textContent = "M";
  mute.title = "Mute";
  mute.addEventListener("click", function () {
    layer.muted = !layer.muted;
    renderRecipe();
    applyLiveGains();
  });

  const solo = document.createElement("button");
  solo.className = "toggle" + (layer.solo ? " active" : "");
  solo.type = "button";
  solo.textContent = "S";
  solo.title = "Solo";
  solo.addEventListener("click", function () {
    layer.solo = !layer.solo;
    renderRecipe();
    applyLiveGains();
  });

  const remove = document.createElement("button");
  remove.className = "remove";
  remove.type = "button";
  remove.textContent = "Remove";
  remove.addEventListener("click", function () {
    state.selected = state.selected.filter(function (candidate) {
      return candidate.sound.relative_path !== layer.sound.relative_path;
    });
    stopMix();
    renderRecipe();
  });

  actions.append(mute, solo, remove);
  head.append(name, actions);

  const gainControl = document.createElement("label");
  gainControl.className = "layer-control";
  const gainSlider = document.createElement("input");
  gainSlider.type = "range";
  gainSlider.min = "0";
  gainSlider.max = "2";
  gainSlider.step = "0.05";
  gainSlider.value = String(layer.gain);
  const gainValue = document.createElement("span");
  gainValue.className = "layer-value";
  gainValue.textContent = layer.gain.toFixed(2) + "×";
  gainSlider.addEventListener("input", function () {
    layer.gain = Number(gainSlider.value);
    gainValue.textContent = layer.gain.toFixed(2) + "×";
    applyLiveGains();
  });
  gainControl.append(addControlLabel("Gain"), gainSlider, gainValue);

  const offsetControl = document.createElement("label");
  offsetControl.className = "layer-control";
  const offsetInput = document.createElement("input");
  offsetInput.className = "offset-input";
  offsetInput.type = "number";
  offsetInput.min = "0";
  offsetInput.max = "5000";
  offsetInput.step = "10";
  offsetInput.value = String(layer.offset_ms);
  offsetInput.addEventListener("change", function () {
    const value = Math.max(0, Math.min(5000, Number(offsetInput.value) || 0));
    layer.offset_ms = Math.round(value);
    offsetInput.value = String(layer.offset_ms);
    scheduleMixRestart();
  });
  const offsetUnit = document.createElement("span");
  offsetUnit.className = "layer-value";
  offsetUnit.textContent = "ms";
  offsetControl.append(addControlLabel("Offset"), offsetInput, offsetUnit);

  row.append(head, gainControl, offsetControl);
  return row;
}

function renderRecipe() {
  recipeLayers.replaceChildren();

  if (state.selected.length === 0) {
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = "Use “Add layer” on sounds you want to combine.";
    recipeLayers.appendChild(hint);
  } else {
    state.selected.forEach(function (layer) {
      recipeLayers.appendChild(renderLayer(layer));
    });
  }

  layerCount.textContent = String(state.selected.length) + " / 4";
  downloadRecipe.disabled = state.selected.length === 0;
  previewMixButton.disabled = state.selected.length === 0;
  stopMixButton.disabled = state.selected.length === 0 || state.mixVoices.length === 0;

  document.querySelectorAll(".audio-card").forEach(function (card) {
    const path = card.querySelector(".file-path").textContent;
    const button = card.querySelector(".add");
    const selected = state.selected.some(function (layer) {
      return layer.sound.relative_path === path;
    });
    button.disabled = selected || state.selected.length >= 4;
    button.textContent = selected ? "✓ Added" : "＋ Add layer";
  });
}

function recipePayload() {
  const intentValue = intent.value.trim() || "game sound effect";
  return {
    recipe_version: "0.1",
    id: escapeRecipeId(intentValue),
    intent: intentValue,
    layers: state.selected.map(function (layer) {
      return {
        source: layer.sound.relative_path,
        gain: Number(layer.gain.toFixed(3)),
        offset_ms: layer.offset_ms,
      };
    }),
    processing: {
      normalize: true,
      fade_out_ms: 0,
    },
  };
}

downloadRecipe.addEventListener("click", function () {
  const payload = recipePayload();
  const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], {
    type: "application/json",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = payload.id + ".json";
  link.click();
  URL.revokeObjectURL(link.href);
});

filter.addEventListener("input", function () {
  const query = filter.value.trim().toLowerCase();
  document.querySelectorAll(".audio-card").forEach(function (card) {
    card.hidden = Boolean(query && !card.dataset.search.includes(query));
  });
});

previewMixButton.addEventListener("click", previewMix);
stopMixButton.addEventListener("click", stopMix);
document.querySelector("#stop-all").addEventListener("click", stopAll);

async function boot() {
  try {
    const response = await fetch("/api/audio");
    if (!response.ok) throw new Error("HTTP " + String(response.status));
    state.sounds = await response.json();
    renderSounds(state.sounds);
    renderRecipe();
    status.textContent =
      String(state.sounds.length) +
      " WAV file" +
      (state.sounds.length === 1 ? "" : "s");
  } catch (error) {
    status.textContent = "Could not scan audio";
    empty.hidden = false;
    empty.textContent = error.message;
  }
}

boot();
