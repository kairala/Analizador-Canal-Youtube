# tests/test_build_workflow.py
#
# actions/upload-artifact does not preserve Unix permissions (e.g. the
# executable +x bit), so a bare uploaded dist/ would need a manual `chmod +x`
# before it could run at all on macOS/Linux. These checks confirm the
# workflow archives dist/ into a permission-preserving tarball before
# uploading on non-Windows runners, while Windows keeps uploading dist/
# as-is (its .exe doesn't need the executable bit preserved the same way).
#
# PyYAML isn't a declared project dependency, so this checks the raw text
# rather than parsing with yaml.safe_load -- the YAML syntax itself was
# validated manually (see the fix report).
from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "build-desktop.yml"


def _workflow_text():
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_workflow_archives_dist_into_a_tarball_before_uploading_on_non_windows():
    workflow = _workflow_text()
    assert "tar -czf dist.tar.gz -C dist ." in workflow

    archive_step = (
        "- name: Archive dist (preserve permissions)\n"
        "        if: runner.os != 'Windows'\n"
        "        run: tar -czf dist.tar.gz -C dist .\n"
    )
    assert archive_step in workflow


def test_workflow_uploads_the_tarball_on_non_windows_and_the_raw_dist_on_windows():
    workflow = _workflow_text()

    # exactly two upload-artifact steps: one for the tarball (non-Windows),
    # one for the raw dist/ (Windows)
    assert workflow.count("actions/upload-artifact@v4") == 2

    non_windows_upload_step = (
        "- uses: actions/upload-artifact@v4\n"
        "        if: runner.os != 'Windows'\n"
        "        with:\n"
        "          name: yt-data-extractor-${{ matrix.os }}\n"
        "          path: dist.tar.gz\n"
    )
    windows_upload_step = (
        "- uses: actions/upload-artifact@v4\n"
        "        if: runner.os == 'Windows'\n"
        "        with:\n"
        "          name: yt-data-extractor-${{ matrix.os }}\n"
        "          path: dist/\n"
    )
    assert non_windows_upload_step in workflow
    assert windows_upload_step in workflow
