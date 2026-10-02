const state = {
  sounds: [],
  selected: [],
  mixVoices: [],
  bufferCache: new Map(),
  mixRestartTimer: null,
  previewOwner: null,
  candidates: [],
  activeCandidateId: null,
  boardBaseRecipe: null,
  catalogSignature: null,
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
const seedCandidatesButton = document.querySelector("#seed-candidates");
const candidateBoard = document.querySelector("#candidate-board");
const candidateHelp = document.querySelector("#candidate-help");
const downloadBoardButton = document.querySelector("#download-board");
const mixerTitle = document.querySelector("#mixer-title");
const refreshSourcesButton = document.querySelector("#refresh-sources");

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

function selectedCandidate() {
  return state.candidates.find(function (candidate) {
    return candidate.id === state.activeCandidateId;
  }) || null;
}

function setSelected(layers) {
  state.selected = layers;
  const candidate = selectedCandidate();
  if (candidate) candidate.layers = layers;
}

function cloneLayer(layer) {
  return {
    sound: layer.sound,
    gain: layer.gain,
    offset_ms: layer.offset_ms,
    muted: false,
    solo: false,
  };
}

function cloneLayers(layers) {
  return layers.map(cloneLayer);
}

function persistedLayer(layer) {
  return {
    source: layer.sound.relative_path,
    gain: Number(layer.gain.toFixed(3)),
    offset_ms: layer.offset_ms,
  };
}

function recipePayloadForLayers(layers, idOverride) {
  const intentValue = intent.value.trim() || "game sound effect";
  return {
    recipe_version: "0.1",
    id: idOverride || escapeRecipeId(intentValue),
    intent: intentValue,
    layers: layers.map(persistedLayer),
    processing: {
      normalize: true,
      fade_out_ms: 0,
    },
  };
}

function recipePayload() {
  const candidate = selectedCandidate();
  return recipePayloadForLayers(
    state.selected,
    candidate ? candidate.id : null
  );
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

function resetPreviewLabels() {
  previewMixButton.textContent = "▶ Preview mix";
  document.querySelectorAll(".candidate-preview").forEach(function (button) {
    button.textContent = "▶ Preview";
  });
}

function stopMix() {
  if (state.mixRestartTimer) {
    clearTimeout(state.mixRestartTimer);
    state.mixRestartTimer = null;
  }

  state.mixVoices.forEach(function (voice) {
    try {
      voice.source.onended = null;
      voice.source.stop();
    } catch (error) {
      // Already stopped.
    }
  });
  state.mixVoices = [];
  state.previewOwner = null;
  resetPreviewLabels();
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

function hasSoloLayer(layers) {
  return layers.some(function (layer) {
    return layer.solo;
  });
}

function isLayerAudible(layer, layers) {
  if (layer.muted) return false;
  return !hasSoloLayer(layers) || layer.solo;
}

function effectiveGain(layer, layers) {
  return isLayerAudible(layer, layers) ? layer.gain : 0;
}

function applyLiveGains() {
  if (state.previewOwner !== "mixer") return;
  state.mixVoices.forEach(function (voice) {
    const layer = state.selected.find(function (candidate) {
      return candidate.sound.relative_path === voice.path;
    });
    if (!layer) return;
    voice.gainNode.gain.setTargetAtTime(
      effectiveGain(layer, state.selected),
      audioContext.currentTime,
      0.01
    );
  });
}

async function playLayerSet(layers, options) {
  if (layers.length === 0) return;

  stopIndividualAuditions();
  stopMix();
  await audioContext.resume();

  const owner = options.owner;
  const respectAudition = options.respectAudition;
  state.previewOwner = owner;

  try {
    const loaded = await Promise.all(
      layers.map(async function (layer) {
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
      gainNode.gain.value = respectAudition
        ? effectiveGain(entry.layer, layers)
        : entry.layer.gain;
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
          state.previewOwner = null;
          resetPreviewLabels();
          stopMixButton.disabled = true;
        }
      };
      return voice;
    });

    stopMixButton.disabled = false;
  } catch (error) {
    status.textContent = "Preview failed: " + error.message;
    stopMix();
  }
}

async function previewMix() {
  if (state.selected.length === 0) return;
  previewMixButton.disabled = true;
  previewMixButton.textContent = "Loading…";
  await playLayerSet(state.selected, {
    owner: "mixer",
    respectAudition: true,
  });
  if (state.previewOwner === "mixer") previewMixButton.textContent = "↻ Replay mix";
  previewMixButton.disabled = state.selected.length === 0;
}

async function previewCandidate(candidate) {
  const button = document.querySelector('[data-candidate-preview="' + candidate.id + '"]');
  if (button) button.textContent = "Loading…";
  await playLayerSet(candidate.layers, {
    owner: candidate.id,
    respectAudition: false,
  });
  if (state.previewOwner === candidate.id && button) button.textContent = "■ Playing";
}

function scheduleMixRestart() {
  if (state.mixVoices.length === 0 || state.previewOwner !== "mixer") return;
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
    const sourceContext = node.querySelector(".source-context");

    node.querySelector(".file-name").textContent = sound.name;
    node.querySelector(".file-path").textContent = sound.relative_path;
    node.querySelector(".duration").textContent = formatDuration(sound.duration_ms);
    node.querySelector(".meta").textContent =
      String(sound.sample_rate) + " Hz · " + String(sound.channels) + "ch";

    if (sound.intake) {
      card.classList.add("intake-card");
      sourceContext.hidden = false;
      node.querySelector(".source-type-badge").textContent =
        sound.intake.source_type || sound.intake.provider_kind || "provider";
      node.querySelector(".provider-badge").textContent =
        sound.intake.generation_provider || sound.intake.provider_id || "provider";
      node.querySelector(".intake-badge").textContent =
        "intake · " + (sound.intake.intake_id || "unknown");
      node.querySelector(".source-prompt").textContent =
        sound.intake.prompt || sound.intake.intent || "";
    }

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
      renderCandidates();
    });

    const intakeSearch = sound.intake
      ? [
          sound.intake.intake_id,
          sound.intake.provider_id,
          sound.intake.provider_kind,
          sound.intake.source_type,
          sound.intake.generation_provider,
          sound.intake.generation_model,
          sound.intake.prompt,
          sound.intake.intent,
        ].filter(Boolean).join(" ")
      : "";
    card.dataset.search = (
      sound.name + " " + sound.relative_path + " " + intakeSearch
    ).toLowerCase();
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
    setSelected(state.selected.filter(function (candidate) {
      return candidate.sound.relative_path !== layer.sound.relative_path;
    }));
    stopMix();
    renderRecipe();
    renderCandidates();
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
    renderCandidates();
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
    renderCandidates();
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

  const candidate = selectedCandidate();
  mixerTitle.textContent = candidate ? "Candidate " + candidate.label : "Base recipe";
  layerCount.textContent = String(state.selected.length) + " / 4";
  downloadRecipe.disabled = state.selected.length === 0;
  previewMixButton.disabled = state.selected.length === 0;
  seedCandidatesButton.disabled = state.selected.length === 0 || state.candidates.length > 0;
  stopMixButton.disabled = state.mixVoices.length === 0;
  downloadBoardButton.disabled = state.candidates.length === 0;

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

function seedCandidates() {
  if (state.selected.length === 0) return;

  const base = recipePayloadForLayers(state.selected, escapeRecipeId(intent.value) + "-base");
  state.boardBaseRecipe = base;
  state.candidates = ["A", "B", "C"].map(function (label) {
    return {
      id: base.id + "-" + label.toLowerCase(),
      label: label,
      parent_recipe_id: base.id,
      revision: 1,
      layers: cloneLayers(state.selected),
      decision: "undecided",
      reason: "",
      lineage: [
        {
          from_recipe_id: base.id,
          action: "fork",
          revision: 1,
        },
      ],
    };
  });

  state.activeCandidateId = state.candidates[0].id;
  state.selected = state.candidates[0].layers;
  stopMix();
  renderRecipe();
  renderCandidates();
}

function loadCandidate(candidateId) {
  const candidate = state.candidates.find(function (item) {
    return item.id === candidateId;
  });
  if (!candidate) return;
  stopMix();
  state.activeCandidateId = candidate.id;
  state.selected = candidate.layers;
  renderRecipe();
  renderCandidates();
}

function copyActiveInto(targetId) {
  const source = selectedCandidate();
  const target = state.candidates.find(function (candidate) {
    return candidate.id === targetId;
  });
  if (!source || !target || source.id === target.id) return;

  target.layers = cloneLayers(source.layers);
  target.parent_recipe_id = source.id + "@r" + String(source.revision);
  target.revision += 1;
  target.lineage.push({
    from_recipe_id: target.parent_recipe_id,
    action: "copy",
    revision: target.revision,
  });
  target.decision = "undecided";
  target.reason = "";
  renderCandidates();
}

function setCandidateDecision(candidateId, decision) {
  const candidate = state.candidates.find(function (item) {
    return item.id === candidateId;
  });
  if (!candidate) return;

  if (decision === "selected") {
    state.candidates.forEach(function (item) {
      if (item.decision === "selected") item.decision = "undecided";
    });
  }

  candidate.decision = candidate.decision === decision ? "undecided" : decision;
  renderCandidates();
}

function candidateDeltaCount(candidate) {
  if (!state.boardBaseRecipe) return 0;
  const baseLayers = state.boardBaseRecipe.layers;
  const candidateLayers = candidate.layers.map(persistedLayer);
  const maxLength = Math.max(baseLayers.length, candidateLayers.length);
  let changes = 0;

  for (let i = 0; i < maxLength; i += 1) {
    const base = baseLayers[i];
    const current = candidateLayers[i];
    if (!base || !current) {
      changes += 1;
      continue;
    }
    if (base.source !== current.source) changes += 1;
    if (base.gain !== current.gain) changes += 1;
    if (base.offset_ms !== current.offset_ms) changes += 1;
  }

  return changes;
}

function decisionButton(candidate, decision, label, className) {
  const button = document.createElement("button");
  button.type = "button";
  button.className =
    "candidate-action " +
    className +
    (candidate.decision === decision ? " active" : "");
  button.textContent = label;
  button.addEventListener("click", function () {
    setCandidateDecision(candidate.id, decision);
  });
  return button;
}

function renderCandidateCard(candidate) {
  const card = document.createElement("article");
  card.className =
    "candidate-card" +
    (candidate.id === state.activeCandidateId ? " active" : "") +
    (candidate.decision === "selected" ? " selected" : "");

  const head = document.createElement("div");
  head.className = "candidate-card-head";

  const title = document.createElement("div");
  title.className = "candidate-title";

  const label = document.createElement("span");
  label.className = "candidate-label";
  label.textContent = candidate.label;

  const titleMeta = document.createElement("div");
  const badge = document.createElement("span");
  badge.className = "candidate-badge";
  badge.textContent = candidate.decision;
  const lineage = document.createElement("div");
  lineage.className = "candidate-meta";
  lineage.textContent =
    "parent: " +
    candidate.parent_recipe_id +
    " · rev " +
    String(candidate.revision) +
    " · hops " +
    String(candidate.lineage.length);
  titleMeta.append(badge, lineage);
  title.append(label, titleMeta);

  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "candidate-action";
  edit.textContent = candidate.id === state.activeCandidateId ? "Editing" : "Edit";
  edit.disabled = candidate.id === state.activeCandidateId;
  edit.addEventListener("click", function () {
    loadCandidate(candidate.id);
  });

  head.append(title, edit);

  const delta = document.createElement("div");
  delta.className = "candidate-delta";
  const changes = candidateDeltaCount(candidate);
  delta.textContent =
    String(candidate.layers.length) +
    " layers · " +
    String(changes) +
    (changes === 1 ? " change" : " changes") +
    " vs base";

  const actions = document.createElement("div");
  actions.className = "candidate-actions";

  const preview = document.createElement("button");
  preview.type = "button";
  preview.className = "candidate-action candidate-preview";
  preview.dataset.candidatePreview = candidate.id;
  preview.textContent = state.previewOwner === candidate.id ? "■ Playing" : "▶ Preview";
  preview.addEventListener("click", function () {
    if (state.previewOwner === candidate.id) {
      stopMix();
      return;
    }
    previewCandidate(candidate);
  });

  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "candidate-action";
  copy.textContent = "Copy active → " + candidate.label;
  copy.disabled = !state.activeCandidateId || state.activeCandidateId === candidate.id;
  copy.addEventListener("click", function () {
    copyActiveInto(candidate.id);
  });

  actions.append(preview, copy);

  const decisions = document.createElement("div");
  decisions.className = "candidate-decisions";
  decisions.append(
    decisionButton(candidate, "favorite", "★ Favorite", "decision-favorite"),
    decisionButton(candidate, "reject", "× Reject", "decision-reject"),
    decisionButton(candidate, "selected", "✓ Select", "decision-selected")
  );

  const reason = document.createElement("textarea");
  reason.className = "candidate-reason";
  reason.placeholder = "Why does this candidate work or fail?";
  reason.value = candidate.reason;
  reason.addEventListener("input", function () {
    candidate.reason = reason.value;
  });

  card.append(head, delta, actions, decisions, reason);
  return card;
}

function renderCandidates() {
  candidateBoard.replaceChildren();

  if (state.candidates.length === 0) {
    candidateHelp.hidden = false;
    downloadBoardButton.disabled = true;
    return;
  }

  candidateHelp.hidden = true;
  state.candidates.forEach(function (candidate) {
    candidateBoard.appendChild(renderCandidateCard(candidate));
  });
  downloadBoardButton.disabled = false;
}

function boardPayload() {
  const selected = state.candidates.find(function (candidate) {
    return candidate.decision === "selected";
  });
  return {
    candidate_board_version: "0.1",
    intent: intent.value.trim() || "game sound effect",
    base_recipe: state.boardBaseRecipe,
    active_candidate_id: state.activeCandidateId,
    selected_candidate_id: selected ? selected.id : null,
    candidates: state.candidates.map(function (candidate) {
      return {
        id: candidate.id,
        label: candidate.label,
        parent_recipe_id: candidate.parent_recipe_id,
        revision: candidate.revision,
        lineage: candidate.lineage,
        recipe: recipePayloadForLayers(candidate.layers, candidate.id),
        decision: {
          status: candidate.decision,
          reason: candidate.reason,
        },
      };
    }),
  };
}

function downloadJson(payload, filename) {
  const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], {
    type: "application/json",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

downloadRecipe.addEventListener("click", function () {
  const payload = recipePayload();
  downloadJson(payload, payload.id + ".json");
});

downloadBoardButton.addEventListener("click", function () {
  const payload = boardPayload();
  const baseId = payload.base_recipe ? payload.base_recipe.id : "candidate-board";
  downloadJson(payload, baseId + "-candidates.json");
});

seedCandidatesButton.addEventListener("click", seedCandidates);

function applyFilter() {
  const query = filter.value.trim().toLowerCase();
  document.querySelectorAll(".audio-card").forEach(function (card) {
    card.hidden = Boolean(query && !card.dataset.search.includes(query));
  });
}

filter.addEventListener("input", applyFilter);

previewMixButton.addEventListener("click", previewMix);
stopMixButton.addEventListener("click", stopMix);
document.querySelector("#stop-all").addEventListener("click", stopAll);

function catalogSignature(sounds) {
  return JSON.stringify(
    sounds.map(function (sound) {
      return [
        sound.relative_path,
        sound.bytes || 0,
        sound.intake ? sound.intake.intake_id : null,
        sound.intake ? sound.intake.source_id : null,
      ];
    })
  );
}

async function refreshCatalog(options) {
  const quiet = Boolean(options && options.quiet);
  if (!quiet) {
    refreshSourcesButton.disabled = true;
    refreshSourcesButton.textContent = "Refreshing…";
  }

  try {
    const response = await fetch("/api/audio", { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + String(response.status));
    const sounds = await response.json();
    const signature = catalogSignature(sounds);

    if (signature !== state.catalogSignature) {
      state.sounds = sounds;
      state.catalogSignature = signature;
      renderSounds(state.sounds);
      applyFilter();
    }

    status.textContent =
      String(state.sounds.length) +
      " WAV file" +
      (state.sounds.length === 1 ? "" : "s") +
      " · live intake";
  } catch (error) {
    if (!quiet) {
      status.textContent = "Could not scan audio";
      empty.hidden = false;
      empty.textContent = error.message;
    }
  } finally {
    if (!quiet) {
      refreshSourcesButton.disabled = false;
      refreshSourcesButton.textContent = "↻ Refresh sources";
    }
  }
}

refreshSourcesButton.addEventListener("click", function () {
  refreshCatalog({ quiet: false });
});

async function boot() {
  await refreshCatalog({ quiet: false });
  renderRecipe();
  renderCandidates();
  window.setInterval(function () {
    refreshCatalog({ quiet: true });
  }, 2500);
}

boot();
