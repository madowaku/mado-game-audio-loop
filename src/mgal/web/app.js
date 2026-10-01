const state = {
  sounds: [],
  selected: [],
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

function stopAll() {
  document.querySelectorAll("audio").forEach(function (audio) {
    audio.pause();
    audio.currentTime = 0;
  });
  document.querySelectorAll(".play").forEach(function (button) {
    button.textContent = "▶ Play";
  });
}

async function drawWaveform(canvas, url) {
  if (canvas.dataset.loaded === "true") return;
  canvas.dataset.loaded = "true";

  try {
    const response = await fetch(url);
    const arrayBuffer = await response.arrayBuffer();
    const buffer = await audioContext.decodeAudioData(arrayBuffer);
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
      const exists = state.selected.some(function (item) {
        return item.relative_path === sound.relative_path;
      });
      if (exists || state.selected.length >= 4) return;
      state.selected.push(sound);
      renderRecipe();
    });

    card.dataset.search = (sound.name + " " + sound.relative_path).toLowerCase();
    list.appendChild(node);
    waveformObserver.observe(list.lastElementChild.querySelector(".waveform"));
  });

  empty.hidden = sounds.length !== 0;
}

function renderRecipe() {
  recipeLayers.replaceChildren();

  if (state.selected.length === 0) {
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = "Use “Add layer” on sounds you want to combine.";
    recipeLayers.appendChild(hint);
  } else {
    state.selected.forEach(function (sound) {
      const row = document.createElement("div");
      row.className = "recipe-layer";

      const name = document.createElement("strong");
      name.textContent = sound.name;

      const remove = document.createElement("button");
      remove.className = "remove";
      remove.type = "button";
      remove.textContent = "Remove";
      remove.addEventListener("click", function () {
        state.selected = state.selected.filter(function (item) {
          return item.relative_path !== sound.relative_path;
        });
        renderRecipe();
      });

      row.append(name, remove);
      recipeLayers.appendChild(row);
    });
  }

  layerCount.textContent = String(state.selected.length) + " / 4";
  downloadRecipe.disabled = state.selected.length === 0;

  document.querySelectorAll(".audio-card").forEach(function (card) {
    const path = card.querySelector(".file-path").textContent;
    const button = card.querySelector(".add");
    const selected = state.selected.some(function (item) {
      return item.relative_path === path;
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
    layers: state.selected.map(function (sound) {
      return {
        source: sound.relative_path,
        gain: 1.0,
        offset_ms: 0,
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
