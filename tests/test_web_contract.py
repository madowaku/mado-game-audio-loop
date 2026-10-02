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
