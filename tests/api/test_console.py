# tests/api/test_console.py
"""Web GUI(apps/AIDC-Console)の静的ファイルの配信(api/main.pyの/appのmount)。"""


def test_console_index_is_served(client):
    resp = client.get("/app/")
    assert resp.status_code == 200
    assert "<title>AIDC Console</title>" in resp.text


def test_console_scripts_are_served(client):
    for path in (
        "/app/static/app.js",
        "/app/static/app.css",
        "/app/static/vendor/js-yaml.min.js",
        "/app/static/project_overview_panel.js",
        "/app/static/project_genai_tab.js",
        "/app/static/data_viewer_panel.js",
        "/app/static/dramaturgy_editor_panel.js",
        "/app/static/proposal_form.js",
        "/app/static/ai_build_panel.js",
    ):
        assert client.get(path).status_code == 200, path
