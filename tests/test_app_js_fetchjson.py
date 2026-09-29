# tests/test_app_js_fetchjson.py
#
# The `fetchJSON` helper in static/app.js exists specifically so that a
# non-JSON error body (e.g. Starlette's default plain-text 500 response,
# `Internal Server Error`) doesn't crash every caller with an unhandled
# `SyntaxError` from `response.json()`. That behavior lives entirely in the
# browser, so it's exercised here by running the actual helper (extracted
# verbatim from the served file) under Node with a stubbed `fetch`.
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parent.parent / "static" / "app.js"

NODE_DRIVER = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const match = src.match(/async function fetchJSON\([\s\S]*?\n\}\n/);
if (!match) {
  console.error("fetchJSON function not found in app.js");
  process.exit(1);
}
eval(match[0]);

async function main() {
  // ok response with a JSON body is parsed and returned
  global.fetch = async () => ({ ok: true, status: 200, text: async () => JSON.stringify({ a: 1 }) });
  const ok = await fetchJSON("/x");
  if (ok.a !== 1) throw new Error("expected parsed JSON body, got " + JSON.stringify(ok));

  // ok response with an empty body returns null instead of throwing
  global.fetch = async () => ({ ok: true, status: 204, text: async () => "" });
  const empty = await fetchJSON("/x");
  if (empty !== null) throw new Error("expected null for empty ok body, got " + JSON.stringify(empty));

  // error response with a JSON {detail} body throws using that message
  global.fetch = async () => ({
    ok: false,
    status: 400,
    text: async () => JSON.stringify({ detail: "mensagem de erro" }),
  });
  try {
    await fetchJSON("/x");
    throw new Error("expected a throw for a non-ok response");
  } catch (e) {
    if (e.message !== "mensagem de erro") throw new Error("wrong message: " + e.message);
  }

  // This is the bug fetchJSON exists to fix: Starlette's default 500
  // response is the literal text "Internal Server Error" with
  // content-type: text/plain, not JSON. Before the fix, callers did
  // `await response.json()` directly, which throws a SyntaxError on this
  // body -- silently, since these were unawaited click handlers. fetchJSON
  // must not throw a JSON-parse error here; it must throw a normal Error
  // carrying the raw text so a caller's catch block can show it.
  global.fetch = async () => ({ ok: false, status: 500, text: async () => "Internal Server Error" });
  try {
    await fetchJSON("/x");
    throw new Error("expected a throw for a non-JSON error body");
  } catch (e) {
    if (e.message !== "Internal Server Error") throw new Error("wrong message: " + e.message);
  }

  console.log("ALL_OK");
}

main().catch((e) => {
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(1);
});
"""


@pytest.fixture(scope="module")
def node_binary():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node não está disponível para exercitar static/app.js")
    return node


def test_fetchjson_parses_ok_bodies_and_throws_readable_errors_for_non_ok_responses(tmp_path, node_binary):
    driver_path = tmp_path / "fetchjson_driver.js"
    driver_path.write_text(NODE_DRIVER, encoding="utf-8")

    result = subprocess.run(
        [node_binary, str(driver_path), str(APP_JS)],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL_OK" in result.stdout
