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
        "preference-close",
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
