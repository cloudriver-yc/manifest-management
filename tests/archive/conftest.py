import shutil
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_data"


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """If workspace is in clean slate mode, temporarily supply sample test fixtures for the test session,

    then cleanly restore the clean slate state afterwards.
    """
    app_groups_dir = WORKSPACE_ROOT / "ApplicationGroups"
    is_clean_slate = not any(app_groups_dir.iterdir()) if app_groups_dir.exists() else True

    if is_clean_slate and FIXTURES_DIR.exists():
        # Capture current clean slate files
        clean_apgs = WORKSPACE_ROOT / "cue" / "catalog" / "apgs"
        clean_envs = WORKSPACE_ROOT / "cue" / "catalog" / "environments" / "envs.cue"
        clean_custom = WORKSPACE_ROOT / "cue" / "catalog" / "extensions" / "custom.cue"
        clean_system = WORKSPACE_ROOT / "cue" / "catalog" / "system.cue"

        clean_apgs_content = {f.name: f.read_text(encoding="utf-8") for f in clean_apgs.glob("*.cue")}
        clean_envs_content = clean_envs.read_text(encoding="utf-8") if clean_envs.exists() else ""
        clean_custom_content = clean_custom.read_text(encoding="utf-8") if clean_custom.exists() else ""
        clean_system_content = clean_system.read_text(encoding="utf-8") if clean_system.exists() else ""

        # Copy fixture cue and ApplicationGroups into workspace
        shutil.copytree(FIXTURES_DIR / "ApplicationGroups", app_groups_dir, dirs_exist_ok=True)
        shutil.copytree(FIXTURES_DIR / "cue" / "catalog", WORKSPACE_ROOT / "cue" / "catalog", dirs_exist_ok=True)

        yield

        # Teardown: Restore clean slate
        for item in app_groups_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        for f in clean_apgs.glob("*.cue"):
            f.unlink()
        for name, content in clean_apgs_content.items():
            (clean_apgs / name).write_text(content, encoding="utf-8")

        if clean_envs_content:
            clean_envs.write_text(clean_envs_content, encoding="utf-8")
        if clean_custom_content:
            clean_custom.write_text(clean_custom_content, encoding="utf-8")
        if clean_system_content:
            clean_system.write_text(clean_system_content, encoding="utf-8")
    else:
        yield
