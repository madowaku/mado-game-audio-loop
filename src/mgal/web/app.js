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
  blindMode: false,
  sequenceRunning: false,
  sequenceIndex: -1,
  sequenceTimer: null,
  playbackToken: 0,
  preferenceSession: null,
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
const intakeSessions = document.querySelector("#intake-sessions");
const intakeSessionList = document.querySelector("#intake-session-list");
const intakeSessionCount = document.querySelector("#intake-session-count");
const clearBoardButton = document.querySelector("#clear-board");
const blindModeButton = document.querySelector("#blind-mode");
const sequenceCandidatesButton = document.querySelector("#sequence-candidates");
const previousCandidateButton = document.querySelector("#previous-candidate");
const nextCandidateButton = document.querySelector("#next-candidate");
const auditionPosition = document.querySelector("#audition-position");
const preferenceSessionButton = document.querySelector("#preference-session");
const preferencePanel = document.querySelector("#preference-panel");
const preferenceTitle = document.querySelector("#preference-title");
const preferenceProgress = document.querySelector("#preference-progress");
const preferenceMessage = document.querySelector("#preference-message");
const preferencePair = document.querySelector("#preference-pair");
const preferenceLeftLabel = document.querySelector("#preference-left-label");
const preferenceRightLabel = document.querySelector("#preference-right-label");
const preferenceLeftPlay = document.querySelector("#preference-left-play");
const preferenceRightPlay = document.querySelector("#preference-right-play");
const preferenceLeftVote = document.querySelector("#preference-left-vote");
const preferenceRightVote = document.querySelector("#preference-right-vote");
const preferenceReveal = document.querySelector("#preference-reveal");
const preferenceRevealButton = document.querySelector("#preference-reveal-button");
const preferenceApply = document.querySelector("#preference-apply");
const preferenceClose = document.querySelector("#preference-close");

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

function randomUint32() {
  const values = new Uint32Array(1);
  window.crypto.getRandomValues(values);
  return values[0];
}

function shuffleCopy(items) {
  const copy = items.slice();
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const swapIndex = randomUint32() % (index + 1);
    const temporary = copy[index];
    copy[index] = copy[swapIndex];
    copy[swapIndex] = temporary;
  }
  return copy;
}

function candidateById(candidateId) {
  return state.candidates.find(function (candidate) {
    return candidate.id === candidateId;
  }) || null;
}

function preferenceAlias(candidateId) {
  const session = state.preferenceSession;
  if (!session || session.revealed) return null;
  const entry = session.mapping.find(function (item) {
    return item.candidateId === candidateId;
  });
  return entry ? entry.alias : null;
}

function displayCandidateLabel(candidate) {
  return preferenceAlias(candidate.id) || candidate.label;
}

function candidatesForDisplay() {
  const session = state.preferenceSession;
  if (!session || session.revealed) return state.candidates;
  return session.mapping
    .map(function (entry) {
      return candidateById(entry.candidateId);
    })
    .filter(Boolean);
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

function updateAuditionControls() {
  const hasCandidates = state.candidates.length > 0;
  const activeIndex = state.candidates.findIndex(function (candidate) {
    return candidate.id === state.activeCandidateId;
  });

  blindModeButton.disabled = !hasCandidates;
  sequenceCandidatesButton.disabled = !hasCandidates;
  preferenceSessionButton.disabled = state.candidates.length < 2;
  previousCandidateButton.disabled = !hasCandidates || activeIndex <= 0;
  nextCandidateButton.disabled =
    !hasCandidates ||
    activeIndex < 0 ||
    activeIndex >= state.candidates.length - 1;

  blindModeButton.textContent = state.blindMode ? "Blind: On" : "Blind: Off";
  blindModeButton.classList.toggle("active", state.blindMode);
  sequenceCandidatesButton.textContent = state.sequenceRunning
    ? "■ Stop sequence"
    : "▶ A→B→C";
  sequenceCandidatesButton.classList.toggle("active", state.sequenceRunning);
  preferenceSessionButton.classList.toggle(
    "active",
    Boolean(state.preferenceSession)
  );

  document.body.classList.toggle("blind-mode", state.blindMode);
  document.body.classList.toggle(
    "preference-mode",
    Boolean(state.preferenceSession && !state.preferenceSession.revealed)
  );

  if (!hasCandidates) {
    auditionPosition.textContent = "No candidates";
  } else if (activeIndex >= 0) {
    auditionPosition.textContent =
      state.candidates[activeIndex].label +
      " · " +
      String(activeIndex + 1) +
      "/" +
      String(state.candidates.length);
  } else {
    auditionPosition.textContent = "Ready";
  }
}

function cancelSequentialAudition() {
  if (state.sequenceTimer) {
    clearTimeout(state.sequenceTimer);
    state.sequenceTimer = null;
  }
  state.sequenceRunning = false;
  state.sequenceIndex = -1;
  updateAuditionControls();
}

function stopMix(options) {
  const preserveSequence = Boolean(options && options.preserveSequence);
  if (!preserveSequence) cancelSequentialAudition();

  state.playbackToken += 1;

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
  stopMix({
    preserveSequence: Boolean(options && options.sequence),
  });
  await audioContext.resume();

  const owner = options.owner;
  const respectAudition = options.respectAudition;
  const onComplete = options.onComplete;
  const playbackToken = state.playbackToken;
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
          if (
            playbackToken === state.playbackToken &&
            typeof onComplete === "function"
          ) {
            onComplete();
          }
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

async function previewCandidate(candidate, options) {
  const sequence = Boolean(options && options.sequence);
  if (!sequence) cancelSequentialAudition();

  const button = document.querySelector('[data-candidate-preview="' + candidate.id + '"]');
  if (button) button.textContent = "Loading…";
  await playLayerSet(candidate.layers, {
    owner: candidate.id,
    respectAudition: false,
    sequence: sequence,
    onComplete: options ? options.onComplete : null,
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

function soundByPath(relativePath) {
  return state.sounds.find(function (sound) {
    return sound.relative_path === relativePath;
  }) || null;
}

function makeLayerFromRecipeLayer(recipeLayer) {
  const sound = soundByPath(recipeLayer.source);
  if (!sound) {
    throw new Error("Seed source is missing from catalog: " + recipeLayer.source);
  }
  return {
    sound: sound,
    gain: Number(recipeLayer.gain ?? 1.0),
    offset_ms: Number(recipeLayer.offset_ms ?? 0),
    muted: false,
    solo: false,
  };
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

function intakeGroups() {
  const groups = new Map();

  state.sounds.forEach(function (sound) {
    if (!sound.intake || !sound.intake.intake_id) return;
    const id = sound.intake.intake_id;
    if (!groups.has(id)) {
      groups.set(id, {
        id: id,
        provider: sound.intake.generation_provider || sound.intake.provider_id || "provider",
        model: sound.intake.generation_model || "",
        intent: sound.intake.prompt || sound.intake.intent || "",
        sounds: [],
      });
    }
    groups.get(id).sounds.push(sound);
  });

  return Array.from(groups.values())
    .map(function (group) {
      group.sounds.sort(function (a, b) {
        return a.relative_path.localeCompare(b.relative_path);
      });
      return group;
    })
    .sort(function (a, b) {
      return a.id.localeCompare(b.id);
    });
}

async function seedIntakeSession(intakeId, button) {
  if (state.candidates.length > 0) return;

  button.disabled = true;
  button.textContent = "Seeding…";

  try {
    const response = await fetch(
      "/api/intakes/" + encodeURIComponent(intakeId) + "/seed-board",
      { cache: "no-store" }
    );
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not seed intake");
    }

    intent.value = payload.intent || "game sound effect";
    state.boardBaseRecipe = payload.base_recipe;
    state.candidates = payload.candidates.map(function (candidate) {
      return {
        id: candidate.id,
        label: candidate.label,
        parent_recipe_id: candidate.parent_recipe_id,
        revision: candidate.revision,
        lineage: candidate.lineage,
        layers: candidate.recipe.layers.map(makeLayerFromRecipeLayer),
        decision: candidate.decision.status,
        reason: candidate.decision.reason,
      };
    });
    state.activeCandidateId =
      payload.active_candidate_id ||
      (state.candidates[0] ? state.candidates[0].id : null);

    const active = selectedCandidate();
    state.selected = active ? active.layers : [];
    stopMix();
    renderRecipe();
    renderCandidates();
    renderIntakeSessions();
    status.textContent =
      "Seeded " +
      String(state.candidates.length) +
      " candidate" +
      (state.candidates.length === 1 ? "" : "s") +
      " from intake " +
      intakeId;
  } catch (error) {
    status.textContent = "Intake seed failed: " + error.message;
    renderIntakeSessions();
  }
}

function renderIntakeSessions() {
  const groups = intakeGroups();
  intakeSessionList.replaceChildren();
  intakeSessionCount.textContent = String(groups.length);
  intakeSessions.hidden = groups.length === 0;

  groups.forEach(function (group) {
    const card = document.createElement("article");
    card.className = "intake-session-card";

    const meta = document.createElement("div");
    meta.className = "intake-session-meta";

    const title = document.createElement("strong");
    title.textContent = group.id;

    const detail = document.createElement("span");
    const comparableCount = Math.min(3, group.sounds.length);
    detail.textContent =
      group.provider +
      (group.model ? " · " + group.model : "") +
      " · " +
      String(group.sounds.length) +
      " source" +
      (group.sounds.length === 1 ? "" : "s") +
      (group.sounds.length > 3 ? " · first 3 seed" : "");

    const prompt = document.createElement("span");
    prompt.className = "intake-session-prompt";
    prompt.textContent = group.intent || "No prompt metadata";

    meta.append(title, detail, prompt);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "primary compact intake-seed";
    button.textContent =
      "Seed " +
      ["A", "B", "C"].slice(0, comparableCount).join("/") +
      " from intake";
    button.disabled = state.candidates.length > 0 || comparableCount === 0;
    button.addEventListener("click", function () {
      seedIntakeSession(group.id, button);
    });

    card.append(meta, button);
    intakeSessionList.appendChild(card);
  });
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

    node.querySelector(".file-name").classList.add("blind-sensitive");
    node.querySelector(".file-path").classList.add("blind-sensitive");
    node.querySelector(".file-name").textContent = sound.name;
    node.querySelector(".file-path").textContent = sound.relative_path;
    node.querySelector(".duration").textContent = formatDuration(sound.duration_ms);
    node.querySelector(".meta").textContent =
      String(sound.sample_rate) + " Hz · " + String(sound.channels) + "ch";

    if (sound.intake) {
      card.classList.add("intake-card");
      sourceContext.hidden = false;
      sourceContext.classList.add("blind-sensitive");
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
  name.className = "layer-name blind-sensitive";
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
  clearBoardButton.disabled = state.candidates.length === 0;

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

function activateCandidate(candidate, options) {
  if (!candidate) return;
  const preservePlayback = Boolean(options && options.preservePlayback);
  if (!preservePlayback) stopMix();
  state.activeCandidateId = candidate.id;
  state.selected = candidate.layers;
  renderRecipe();
  renderCandidates();
  updateAuditionControls();
}

function loadCandidate(candidateId) {
  const candidate = state.candidates.find(function (item) {
    return item.id === candidateId;
  });
  activateCandidate(candidate);
}

function candidateIndex() {
  return state.candidates.findIndex(function (candidate) {
    return candidate.id === state.activeCandidateId;
  });
}

function moveCandidate(step, shouldPreview) {
  if (state.candidates.length === 0) return;
  cancelSequentialAudition();

  const current = candidateIndex();
  const start = current < 0 ? 0 : current;
  const targetIndex = Math.max(
    0,
    Math.min(state.candidates.length - 1, start + step)
  );
  const candidate = state.candidates[targetIndex];
  activateCandidate(candidate);

  if (shouldPreview) previewCandidate(candidate);
}

function toggleBlindMode() {
  if (state.candidates.length === 0) return;
  state.blindMode = !state.blindMode;
  updateAuditionControls();
  status.textContent = state.blindMode
    ? "Blind audition enabled · source and provider identity hidden"
    : "Blind audition disabled";
}

async function playSequentialCandidate(index) {
  if (!state.sequenceRunning) return;

  if (index >= state.candidates.length) {
    cancelSequentialAudition();
    status.textContent = "Sequential audition complete";
    return;
  }

  state.sequenceIndex = index;
  const candidate = state.candidates[index];
  state.activeCandidateId = candidate.id;
  state.selected = candidate.layers;
  renderRecipe();
  renderCandidates();
  updateAuditionControls();

  status.textContent =
    "Sequential audition · " +
    candidate.label +
    " · " +
    String(index + 1) +
    "/" +
    String(state.candidates.length);

  await previewCandidate(candidate, {
    sequence: true,
    onComplete: function () {
      if (!state.sequenceRunning) return;
      state.sequenceTimer = setTimeout(function () {
        state.sequenceTimer = null;
        playSequentialCandidate(index + 1);
      }, 350);
    },
  });
}

function startSequentialAudition() {
  if (state.candidates.length === 0) return;

  if (state.sequenceRunning) {
    stopMix();
    status.textContent = "Sequential audition stopped";
    return;
  }

  stopAll();
  state.sequenceRunning = true;
  state.sequenceIndex = 0;
  updateAuditionControls();
  playSequentialCandidate(0);
}

function preferencePairs(mapping) {
  const pairs = [];
  for (let left = 0; left < mapping.length; left += 1) {
    for (let right = left + 1; right < mapping.length; right += 1) {
      const pair = [mapping[left], mapping[right]];
      if (randomUint32() % 2 === 1) pair.reverse();
      pairs.push(pair);
    }
  }
  return shuffleCopy(pairs);
}

function preferenceScores(session) {
  const scores = new Map();
  session.mapping.forEach(function (entry) {
    scores.set(entry.candidateId, 0);
  });
  session.votes.forEach(function (vote) {
    scores.set(
      vote.winnerCandidateId,
      (scores.get(vote.winnerCandidateId) || 0) + 1
    );
  });
  return scores;
}

function preferenceWinner(session) {
  if (session.votes.length !== session.pairs.length) return null;
  const scores = preferenceScores(session);
  let best = -1;
  let leaders = [];
  scores.forEach(function (score, candidateId) {
    if (score > best) {
      best = score;
      leaders = [candidateId];
    } else if (score === best) {
      leaders.push(candidateId);
    }
  });
  return leaders.length === 1 ? leaders[0] : null;
}

function closePreferenceSession() {
  stopAll();
  state.preferenceSession = null;
  preferencePanel.hidden = true;
  state.blindMode = false;
  updateAuditionControls();
  renderCandidates();
  status.textContent = "Preference session closed";
}

function startPreferenceSession() {
  if (state.candidates.length < 2) return;
  stopAll();

  const aliases = ["X", "Y", "Z"];
  const shuffled = shuffleCopy(state.candidates.slice(0, 3));
  const mapping = shuffled.map(function (candidate, index) {
    return {
      alias: aliases[index],
      candidateId: candidate.id,
    };
  });

  state.preferenceSession = {
    mapping: mapping,
    pairs: preferencePairs(mapping),
    pairIndex: 0,
    votes: [],
    revealed: false,
    applied: false,
  };
  state.blindMode = true;
  preferencePanel.hidden = false;
  updateAuditionControls();
  renderCandidates();
  renderPreferenceSession();
  status.textContent = "Randomized blind preference session started";
}

function currentPreferencePair() {
  const session = state.preferenceSession;
  if (!session) return null;
  return session.pairs[session.pairIndex] || null;
}

function playPreferenceSide(sideIndex) {
  const pair = currentPreferencePair();
  if (!pair) return;
  const entry = pair[sideIndex];
  const candidate = candidateById(entry.candidateId);
  if (!candidate) return;

  state.activeCandidateId = candidate.id;
  state.selected = candidate.layers;
  renderRecipe();
  renderCandidates();
  previewCandidate(candidate);
}

function votePreferenceSide(sideIndex) {
  const session = state.preferenceSession;
  const pair = currentPreferencePair();
  if (!session || !pair || session.revealed) return;

  const winner = pair[sideIndex];
  const loser = pair[sideIndex === 0 ? 1 : 0];
  session.votes.push({
    leftAlias: pair[0].alias,
    rightAlias: pair[1].alias,
    winnerAlias: winner.alias,
    winnerCandidateId: winner.candidateId,
    loserCandidateId: loser.candidateId,
  });
  session.pairIndex += 1;
  stopAll();
  renderPreferenceSession();
}

function revealPreferenceSession() {
  const session = state.preferenceSession;
  if (!session) return;
  if (session.votes.length !== session.pairs.length) return;

  session.revealed = true;
  state.blindMode = false;
  updateAuditionControls();
  renderCandidates();
  renderPreferenceSession();
  status.textContent = "Preference identities revealed";
}

function applyPreferenceWinner() {
  const session = state.preferenceSession;
  if (!session || !session.revealed) return;

  const winnerId = preferenceWinner(session);
  if (!winnerId) return;

  state.candidates.forEach(function (candidate) {
    if (candidate.decision === "selected") {
      candidate.decision = "undecided";
    }
  });

  const winner = candidateById(winnerId);
  if (!winner) return;
  winner.decision = "selected";
  session.applied = true;
  state.activeCandidateId = winner.id;
  state.selected = winner.layers;

  renderRecipe();
  renderCandidates();
  renderPreferenceSession();
  status.textContent =
    "Preference winner applied · Candidate " + winner.label;
}

function renderPreferenceSession() {
  const session = state.preferenceSession;
  if (!session) {
    preferencePanel.hidden = true;
    return;
  }

  preferencePanel.hidden = false;
  const complete = session.votes.length === session.pairs.length;
  preferenceProgress.textContent =
    String(session.votes.length) + " / " + String(session.pairs.length);

  if (!complete) {
    const pair = currentPreferencePair();
    preferencePair.hidden = false;
    preferenceReveal.hidden = true;
    preferenceRevealButton.disabled = true;
    preferenceApply.disabled = true;
    preferenceTitle.textContent = "Which sound do you prefer?";
    preferenceMessage.textContent =
      "Pair " +
      String(session.pairIndex + 1) +
      " of " +
      String(session.pairs.length) +
      " · identity remains hidden";

    preferenceLeftLabel.textContent = pair[0].alias;
    preferenceRightLabel.textContent = pair[1].alias;
    preferenceLeftPlay.textContent = "▶ Play " + pair[0].alias;
    preferenceRightPlay.textContent = "▶ Play " + pair[1].alias;
    preferenceLeftVote.textContent = "Prefer " + pair[0].alias;
    preferenceRightVote.textContent = "Prefer " + pair[1].alias;
    return;
  }

  preferencePair.hidden = true;
  preferenceRevealButton.disabled = session.revealed;
  preferenceTitle.textContent = session.revealed
    ? "Preference reveal"
    : "Voting complete";
  preferenceMessage.textContent = session.revealed
    ? "Random aliases are now mapped back to Candidates."
    : "All pairwise votes are complete. Reveal when ready.";

  if (!session.revealed) {
    preferenceReveal.hidden = true;
    preferenceApply.disabled = true;
    return;
  }

  const scores = preferenceScores(session);
  const winnerId = preferenceWinner(session);
  preferenceReveal.hidden = false;
  preferenceReveal.replaceChildren();

  session.mapping.forEach(function (entry) {
    const candidate = candidateById(entry.candidateId);
    const row = document.createElement("div");
    row.className = "preference-reveal-row";

    const identity = document.createElement("strong");
    identity.textContent =
      entry.alias +
      " = " +
      (candidate ? "Candidate " + candidate.label : "missing Candidate");

    const score = document.createElement("span");
    const wins = scores.get(entry.candidateId) || 0;
    score.textContent =
      String(wins) + " win" + (wins === 1 ? "" : "s");

    row.append(identity, score);
    preferenceReveal.appendChild(row);
  });

  const verdict = document.createElement("p");
  verdict.className = "preference-verdict";
  if (winnerId) {
    const winner = candidateById(winnerId);
    verdict.textContent =
      "Session winner: Candidate " +
      (winner ? winner.label : "?") +
      " · Apply winner is explicit.";
  } else {
    verdict.textContent =
      "Tie: no Candidate decision will be applied automatically.";
  }
  preferenceReveal.appendChild(verdict);

  preferenceApply.disabled = !winnerId || session.applied;
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
  status.textContent =
    "Candidate " + candidate.label + " · " + candidate.decision;
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
  label.textContent = displayCandidateLabel(candidate);

  const titleMeta = document.createElement("div");
  const badge = document.createElement("span");
  badge.className = "candidate-badge";
  badge.textContent =
    state.preferenceSession && !state.preferenceSession.revealed
      ? "blind"
      : candidate.decision;
  const lineage = document.createElement("div");
  lineage.className = "candidate-meta blind-sensitive";
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
  edit.hidden = Boolean(
    state.preferenceSession && !state.preferenceSession.revealed
  );
  edit.addEventListener("click", function () {
    loadCandidate(candidate.id);
  });

  head.append(title, edit);

  const delta = document.createElement("div");
  delta.className = "candidate-delta blind-sensitive";
  const changes = candidateDeltaCount(candidate);
  delta.textContent =
    String(candidate.layers.length) +
    " layers · " +
    String(changes) +
    (changes === 1 ? " change" : " changes") +
    " vs base";

  const sourceSummary = document.createElement("div");
  sourceSummary.className = "candidate-sources blind-sensitive";
  sourceSummary.textContent = candidate.layers
    .map(function (layer) {
      return layer.sound.name;
    })
    .join(" + ");

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
  copy.hidden = Boolean(
    state.preferenceSession && !state.preferenceSession.revealed
  );
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

  if (state.preferenceSession && !state.preferenceSession.revealed) {
    decisions.hidden = true;
    reason.hidden = true;
  }

  card.append(head, delta, sourceSummary, actions, decisions, reason);
  return card;
}

function renderCandidates() {
  candidateBoard.replaceChildren();

  if (state.candidates.length === 0) {
    candidateHelp.hidden = false;
    downloadBoardButton.disabled = true;
    clearBoardButton.disabled = true;
    cancelSequentialAudition();
    state.blindMode = false;
    state.preferenceSession = null;
    preferencePanel.hidden = true;
    updateAuditionControls();
    renderIntakeSessions();
    return;
  }

  candidateHelp.hidden = true;
  candidatesForDisplay().forEach(function (candidate) {
    candidateBoard.appendChild(renderCandidateCard(candidate));
  });
  downloadBoardButton.disabled = false;
  clearBoardButton.disabled = false;
  updateAuditionControls();
  renderIntakeSessions();
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

blindModeButton.addEventListener("click", toggleBlindMode);
sequenceCandidatesButton.addEventListener("click", startSequentialAudition);
previousCandidateButton.addEventListener("click", function () {
  moveCandidate(-1, true);
});
nextCandidateButton.addEventListener("click", function () {
  moveCandidate(1, true);
});
preferenceSessionButton.addEventListener("click", function () {
  if (state.preferenceSession) {
    closePreferenceSession();
  } else {
    startPreferenceSession();
  }
});
preferenceLeftPlay.addEventListener("click", function () {
  playPreferenceSide(0);
});
preferenceRightPlay.addEventListener("click", function () {
  playPreferenceSide(1);
});
preferenceLeftVote.addEventListener("click", function () {
  votePreferenceSide(0);
});
preferenceRightVote.addEventListener("click", function () {
  votePreferenceSide(1);
});
preferenceRevealButton.addEventListener("click", revealPreferenceSession);
preferenceApply.addEventListener("click", applyPreferenceWinner);
preferenceClose.addEventListener("click", closePreferenceSession);

clearBoardButton.addEventListener("click", function () {
  stopAll();
  state.blindMode = false;
  state.preferenceSession = null;
  preferencePanel.hidden = true;
  state.candidates = [];
  state.activeCandidateId = null;
  state.boardBaseRecipe = null;
  state.selected = [];
  renderRecipe();
  renderCandidates();
  renderIntakeSessions();
  status.textContent = "Candidate Board cleared";
});

function isTypingTarget(target) {
  if (!(target instanceof Element)) return false;
  if (target.isContentEditable) return true;
  return Boolean(target.closest("input, textarea, select"));
}

document.addEventListener("keydown", function (event) {
  if (state.candidates.length === 0) return;
  if (isTypingTarget(event.target)) return;
  if (event.ctrlKey || event.metaKey || event.altKey) return;

  const key = event.key.toLowerCase();
  const active = selectedCandidate();
  const preference = state.preferenceSession;

  if (preference && !preference.revealed) {
    if (event.key === "1") {
      event.preventDefault();
      playPreferenceSide(0);
      return;
    }
    if (event.key === "2") {
      event.preventDefault();
      playPreferenceSide(1);
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      votePreferenceSide(0);
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      votePreferenceSide(1);
      return;
    }
    if (key === "r") {
      event.preventDefault();
      revealPreferenceSession();
      return;
    }
    if (key === "p") {
      event.preventDefault();
      closePreferenceSession();
      return;
    }
    if (event.key === "Escape") {
      stopAll();
      status.textContent = "Preference audio stopped";
      return;
    }
    return;
  }

  if (event.key === " ") {
    event.preventDefault();
    if (active) previewCandidate(active);
    return;
  }

  if (event.key === "ArrowRight") {
    event.preventDefault();
    moveCandidate(1, true);
    return;
  }

  if (event.key === "ArrowLeft") {
    event.preventDefault();
    moveCandidate(-1, true);
    return;
  }

  if (event.key === "Escape") {
    stopAll();
    status.textContent = "Audition stopped";
    return;
  }

  if (key === "b") {
    event.preventDefault();
    toggleBlindMode();
    return;
  }

  if (key === "q") {
    event.preventDefault();
    startSequentialAudition();
    return;
  }

  if (key === "p") {
    event.preventDefault();
    if (state.preferenceSession) {
      closePreferenceSession();
    } else {
      startPreferenceSession();
    }
    return;
  }

  if (!active) return;

  if (key === "f") {
    event.preventDefault();
    setCandidateDecision(active.id, "favorite");
  } else if (key === "x") {
    event.preventDefault();
    setCandidateDecision(active.id, "reject");
  } else if (key === "s") {
    event.preventDefault();
    setCandidateDecision(active.id, "selected");
  }
});

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
      renderIntakeSessions();
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
  updateAuditionControls();
  renderRecipe();
  renderCandidates();
  window.setInterval(function () {
    refreshCatalog({ quiet: true });
  }, 2500);
}

boot();
