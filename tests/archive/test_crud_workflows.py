import os
import shutil
import sys
import tempfile
from pathlib import Path
import pytest
import subprocess
import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS_DIR = WORKSPACE_ROOT / ".agents" / "skills" / "manifest-management" / "scripts"
if str(SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS_DIR))

from py_engine.cue_client import CueClient
from py_engine.dimension_mgr import DimensionManager
from py_engine.generator import ManifestGenerator
from py_engine.graph import RelationalGraph
from py_engine.manifest_parser import ManifestParser


@pytest.fixture(scope="module")
def cue_client():
    client = CueClient(str(WORKSPACE_ROOT))
    ok, err = client.vet()
    assert ok, f"Initial CUE validation failed: {err}"
    return client


@pytest.fixture(scope="module", autouse=True)
def preserve_custom_extensions():
    custom_file = WORKSPACE_ROOT / "cue" / "catalog" / "extensions" / "custom.cue"
    original_content = custom_file.read_text(encoding="utf-8") if custom_file.exists() else ""
    yield
    if original_content:
        custom_file.write_text(original_content, encoding="utf-8")



@pytest.fixture(scope="module")
def graph(cue_client):
    return RelationalGraph(cue_client)


class TestSkillCRUDWorkflows:
    """Validates the full CRUD lifecycle and the user's three challenge queries."""

    def test_01_read_challenge_1_reverse_path_lookup(self, graph):
        """Challenge 1: Find which AGW and HTTPRoute accommodates a url-path."""
        matches = graph.find_routes_for_path("/v1/retail/orders/")
        assert len(matches) > 0

        first_match = matches[0]
        assert first_match["route_name"] == "ncbs-retail-orders-route"
        assert first_match["parent_agw"] == "agw-ncbs-retail-blue"
        assert first_match["route_namespace"] == "gpi-retail-1"
        assert first_match["apg"] == "ncbs"
        assert first_match["cell"] == "retail"
        assert first_match["region"] == "blue"
        assert first_match["backend_services"][0]["service"] == "retail-order-service"

    def test_02_read_challenge_2_proxy_defaults(self, graph):
        """Challenge 2: Query proxyDefaults for Green cell in UAT OCP53.
        Verifies that ProxyDefaults is cluster-global (1 per Consul cluster).
        """
        res = graph.get_proxy_defaults(
            env="UAT",
            cluster="ocp53",
            cell="retail",
            region="green",
        )
        assert res["match_level"] == "cluster_global"
        assert res["scope_note"] is not None
        pd = res["proxy_defaults"]
        assert pd is not None
        assert pd["name"] == "global"
        assert pd["env"] == "UAT"
        assert pd["cluster"] == "ocp53"
        assert pd["apg"] == "ncbs"
        assert pd["config"]["access_logs"]["format"] == "json-uat-ocp53"
        assert pd["config"]["tracing"]["enabled"] is True

    def test_03_read_challenge_3_agw_inventory(self, graph):
        """Challenge 3: Count httproutes and accommodated services for an AGW."""
        inv = graph.get_agw_inventory("agw-ncbs-retail-blue")
        assert inv is not None
        assert inv["agw_name"] == "agw-ncbs-retail-blue"
        assert inv["apg"] == "ncbs"
        assert inv["cell"] == "retail"
        assert inv["region"] == "blue"
        assert inv["bonded_route_count"] >= 2  # orders and payment routes
        assert inv["accommodated_service_count"] >= 1
        assert any("retail-order-service" in s for s in inv["accommodated_services"])

    def test_04_create_dynamic_dimensions(self, cue_client):
        """CREATE: Dynamically extend dimensions (Env, APG, Cell, Namespace, Service)."""
        dim_mgr = DimensionManager(str(WORKSPACE_ROOT))

        # 1. Add Environment
        env_res = dim_mgr.add_environment("STG", peering_enabled=True)
        assert env_res["environment"] == "STG"

        # 2. Add APG
        apg_res = dim_mgr.add_application_group("wealth-mgmt")
        assert apg_res["application_group"] == "wealth-mgmt"

        # 3. Add Cell
        cell_res = dim_mgr.add_cell(apg="wealth-mgmt", cell="portfolio", description="Portfolio Cell")
        assert cell_res["cell"] == "portfolio"

        # 4. Add Namespace with -1 suffix -> blue region inferred
        ns_res = dim_mgr.add_namespace("portfolio-core-1", apg="wealth-mgmt", cell="portfolio")
        assert ns_res["region"] == "blue"

        # 5. Add Service
        svc_res = dim_mgr.add_service(
            name="portfolio-calc",
            namespace="portfolio-core-1",
            apg="wealth-mgmt",
            cell="portfolio",
            region="blue",
            version="v1.0.0",
            port=8080,
        )
        assert svc_res["service"] == "portfolio-calc"

        # Refresh graph and verify newly created dimensions exist
        graph = RelationalGraph(cue_client)
        assert "STG" in graph.environments
        assert "wealth-mgmt" in graph.application_groups
        assert "portfolio-core-1" in graph.namespaces
        assert "portfolio-calc-blue" in graph.services

    def test_05_create_ingest_service_defaults_manifest(self, cue_client):
        """CREATE: Ingest ServiceDefaults.yaml and verify automatic AGW and Route linkage."""
        parser = ManifestParser(str(WORKSPACE_ROOT))
        example_file = WORKSPACE_ROOT / "examples" / "ServiceDefaults_example.yaml"

        res = parser.parse_manifest_file(str(example_file))
        assert len(res["processed"]) == 1
        item = res["processed"][0]

        assert item["kind"] == "ServiceDefaults"
        assert item["service"] == "cb-payment-service"
        assert item["namespace"] == "cbcoresg-com-1"
        assert item["region"] == "blue"
        assert item["linked_agw"] == "agw-ncbs-common-blue"
        assert item["linked_path"] == "/v1/common/payment/"
        assert item["route_created"] is True

        # Verify through query
        graph = RelationalGraph(cue_client)
        matches = graph.find_routes_for_path("/v1/common/payment/")
        assert len(matches) > 0
        assert matches[0]["parent_agw"] == "agw-ncbs-common-blue"
        assert matches[0]["backend_services"][0]["service"] == "cb-payment-service"

    def test_06_create_ingest_http_route_manifest(self, cue_client):
        """CREATE: Ingest HTTPRoute.yaml for Green canary service."""
        parser = ManifestParser(str(WORKSPACE_ROOT))
        example_file = WORKSPACE_ROOT / "examples" / "HTTPRoute_example.yaml"

        res = parser.parse_manifest_file(str(example_file))
        assert len(res["processed"]) == 1
        item = res["processed"][0]
        assert item["kind"] == "HTTPRoute"
        assert item["name"] == "ncbs-loyalty-route"

        # Verify reverse path query finds it
        graph = RelationalGraph(cue_client)
        matches = graph.find_routes_for_path("/v1/retail/loyalty/")
        assert len(matches) > 0
        assert matches[0]["parent_agw"] == "agw-ncbs-retail-green"
        assert matches[0]["region"] == "green"

    def test_07_update_and_validate(self, cue_client):
        """UPDATE: Re-linking route path and verifying CUE unification."""
        dim_mgr = DimensionManager(str(WORKSPACE_ROOT))
        # Add updated route rule
        dim_mgr.add_route(
            name="ncbs-loyalty-route-v2",
            namespace="cb-core-ss-retail-2",
            apg="ncbs",
            cell="retail",
            region="green",
            parent_agw="agw-ncbs-retail-green",
            path="/v2/retail/loyalty/",
            target_service="retail-loyalty-canary",
        )
        ok, err = cue_client.vet()
        assert ok, f"CUE vet failed after update: {err}"

        graph = RelationalGraph(cue_client)
        matches = graph.find_routes_for_path("/v2/retail/loyalty/")
        assert len(matches) > 0
        assert matches[0]["route_name"] == "ncbs-loyalty-route-v2"

    def test_08_delete_and_cleanup(self, cue_client):
        """DELETE: Decommissioning an extension entry."""
        dim_mgr = DimensionManager(str(WORKSPACE_ROOT))
        deleted = dim_mgr.delete_item("services", "portfolio-calc-blue")
        assert deleted is True

        graph = RelationalGraph(cue_client)
        assert "portfolio-calc-blue" not in graph.services

    def test_09_export_and_cross_dc_symmetry(self):
        """EXPORT: Verify cross-DC symmetry between DCE (ocp53) and DCW (ocp54) in UAT."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ManifestGenerator(str(WORKSPACE_ROOT))
            res = gen.export_all(target_dir=tmpdir, env_filter="UAT")
            assert res["total_files"] > 0

            out_path = Path(tmpdir) / "UAT"
            dce_cluster = out_path / "ocp53"
            dcw_cluster = out_path / "ocp54"

            # Both clusters must exist
            assert dce_cluster.exists()
            assert dcw_cluster.exists()

            # Cross-DC Symmetry verification: Compare Blue retail order route
            dce_route = (dce_cluster / "ncbs" / "blue" / "httproute-ncbs-retail-orders-route.yaml").read_text()
            dcw_route = (dcw_cluster / "ncbs" / "blue" / "httproute-ncbs-retail-orders-route.yaml").read_text()
            assert dce_route == dcw_route, "Cross-DC symmetry failed: DCE and DCW routes differ!"

            # Compare Blue retail gateway
            dce_gw = (dce_cluster / "ncbs" / "blue" / "gateway-agw-ncbs-retail-blue.yaml").read_text()
            dcw_gw = (dcw_cluster / "ncbs" / "blue" / "gateway-agw-ncbs-retail-blue.yaml").read_text()
            assert dce_gw == dcw_gw, "Cross-DC symmetry failed: DCE and DCW gateways differ!"

    def test_10_query_reference_grant_by_region_and_cell(self, cue_client):
        """Remediation verification: Query ReferenceGrant filtered by region and cell."""
        graph = RelationalGraph(cue_client)
        assert len(graph.reference_grants) > 0

        # Verify ReferenceGrant in blue region
        blue_grants = [
            rg for rg in graph.reference_grants.values()
            if rg.get("region") == "blue" or rg.get("namespace", "").endswith("-1")
        ]
        assert len(blue_grants) >= 1
        grant = blue_grants[0]
        assert grant["name"] == "cbcoresg-com-1-grant-new"
        assert grant["namespace"] == "cbcoresg-com-1"
        assert grant["cell"] == "common"
        assert grant["region"] == "blue"
        assert grant["apg"] == "ncbs"

        # Verify CLI execution with --region blue and --cell blue
        runner = WORKSPACE_ROOT / ".agents" / "skills" / "manifest-management" / "scripts" / "manifest-mgr"
        cmd = [str(runner), "query", "grant", "--region", "blue"]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WORKSPACE_ROOT))
        assert res.returncode == 0
        assert "kind: ReferenceGrant" in res.stdout
        assert "cbcoresg-com-1-grant-new" in res.stdout

    def test_11_llm_dynamic_query_find_and_eval(self):
        """Verify dynamic LLM-driven query find and eval without CLI code modifications."""
        runner = WORKSPACE_ROOT / ".agents" / "skills" / "manifest-management" / "scripts" / "manifest-mgr"

        # 1. Dynamic find with arbitrary key=value filters
        cmd_find = [str(runner), "query", "find", "grant", "region=blue"]
        res_find = subprocess.run(cmd_find, capture_output=True, text=True, cwd=str(WORKSPACE_ROOT))
        assert res_find.returncode == 0
        assert "kind: ReferenceGrant" in res_find.stdout
        assert "cbcoresg-com-1-grant-new" in res_find.stdout

        # 2. Dynamic find routes by cell
        cmd_find_route = [str(runner), "query", "find", "route", "cell=retail"]
        res_route = subprocess.run(cmd_find_route, capture_output=True, text=True, cwd=str(WORKSPACE_ROOT))
        assert res_route.returncode == 0
        assert "ncbs-retail-orders-route" in res_route.stdout

        # 3. Dynamic eval with CUE expression
        cmd_eval = [str(runner), "query", "eval", "system.reference_grants"]
        res_eval = subprocess.run(cmd_eval, capture_output=True, text=True, cwd=str(WORKSPACE_ROOT))
        assert res_eval.returncode == 0
        assert "cbcoresg-com-1-grant-new" in res_eval.stdout

    def test_12_cluster_scoped_manifest_and_sync(self, cue_client):
        """Verify cluster-scoped manifest targeting specific cluster (e.g. ocp53) without broadcasting to ocp54."""
        dim_mgr = DimensionManager(str(WORKSPACE_ROOT))
        test_route_name = "test-cluster-canary-route"

        # Add cluster-scoped route to ocp53 only
        dim_mgr.add_route(
            name=test_route_name,
            namespace="gpi-retail-1",
            apg="ncbs",
            cell="retail",
            region="blue",
            parent_agw="agw-ncbs-retail-blue",
            path="/v1/canary/",
            target_service="canary-service",
            env="UAT",
            cluster="ocp53",
        )

        try:
            from py_engine.sync_engine import SyncEngine
            sync = SyncEngine(str(WORKSPACE_ROOT))
            sync_res = sync.sync_cue_to_dir()

            ocp53_file = WORKSPACE_ROOT / "ApplicationGroups" / "NCBS" / "uat" / "retail" / "DCE" / "ocp53" / "httproutes" / f"{test_route_name}.yaml"
            ocp54_file = WORKSPACE_ROOT / "ApplicationGroups" / "NCBS" / "uat" / "retail" / "DCW" / "ocp54" / "httproutes" / f"{test_route_name}.yaml"

            assert ocp53_file.exists(), "Targeted cluster ocp53 must have the route manifest"
            assert not ocp54_file.exists(), "Untargeted cluster ocp54 must NOT have the route manifest"

            # Consistency check should pass without treating cluster-scoped manifest as cross-DC asymmetry
            audit = sync.check_consistency()
            assert audit["is_synced"] is True, f"Consistency check failed: {audit}"
        finally:
            dim_mgr.delete_item("http_routes", test_route_name)
            if ocp53_file.exists():
                ocp53_file.unlink()
            SyncEngine(str(WORKSPACE_ROOT)).refresh()

    def test_13_query_routes_by_path_and_env(self):
        """Verify dynamic query find route by path and env/cluster."""
        runner = WORKSPACE_ROOT / ".agents" / "skills" / "manifest-management" / "scripts" / "manifest-mgr"

        # 1. Query path and env=prod (should return base route + prod-scoped route)
        cmd = [str(runner), "query", "find", "route", "path=/v1/retail/orders/", "env=prod"]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WORKSPACE_ROOT))
        assert res.returncode == 0
        assert "ncbs-retail-orders-route" in res.stdout
        assert "ncbs-retail-orders-route-xxxx" in res.stdout

        # 2. Query path and env=prod cluster=ocp71 (should return base route only)
        cmd_71 = [str(runner), "query", "find", "route", "path=/v1/retail/orders/", "env=prod", "cluster=ocp71"]
        res_71 = subprocess.run(cmd_71, capture_output=True, text=True, cwd=str(WORKSPACE_ROOT))
        assert res_71.returncode == 0
        assert "ncbs-retail-orders-route" in res_71.stdout
        assert "ncbs-retail-orders-route-xxxx" not in res_71.stdout

        # 3. Query path and env=prod cluster=ocp72 (should return base route + xxxx route)
        cmd_72 = [str(runner), "query", "find", "route", "path=/v1/retail/orders/", "env=prod", "cluster=ocp72"]
        res_72 = subprocess.run(cmd_72, capture_output=True, text=True, cwd=str(WORKSPACE_ROOT))
        assert res_72.returncode == 0
        assert "ncbs-retail-orders-route" in res_72.stdout
        assert "ncbs-retail-orders-route-xxxx" in res_72.stdout

