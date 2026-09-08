import os
from pathlib import Path
import shutil
import sys
import pytest
import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS_DIR = WORKSPACE_ROOT / ".agents" / "skills" / "manifest-management" / "scripts"
if str(SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS_DIR))

from py_engine.cue_client import CueClient
from py_engine.graph import RelationalGraph
from py_engine.sync_engine import SyncEngine


@pytest.fixture(scope="module")
def cue_client():
    client = CueClient(str(WORKSPACE_ROOT))
    ok, err = client.vet()
    assert ok, f"Initial CUE validation failed: {err}"
    return client


@pytest.fixture(scope="function")
def clean_custom_and_dirs():
    custom_file = WORKSPACE_ROOT / "cue" / "catalog" / "extensions" / "custom.cue"
    original_custom = custom_file.read_text(encoding="utf-8") if custom_file.exists() else ""
    yield
    # Restore custom.cue
    if original_custom:
        custom_file.write_text(original_custom, encoding="utf-8")
    # Clean up any test directories created
    ocp52_dir = WORKSPACE_ROOT / "ApplicationGroups" / "NCBS" / "sit" / "retail" / "DCE" / "ocp52"
    if ocp52_dir.exists():
        shutil.rmtree(ocp52_dir)
    # Resync to clean state
    engine = SyncEngine(str(WORKSPACE_ROOT))
    engine.sync_cue_to_dir(prune=True)


class TestSyncWorkflows:
    """Verifies bidirectional synchronization between CUE and hierarchical directory structure."""

    def test_01_cue_to_dir_hierarchy_structure(self, cue_client):
        """Verifies that CUE -> Directory export produces the exact required hierarchy."""
        engine = SyncEngine(str(WORKSPACE_ROOT))
        res = engine.sync_cue_to_dir()
        assert res["total_updated"] >= 0

        # Check NCBS UAT DCE ocp53
        ncbs_uat_ocp53 = WORKSPACE_ROOT / "ApplicationGroups" / "NCBS" / "uat" / "retail" / "DCE" / "ocp53"
        assert ncbs_uat_ocp53.exists()
        assert (ncbs_uat_ocp53 / "httproutes" / "ncbs-retail-orders-route.yaml").exists()
        assert (ncbs_uat_ocp53 / "gateway" / "agw-ncbs-retail-blue.yaml").exists()
        assert (ncbs_uat_ocp53 / "servicedefaults" / "retail-order-service-blue.yaml").exists()
        assert (ncbs_uat_ocp53 / "proxydefaults" / "global.yaml").exists()

        # Check Cross-DC pair in DCW ocp54
        ncbs_uat_ocp54 = WORKSPACE_ROOT / "ApplicationGroups" / "NCBS" / "uat" / "retail" / "DCW" / "ocp54"
        assert ncbs_uat_ocp54.exists()
        assert (ncbs_uat_ocp54 / "httproutes" / "ncbs-retail-orders-route.yaml").exists()

    def test_02_dir_to_cue_manual_file_addition_with_ocp52(self, cue_client, clean_custom_and_dirs):
        """Challenge Scenario: User manually creates a ServiceDefaults file under

        ApplicationGroups/NCBS/sit/retail/DCE/ocp52/servicedefaults/cb-payment-gateway.yaml.
        Verifies:
        1. Cluster ocp52 is automatically registered under SIT (DCE) in CUE.
        2. ServiceDefaults cb-payment-gateway is registered in CUE.
        3. CUE validation (cue vet) succeeds.
        """
        target_dir = WORKSPACE_ROOT / "ApplicationGroups" / "NCBS" / "sit" / "retail" / "DCE" / "ocp52" / "servicedefaults"
        target_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = target_dir / "cb-payment-gateway.yaml"

        manifest_content = {
            "apiVersion": "consul.hashicorp.com/v1alpha1",
            "kind": "ServiceDefaults",
            "metadata": {
                "name": "cb-payment-gateway",
                "namespace": "gpi-retail-1",
                "labels": {
                    "component": "ncbs-banking-sit",
                    "deployment": "blue",
                },
            },
            "spec": {
                "protocol": "http",
                "meshGateway": {"mode": "local"},
                "mutualTLSMode": "strict",
            },
        }
        manifest_file.write_text(yaml.dump(manifest_content), encoding="utf-8")

        # Run Directory -> CUE sync
        engine = SyncEngine(str(WORKSPACE_ROOT))
        sync_res = engine.sync_dir_to_cue()
        assert sync_res["total_processed"] > 0

        # Verify in RelationalGraph / CUE
        graph = RelationalGraph(cue_client)
        assert "SIT" in graph.environments
        sit_clusters = graph.environments["SIT"].get("clusters", {})
        assert "ocp52" in sit_clusters
        assert sit_clusters["ocp52"]["dc"] == "DCE"

        # Verify ServiceDefaults registered
        sd_key = "cb-payment-gateway-blue-sd"
        assert sd_key in graph.service_defaults
        sd_item = graph.service_defaults[sd_key]
        assert sd_item["service"] == "cb-payment-gateway"
        assert sd_item["cell"] == "retail"
        assert sd_item["apg"] == "ncbs"
        assert sd_item["region"] == "blue"

    def test_03_consistency_check_passes_when_clean(self, cue_client):
        """Verifies that check_consistency reports is_synced=True on a clean system."""
        engine = SyncEngine(str(WORKSPACE_ROOT))
        engine.sync_cue_to_dir(prune=True)

        report = engine.check_consistency()
        assert report["is_synced"] is True
        assert len(report["missing_in_dir"]) == 0
        assert len(report["missing_in_cue"]) == 0
        assert len(report["content_drift"]) == 0
        assert len(report["cross_dc_asymmetry"]) == 0

    def test_04_consistency_check_detects_drift(self, cue_client, clean_custom_and_dirs):
        """Verifies that modifying a file on disk without syncing to CUE triggers drift detection."""
        engine = SyncEngine(str(WORKSPACE_ROOT))
        engine.sync_cue_to_dir(prune=True)

        test_file = WORKSPACE_ROOT / "ApplicationGroups" / "NCBS" / "uat" / "retail" / "DCE" / "ocp53" / "servicedefaults" / "retail-order-service-blue.yaml"
        assert test_file.exists()

        # Modify protocol from http to grpc on disk
        data = yaml.safe_load(test_file.read_text(encoding="utf-8"))
        data["spec"]["protocol"] = "grpc"
        test_file.write_text(yaml.dump(data), encoding="utf-8")

        # Run check
        report = engine.check_consistency()
        assert report["is_synced"] is False
        assert len(report["content_drift"]) > 0
        assert any("retail-order-service-blue.yaml" in d["file"] for d in report["content_drift"])

    def test_05_consistency_check_detects_cross_dc_asymmetry(self, cue_client, clean_custom_and_dirs):
        """Verifies that asymmetry between paired DCE (ocp53) and DCW (ocp54) is flagged."""
        engine = SyncEngine(str(WORKSPACE_ROOT))
        engine.sync_cue_to_dir(prune=True)

        dcw_file = WORKSPACE_ROOT / "ApplicationGroups" / "NCBS" / "uat" / "retail" / "DCW" / "ocp54" / "httproutes" / "ncbs-retail-orders-route.yaml"
        assert dcw_file.exists()
        # Artificially remove DCW route to simulate asymmetry
        dcw_file.unlink()

        report = engine.check_consistency()
        assert report["is_synced"] is False
        assert len(report["cross_dc_asymmetry"]) > 0
        assert any("ncbs-retail-orders-route.yaml" in a["reason"] for a in report["cross_dc_asymmetry"])

