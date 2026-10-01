from mgal.server import WEB_ROOT


def test_layer_mixer_static_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    for element_id in ("preview-mix", "stop-mix", "recipe-layers", "download-recipe"):
        assert f'id="{element_id}"' in html

    for token in (
        "createBufferSource",
        "createGain",
        "offset_ms",
        "muted",
        "solo",
        "Preview mix",
    ):
        assert token in js


def test_browser_shell_has_no_external_runtime_dependency():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    assert "https://" not in html
    assert "http://" not in html
