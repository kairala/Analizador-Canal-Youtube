# tests/test_frontend_error_handling.py
#
# Complements tests/test_app_js_fetchjson.py (which exercises the `fetchJSON`
# helper's behavior under Node) with structural checks, served the same way
# tests/test_web_static.py checks static assets: every fetch-based caller
# must route through fetchJSON and handle its rejection, the Browse tab must
# have somewhere to show an error, and a dropped SSE stream must leave a
# visible trace in the log instead of failing silently.
import re

from fastapi.testclient import TestClient

from src.web.app import create_app


def _app_js():
    client = TestClient(create_app())
    response = client.get("/static/app.js")
    assert response.status_code == 200
    return response.text


def _index_html():
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    return response.text


def test_every_fetch_call_is_routed_through_the_fetchjson_helper():
    app_js = _app_js()

    # The only direct `fetch(` call left in the file must be the one inside
    # fetchJSON itself -- every other caller must go through the helper so a
    # non-JSON error body (e.g. Starlette's plain-text 500) can't crash it.
    assert app_js.count("await fetch(") == 1
    assert "async function fetchJSON(" in app_js


def test_previously_unguarded_callers_now_catch_and_report_errors():
    app_js = _app_js()

    for name, error_element in [
        ("refreshSetupStatus", "setup-error"),
        ("loadAnalyzable", "analyze-error"),
        ("loadResults", "browse-error"),
        ("showResult", "browse-error"),
    ]:
        match = re.search(rf"async function {name}\([\s\S]*?\n\}}\n", app_js)
        assert match, f"{name} not found in app.js"
        body = match.group(0)
        assert "try {" in body, f"{name} has no try/catch around its fetchJSON call"
        assert "catch (error)" in body, f"{name} has no catch clause"
        assert error_element in body, f"{name} does not populate #{error_element} on failure"


def test_stream_job_leaves_a_visible_trace_when_the_sse_connection_drops():
    app_js = _app_js()

    match = re.search(r"function streamJob\([\s\S]*?\n\}\n", app_js)
    assert match, "streamJob not found in app.js"
    body = match.group(0)
    assert "source.onerror" in body
    assert "conexão perdida antes de concluir" in body


def test_browse_tab_has_an_error_element():
    index_html = _index_html()

    assert 'id="browse-error"' in index_html
    # It must be inside the browse section, not some other tab.
    browse_section = index_html.split('<section class="tab" data-tab="browse">', 1)[1]
    assert 'id="browse-error"' in browse_section.split("</section>", 1)[0]


def test_extract_tab_has_a_status_element_for_the_oauth_popup_notice():
    index_html = _index_html()

    assert 'id="extract-status"' in index_html
    extract_section = index_html.split('<section class="tab" data-tab="extract">', 1)[1]
    assert 'id="extract-status"' in extract_section.split("</section>", 1)[0]


def test_load_videos_warns_about_the_oauth_popup_before_fetching_and_clears_it_either_way():
    # loadVideos() is the first call that can trigger the Google OAuth
    # browser popup on first use (via GET /api/videos -> get_credentials).
    # The user must be warned a browser window may open before that call
    # fires, and the notice must be cleared whether the call succeeds or
    # fails -- not left stuck on screen forever.
    app_js = _app_js()

    match = re.search(r"async function loadVideos\([\s\S]*?\n\}\n", app_js)
    assert match, "loadVideos not found in app.js"
    body = match.group(0)

    status_message_index = body.find("Abrindo o navegador para autorizar acesso ao Google")
    fetch_call_index = body.find("fetchJSON(\"/api/videos\")")
    assert status_message_index != -1, "loadVideos does not warn about the OAuth popup"
    assert fetch_call_index != -1, "loadVideos does not call fetchJSON(\"/api/videos\")"
    assert status_message_index < fetch_call_index, "status message must be shown before the fetch"

    # cleared on both the success path and the catch block
    assert body.count('$("extract-status").textContent = ""') >= 2
