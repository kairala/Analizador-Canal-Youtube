# tests/test_desktop_spec.py
#
# build/desktop.spec is not an importable module -- PyInstaller execs it with
# special globals (Analysis, EXE, BUNDLE, PYZ, SPECPATH, ...) injected at
# build time, so it can't be unit tested directly without running a full
# PyInstaller build (slow, and only meaningful on macOS/Windows toolchains).
# These are lightweight content checks for the packaging fixes; the actual
# end-to-end verification -- that `pyinstaller build/desktop.spec --distpath
# dist` produces a real dist/yt-data-extractor.app bundle (not a bare
# executable) -- was done manually; see the fix report.
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parent.parent / "build" / "desktop.spec"
README_PATH = Path(__file__).resolve().parent.parent / "README.md"


def _spec_text():
    return SPEC_PATH.read_text(encoding="utf-8")


def test_spec_imports_sys_for_the_platform_check():
    spec = _spec_text()
    assert "import sys" in spec


def test_spec_disables_upx():
    # upx=True is a known risk for corrupting arm64 Mach-O binaries.
    spec = _spec_text()
    assert "upx=False" in spec
    assert "upx=True" not in spec


def test_spec_adds_a_macos_only_bundle_step():
    # A bare Mach-O executable isn't double-clickable in Finder the way a
    # .app bundle is -- double-clicking it opens Terminal and runs it there.
    spec = _spec_text()
    assert 'sys.platform == "darwin"' in spec
    assert "BUNDLE(" in spec

    bundle_block = spec.split("BUNDLE(", 1)[1]
    assert 'name="yt-data-extractor.app"' in bundle_block
    assert 'bundle_identifier="com.ytdataextractor.app"' in bundle_block


def test_readme_warns_about_gatekeeper_blocking_the_unsigned_macos_app():
    # The macOS binary is unsigned/unnotarized, so Gatekeeper blocks the
    # first launch of a double-click. The user needs to right-click and
    # choose "Abrir" (Open) the first time only.
    readme = README_PATH.read_text(encoding="utf-8")
    section = readme.split("## 7. App local com interface (binário)", 1)[1]
    assert "Gatekeeper" in section
    assert "Abrir" in section
