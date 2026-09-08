import os
from pathlib import Path
import shutil
import sys
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS_DIR = WORKSPACE_ROOT / ".agents" / "skills" / "manifest-management" / "scripts"
if str(SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS_DIR))

from py_engine.markdown_db import MarkdownDB
from py_engine.dimension_mgr import DimensionManager
from py_engine.graph import RelationalGraph
from py_engine.sync_engine import SyncEngine


# Blank table definitions for clean reset
EMPTY_TABLES = {
    "environments.md": (
        "Environments & Clusters Topology",
        ["Environment", "Cluster", "Data Center", "Consul Cluster", "Peering Enabled", "Peering Target"],
    ),
    "application_groups.md": (
        "Application Groups & Logical Cells",
        ["Application Group", "Cell", "Description"],
    ),
    "namespaces.md": (
        "Namespaces & Blue/Green Topology",
        ["Namespace", "Application Group", "Cell", "Region", "Description"],
    ),
    "services.md": (
        "Services & Port Bindings",
        ["Service Name", "Namespace", "Application Group", "Cell", "Region", "Port", "Protocol", "Version"],
    ),
    "gateways.md": (
        "Application Gateways (AGW)",
        ["Gateway Name", "Namespace", "Application Group", "Cell", "Region", "Port", "Protocol", "Route Allowed From"],
    ),
    "http_routes.md": (
        "HTTPRoutes & Path Bindings",
        ["Route Name", "Namespace", "Application Group", "Cell", "Region", "Parent Gateway", "Path", "Match Type", "Target Service", "Target Port", "Weight", "Env Scope", "Cluster Scope"],
    ),
    "service_defaults.md": (
        "Consul ServiceDefaults",
        ["Service Name", "Namespace", "Application Group", "Cell", "Region", "Protocol", "Env Scope", "Cluster Scope", "Mutual TLS", "Upstream Connect Timeout"],
    ),
    "proxy_defaults.md": (
        "Consul Cluster-Global ProxyDefaults",
        ["Name", "Environment", "Cluster", "Application Group", "Access Log Format", "Tracing Enabled", "Protocol"],
    ),
    "reference_grants.md": (
        "Gateway API ReferenceGrants",
        ["Grant Name", "Namespace", "Application Group", "Cell", "Region", "From Group", "From Kind", "From Namespace", "To Group", "To Kind"],
    ),
}


def reset_to_clean_tables(db: MarkdownDB):
    """Resets all relations/*.md tables to empty headers and cleans ApplicationGroups/."""
    for filename, (title, headers) in EMPTY_TABLES.items():
        MarkdownDB.write_table(db.relations_dir / filename, title, headers, [])

    app_groups_dir = db.workspace_root / "ApplicationGroups"
    if app_groups_dir.exists():
        for item in app_groups_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()


class TestFrameworkIntegrity:
    """Verifies MarkdownDB validation, dynamic dimensional additions, queries, and GitOps sync."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        db = MarkdownDB(str(WORKSPACE_ROOT))
        reset_to_clean_tables(db)
        yield
        reset_to_clean_tables(db)

    def test_01_clean_state_and_vet(self):
        db = MarkdownDB(str(WORKSPACE_ROOT))
        ok, errs = db.vet()
        assert ok, f"Clean MarkdownDB validation failed: {errs}"

        graph = RelationalGraph(db)
        summary = graph.get_summary()
        assert len(summary["environments"]) == 0
        assert len(summary["application_groups"]) == 0
        assert summary["total_namespaces"] == 0
        assert summary["total_gateways"] == 0
        assert summary["total_http_routes"] == 0
        assert summary["total_services"] == 0

    def test_02_dynamic_add_dimensions_and_queries(self):
        db = MarkdownDB(str(WORKSPACE_ROOT))
        dim_mgr = DimensionManager(str(WORKSPACE_ROOT))

        # 1. Add Environment
        dim_mgr.add_environment("STG", peering_enabled=True)

        # 2. Add APG
        dim_mgr.add_application_group("wealth-mgmt")

        # 3. Add Cell
        dim_mgr.add_cell("wealth-mgmt", "portfolio", description="Portfolio Cell")

        # 4. Add Namespace
        dim_mgr.add_namespace("portfolio-core-1", apg="wealth-mgmt", cell="portfolio", region="blue")

        # 5. Add Service
        dim_mgr.add_service(
            name="portfolio-calc",
            namespace="portfolio-core-1",
            apg="wealth-mgmt",
            cell="portfolio",
            region="blue",
            version="v1.0.0",
            port=8080,
        )

        # 6. Add Gateway
        dim_mgr.add_gateway(
            name="agw-wealth-mgmt-portfolio-blue",
            apg="wealth-mgmt",
            cell="portfolio",
            region="blue",
            namespace="portfolio-core-1",
            port=443,
        )

        # 7. Add Route
        dim_mgr.add_route(
            name="portfolio-calc-route",
            namespace="portfolio-core-1",
            apg="wealth-mgmt",
            cell="portfolio",
            region="blue",
            parent_agw="agw-wealth-mgmt-portfolio-blue",
            path="/v1/portfolio/calc/",
            target_service="portfolio-calc",
            target_port=8080,
        )

        # 8. Add ProxyDefaults
        dim_mgr.add_proxy_defaults(cluster="ocp-stg", env="STG", apg="wealth-mgmt")

        # 9. Add ReferenceGrant
        dim_mgr.add_reference_grant(
            name="rg-portfolio-cross-ns",
            namespace="portfolio-core-1",
            apg="wealth-mgmt",
            cell="portfolio",
            region="blue",
        )

        # Verify Markdown validation succeeds with all entries
        ok, errs = db.vet()
        assert ok, f"Validation failed after adding dimensions: {errs}"

        # Verify Relational Graph Queries
        graph = RelationalGraph(db)

        # Query 1: Reverse path lookup
        routes = graph.find_routes_for_path("/v1/portfolio/calc/")
        assert len(routes) == 1
        assert routes[0]["route_name"] == "portfolio-calc-route"
        assert routes[0]["parent_agw"] == "agw-wealth-mgmt-portfolio-blue"
        assert routes[0]["apg"] == "wealth-mgmt"
        assert routes[0]["cell"] == "portfolio"
        assert routes[0]["region"] == "blue"

        # Query 2: AGW Inventory
        inv = graph.get_agw_inventory("agw-wealth-mgmt-portfolio-blue")
        assert inv is not None
        assert inv["bonded_route_count"] == 1
        assert inv["accommodated_service_count"] == 1
        assert any("portfolio-calc" in s for s in inv["accommodated_services"])

        # Query 3: ProxyDefaults
        pd_res = graph.get_proxy_defaults(env="STG", cluster="ocp-stg")
        assert pd_res["match_level"] == "cluster_global"
        assert pd_res["proxy_defaults"]["name"] == "global"

        # Query 4: ReferenceGrants
        grants = graph.reference_grants
        assert len(grants) == 1
        assert "rg-portfolio-cross-ns" in grants

    def test_03_sync_to_directory_and_consistency_audit(self):
        dim_mgr = DimensionManager(str(WORKSPACE_ROOT))
        sync = SyncEngine(str(WORKSPACE_ROOT))

        dim_mgr.add_environment("STG", peering_enabled=True)
        dim_mgr.add_application_group("wealth-mgmt")
        dim_mgr.add_cell("wealth-mgmt", "portfolio")
        dim_mgr.add_namespace("portfolio-core-1", apg="wealth-mgmt", cell="portfolio", region="blue")
        dim_mgr.add_service("portfolio-calc", "portfolio-core-1", apg="wealth-mgmt", cell="portfolio", region="blue", port=8080)
        dim_mgr.add_gateway(
            name="agw-wealth-mgmt-portfolio-blue",
            apg="wealth-mgmt",
            cell="portfolio",
            region="blue",
            namespace="portfolio-core-1",
            port=443,
        )
        dim_mgr.add_route(
            name="portfolio-calc-route",
            namespace="portfolio-core-1",
            apg="wealth-mgmt",
            cell="portfolio",
            region="blue",
            parent_agw="agw-wealth-mgmt-portfolio-blue",
            path="/v1/portfolio/calc/",
            target_service="portfolio-calc",
            target_port=8080,
        )

        # Sync to ApplicationGroups/
        sync_res = sync.sync_cue_to_dir()
        assert sync_res["total_updated"] > 0

        expected_route_file = (
            WORKSPACE_ROOT
            / "ApplicationGroups"
            / "wealth-mgmt"
            / "STG"
            / "portfolio"
            / "DCE"
            / "ocp-stg"
            / "httproutes"
            / "portfolio-calc-route.yaml"
        )
        assert expected_route_file.exists(), f"Expected manifest not created at {expected_route_file}"

        # Consistency audit
        audit = sync.check_consistency()
        assert audit["is_synced"] is True
        assert len(audit["missing_in_dir"]) == 0
        assert len(audit["content_drift"]) == 0
        assert len(audit["cross_dc_asymmetry"]) == 0

    def test_04_validation_catches_invalid_relations(self):
        dim_mgr = DimensionManager(str(WORKSPACE_ROOT))

        dim_mgr.add_environment("STG")
        dim_mgr.add_application_group("wealth-mgmt")
        dim_mgr.add_cell("wealth-mgmt", "portfolio")

        # Invalid namespace (does not end with -1 or -2) must be rejected
        with pytest.raises(RuntimeError) as exc_info:
            dim_mgr.add_namespace("invalid-ns", apg="wealth-mgmt", cell="portfolio", region="blue")
        assert "Blue namespace 'invalid-ns' must end with '-1'" in str(exc_info.value)
