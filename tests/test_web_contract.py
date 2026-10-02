from mgal.server import WEB_ROOT


def test_candidate_board_static_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    for element_id in (
        "preview-mix",
        "stop-mix",
        "recipe-layers",
        "download-recipe",
        "seed-candidates",
        "candidate-board",
        "download-board",
        "refresh-sources",
        "intake-sessions",
        "intake-session-list",
        "clear-board",
        "blind-mode",
        "sequence-candidates",
        "previous-candidate",
        "next-candidate",
        "audition-position",
        "audition-shortcuts",
        "preference-session",
        "preference-panel",
        "preference-left-play",
        "preference-right-play",
        "preference-left-vote",
        "preference-right-vote",
        "preference-reveal-button",
        "preference-apply",
        "preference-evidence",
        "preference-close",
        "preference-archive",
        "refresh-preference-archive",
        "preference-archive-list",
        "preference-replay-panel",
        "preference-replay-prev",
        "preference-replay-next",
        "preference-replay-left-play",
        "preference-replay-right-play",
        "close-preference-replay",
        "decision-memory",
        "decision-memory-summary",
        "decision-memory-list",
        "refresh-decision-memory",
        "load-decision-context",
        "download-decision-context",
        "decision-context-panel",
        "decision-context-count",
        "decision-context-summary",
        "decision-context-stale",
        "decision-context-empty",
        "decision-context-list",
        "inspect-current-deltas",
        "download-delta-inspector",
        "delta-inspector-panel",
        "delta-inspector-count",
        "delta-inspector-summary",
        "delta-inspector-stale",
        "delta-inspector-list",
        "variation-brief-panel",
        "variation-reference",
        "variation-hypothesis",
        "variation-listening-for",
        "variation-dimension",
        "variation-action",
        "variation-amount",
        "variation-unit",
        "variation-note",
        "variation-preserve",
        "save-variation-brief",
        "variation-brief-list",
        "refresh-candidate-plans",
        "candidate-plan-empty",
        "candidate-plan-list",
    ):
        assert f'id="{element_id}"' in html

    for token in (
        "createBufferSource",
        "createGain",
        "offset_ms",
        "muted",
        "solo",
        "seedCandidates",
        "candidateDeltaCount",
        "parent_recipe_id",
        "revision",
        "lineage",
        "from_recipe_id",
        "favorite",
        "reject",
        "selected",
        "selected_candidate_id",
        "refreshCatalog",
        "catalogSignature",
        "sound.intake",
        "source-type-badge",
        "provider-badge",
        "intake-badge",
        "intakeGroups",
        "seedIntakeSession",
        "renderIntakeSessions",
        "makeLayerFromRecipeLayer",
        "/seed-board",
        "updateAuditionControls",
        "cancelSequentialAudition",
        "playSequentialCandidate",
        "startSequentialAudition",
        "toggleBlindMode",
        "moveCandidate",
        "isTypingTarget",
        "document.addEventListener(\"keydown\"",
        "preserveSequence",
        "onComplete",
        "randomUint32",
        "shuffleCopy",
        "preferencePairs",
        "preferenceScores",
        "preferenceWinner",
        "startPreferenceSession",
        "votePreferenceSide",
        "revealPreferenceSession",
        "applyPreferenceWinner",
        "renderPreferenceSession",
        "displayCandidateLabel",
        "candidatesForDisplay",
        "preferenceEvidenceRequest",
        "downloadPreferenceEvidence",
        "/api/preference-archive",
        "/api/preferences",
        "appliedCandidateId",
        "refreshPreferenceArchive",
        "renderPreferenceArchive",
        "openPreferenceReplay",
        "renderPreferenceReplay",
        "playPreferenceReplaySide",
        "replayRecipeLayers",
        "recoverPreferenceArchive",
        "/recover",
        "Recover sources",
        "source_status",
        "promotePreferenceArchive",
        "refreshDecisionMemory",
        "renderDecisionMemory",
        "/api/decision-memory",
        "/promote",
        "Promote memory",
        "loadDecisionContext",
        "renderDecisionContext",
        "markDecisionContextStale",
        "downloadDecisionContext",
        "/api/decision-context",
        "reference_only",
        "selection_effect",
        "inspectCurrentDeltas",
        "renderDeltaInspector",
        "markDeltaInspectorStale",
        "downloadDeltaInspector",
        "/api/decision-context-inspect",
        "observation_only",
        "mutation_effect",
        "Current − past winner",
        "Current − past loser",
        "saveVariationBrief",
        "refreshVariationBriefs",
        "renderVariationBriefs",
        "variationReferencePayload",
        "/api/variation-briefs",
        "human_explicit",
        "candidate_generation",
        "compileCandidatePlan",
        "refreshCandidatePlans",
        "renderCandidatePlans",
        "formatPlanChange",
        "/api/candidate-plans",
        "Compile plan",
        "Plan ready",
        "manual_required",
        "recipe_materialization",
    ):
        assert token in js


def test_browser_shell_has_no_external_runtime_dependency():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    assert "https://" not in html
    assert "http://" not in html


def test_audition_board_has_intake_metadata_slots():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    for class_name in (
        "source-context",
        "source-badges",
        "source-type-badge",
        "provider-badge",
        "intake-badge",
        "source-prompt",
    ):
        assert f'class="{class_name}"' in html or f".{class_name}" in css

    assert "intake-card" in css


def test_intake_seed_ui_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    assert "Seed A/B/C from an intake" in html
    assert "Clear board" in html
    assert "first 3 seed" in js
    assert "state.candidates.length > 0" in js
    assert ".intake-session-card" in css
    assert ".intake-seed" in css
    assert "candidate-sources" in js
    assert ".candidate-sources" in css


def test_blind_sequential_audition_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    assert "Blind: Off" in html
    assert "▶ A→B→C" in html
    assert "Space replay" in html
    assert "F favorite" in html
    assert "X reject" in html
    assert "S select" in html
    assert "B blind" in html
    assert "Q sequence" in html
    assert "Esc stop" in html

    assert "sequenceRunning: false" in js
    assert "sequenceIndex: -1" in js
    assert "playbackToken: 0" in js
    assert "setTimeout(function ()" in js
    assert "playSequentialCandidate(index + 1)" in js
    assert "index >= state.candidates.length" in js
    assert "candidate.decision" in js
    assert 'setCandidateDecision(active.id, "favorite")' in js
    assert 'setCandidateDecision(active.id, "reject")' in js
    assert 'setCandidateDecision(active.id, "selected")' in js
    assert 'target.closest("input, textarea, select")' in js

    assert ".blind-mode .blind-sensitive" in css
    assert ".blind-mode .intake-session-meta" in css
    assert "#blind-mode.active" in css
    assert "#sequence-candidates.active" in css


def test_audition_modes_do_not_enter_candidate_board_payload():
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    start = js.index("function boardPayload()")
    end = js.index("function downloadJson", start)
    board_payload_code = js[start:end]

    assert "blindMode" not in board_payload_code
    assert "sequenceRunning" not in board_payload_code
    assert "sequenceIndex" not in board_payload_code


def test_randomized_blind_preference_session_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    assert "◇ Preference" in html
    assert "RANDOMIZED BLIND" in html
    assert "Which sound do you prefer?" in js
    assert "Apply winner" in html
    assert "1/2 play" in html
    assert "←/→ prefer" in html

    assert "window.crypto.getRandomValues" in js
    assert 'const aliases = ["X", "Y", "Z"]' in js
    assert "preferencePairs(mapping)" in js
    assert "pair.reverse()" in js
    assert "shuffleCopy(pairs)" in js
    assert "session.votes.length !== session.pairs.length" in js
    assert "leaders.length === 1" in js
    assert "Tie: no Candidate decision will be applied automatically." in js
    assert 'winner.decision = "selected"' in js
    assert "session.applied = true" in js

    assert ".preference-panel" in css
    assert ".preference-side" in css
    assert ".preference-reveal-row" in css
    assert ".preference-mode .candidate-reason" in css


def test_preference_session_hides_identity_until_reveal():
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert "displayCandidateLabel(candidate)" in js
    assert 'state.preferenceSession && !state.preferenceSession.revealed' in js
    assert '? "blind"' in js
    assert "edit.hidden = Boolean(" in js
    assert "copy.hidden = Boolean(" in js
    assert "decisions.hidden = true" in js
    assert "reason.hidden = true" in js
    assert "state.blindMode = true" in js
    assert "session.revealed = true" in js
    assert "state.blindMode = false" in js


def test_preference_session_does_not_enter_candidate_board_payload():
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    start = js.index("function boardPayload()")
    end = js.index("function downloadJson", start)
    board_payload_code = js[start:end]

    for transient in (
        "preferenceSession",
        "mapping",
        "pairs",
        "pairIndex",
        "votes",
        "revealed",
        "applied",
    ):
        assert transient not in board_payload_code


def test_preference_keyboard_intercepts_pairwise_vote_before_navigation():
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    start = js.index('document.addEventListener("keydown"')
    end = js.index("function applyFilter", start)
    keyboard = js[start:end]

    pref = keyboard.index("if (preference && !preference.revealed)")
    vote_right = keyboard.index("votePreferenceSide(1)", pref)
    normal_right = keyboard.index(
        'if (event.key === "ArrowRight")',
        vote_right + 1,
    )

    assert vote_right < normal_right
    assert 'if (event.key === "1")' in keyboard
    assert 'if (event.key === "2")' in keyboard
    assert 'if (key === "r")' in keyboard
    assert 'if (key === "p")' in keyboard


def test_preference_evidence_export_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert "Archive + download" in html
    assert 'method: "POST"' in js
    assert '"Content-Type": "application/json"' in js
    assert "candidate_board: boardPayload()" in js
    assert "mapping: session.mapping" in js
    assert "pairs: session.pairs" in js
    assert "votes: session.votes" in js
    assert "appliedCandidateId: session.appliedCandidateId" in js
    assert "preferenceEvidence.disabled = !session.revealed" in js
    assert 'fetch("/api/preference-archive"' in js
    assert "await refreshPreferenceArchive({ quiet: true })" in js


def test_preference_archive_replay_ui_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    assert "PREFERENCE ARCHIVE" in html
    assert "Replay past blind sessions" in html
    assert "VERIFIED REPLAY" in html
    assert "Prev pair" in html
    assert "Next pair" in html

    assert 'fetch("/api/preferences"' in js
    assert '"/replay"' in js
    assert "state.preferenceReplayPairIndex" in js
    assert "pair.left_recipe" in js
    assert "pair.right_recipe" in js
    assert "recipe.layers.map(makeLayerFromRecipeLayer)" in js
    assert "Recorded preference:" in js

    assert ".preference-archive" in css
    assert ".preference-archive-card" in css
    assert ".preference-replay-panel" in css
    assert ".preference-replay-chip" in css


def test_preference_source_recovery_ui_contract():
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    assert "entry.recoverable" in js
    assert '"Sources unresolved · "' in js
    assert '"Recover sources"' in js
    assert 'method: "POST"' in js
    assert '"/recover"' in js
    assert "recovery.resolved_count" in js
    assert "recovery.ambiguous_count" in js
    assert "recovery.missing_count" in js
    assert 'entry.source_status === "relinked"' in js
    assert "sources relinked by SHA-256" in js
    assert ".recovery-action" in css


def test_decision_memory_ui_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    assert "DECISION MEMORY" in html
    assert "Promoted listening observations" in html
    assert "Only explicit promotions enter memory." in html
    assert "never auto-select a Candidate" in html

    assert "entry.promotable" in js
    assert "entry.promoted" in js
    assert '"Promote memory"' in js
    assert '"/promote"' in js
    assert 'fetch("/api/decision-memory"' in js
    assert "pairwise observation" in js
    assert "observed Δ layers" in js
    assert "winner_candidate_id" in js
    assert "loser_candidate_id" in js

    assert ".decision-memory" in css
    assert ".decision-memory-row" in css
    assert ".memory-promotion-action" in css


def test_decision_context_reference_only_ui_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    assert "Load memory context" in html
    assert "Download context pack" in html
    assert "MEMORY CONTEXT · REFERENCE ONLY" in html
    assert "does not rank, copy, select, or apply any Candidate" in html
    assert "Intent changed. Reload context" in html

    assert 'fetch(' in js
    assert '"/api/decision-context?intent="' in js
    assert '"&limit=6"' in js
    assert "state.decisionContextStale" in js
    assert "normalizeIntentForContext" in js
    assert "downloadDecisionContextButton.disabled" in js
    assert "entry.match.matched_terms" in js
    assert "observed Δ layers" in js

    context_start = js.index("function renderDecisionContext()")
    context_end = js.index("function formatSignedNumber", context_start)
    context_code = js[context_start:context_end]
    assert "setCandidateDecision" not in context_code
    assert "copyActiveInto" not in context_code
    assert "applyPreferenceWinner" not in context_code

    assert ".decision-context-panel" in css
    assert ".decision-context-row" in css
    assert ".decision-context-stale" in css


def test_delta_inspector_observation_only_ui_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    assert "Inspect current deltas" in html
    assert "Download delta inspector" in html
    assert "CURRENT RECIPE · OBSERVATION ONLY" in html
    assert "No closeness score, ranking, or automatic Recipe change" in html
    assert "Current Recipe or Context changed." in html

    assert '"/api/decision-context-inspect"' in js
    assert "current_recipe: recipePayload()" in js
    assert 'result.usage.role !== "observation_only"' in js
    assert 'result.usage.selection_effect !== "none"' in js
    assert 'result.usage.mutation_effect !== "none"' in js
    assert "current_only_source_count" in js
    assert "reference_only_source_count" in js
    assert "state.deltaInspectorStale" in js
    assert "markDeltaInspectorStale()" in js

    inspector_start = js.index("function renderDeltaInspector()")
    inspector_end = js.index("function markDeltaInspectorStale", inspector_start)
    inspector_code = js[inspector_start:inspector_end]
    assert "setCandidateDecision" not in inspector_code
    assert "copyActiveInto" not in inspector_code
    assert "applyPreferenceWinner" not in inspector_code
    assert "similarity" not in inspector_code.lower()
    assert "closer" not in inspector_code.lower()

    assert ".delta-inspector-panel" in css
    assert ".delta-inspector-card" in css
    assert ".delta-inspector-reference" in css


def test_variation_brief_human_authorship_ui_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    assert "HUMAN HYPOTHESIS" in html
    assert "Variation Brief" in html
    assert "What do you want to try, and why?" in html
    assert "What audible change would make this experiment informative?" in html
    assert "does not generate or mutate a Recipe" in html

    assert '"/api/variation-briefs"' in js
    assert "hypothesis: hypothesis" in js
    assert "listening_for: listeningFor" in js
    assert "planned_change:" in js
    assert "preserve:" in js
    assert "reference: variationReferencePayload()" in js
    assert 'result.brief.human_input.authorship !== "human_explicit"' in js
    assert 'result.brief.authority.recipe_mutation !== "none"' in js
    assert 'result.brief.authority.candidate_selection !== "none"' in js
    assert 'result.brief.authority.candidate_generation !== "none"' in js

    start = js.index("async function saveVariationBrief()")
    end = js.index("function syncVariationUnit", start)
    brief_code = js[start:end]
    assert "recipePayload()" not in brief_code
    assert "copyActiveInto" not in brief_code
    assert "setCandidateDecision" not in brief_code
    assert "applyPreferenceWinner" not in brief_code

    assert ".variation-brief-panel" in css
    assert ".variation-change-grid" in css
    assert ".variation-brief-card" in css


def test_candidate_plan_non_materialized_ui_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    css = (WEB_ROOT / "style.css").read_text(encoding="utf-8")

    assert "CANDIDATE PLAN" in html
    assert "Control / Hypothesis / Contrast" in html
    assert "Plans describe experiments only." in html
    assert "do not contain materialized Recipes or select Candidates" in html

    assert '"Compile plan"' in js
    assert '"Plan ready"' in js
    assert '"Plan needs C input"' in js
    assert '"/api/candidate-plans"' in js
    assert "variation_brief_id" in js
    assert 'result.plan.authority.recipe_materialization !== "none"' in js
    assert 'result.plan.authority.candidate_generation !== "none"' in js
    assert 'result.plan.authority.candidate_selection !== "none"' in js

    start = js.index("async function compileCandidatePlan")
    end = js.index("async function refreshVariationBriefs", start)
    plan_code = js[start:end]
    assert "recipePayload()" not in plan_code
    assert "setCandidateDecision" not in plan_code
    assert "applyPreferenceWinner" not in plan_code

    assert ".candidate-plan-shelf" in css
    assert ".candidate-plan-card" in css
    assert ".candidate-plan-variant" in css
    assert ".manual-required" in css
