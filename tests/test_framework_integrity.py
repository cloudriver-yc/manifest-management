import os
from pathlib import Path
import shutil
import sys
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS_DIR = WORKSPACE_ROOT / ".agents" / "skills" / "manifest-management" / "scripts"
if str(SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS_DIR))

from py_engine.cue_client import CueClient
from py_engine.dimension_mgr import DimensionManager
from py_engine.graph import RelationalGraph
from py_engine.sync_engine import SyncEngine


class TestFrameworkIntegrity:
    """Verifies schema validation, dynamic dimensional additions, and GitOps sync on the clean workspace."""

    def test_01_clean_state_and_vet(self):
        cue_client = CueClient(str(WORKSPACE_ROOT))
        ok, err = cue_client.vet()
        assert ok, f"Clean CUE validation failed: {err}"

        graph = RelationalGraph(cue_client)
        summary = graph.get_summary()
        assert summary["total_namespaces"] == 0
        assert summary["total_gateways"] == 0
        assert summary["total_http_routes"] == 0
        assert summary["total_services"] == 0

    def test_02_dynamic_add_dimensions_and_sync(self):
        dim_mgr = DimensionManager(str(WORKSPACE_ROOT))
        sync = SyncEngine(str(WORKSPACE_ROOT))

        # 1. Add Environment
        dim_mgr.add_environment("STG", peering_enabled=True)

        # 2. Add APG
        dim_mgr.add_application_group("wealth-mgmt")

        # 3. Add Cell
        dim_mgr.add_cell("wealth-mgmt", "portfolio")

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

        # 6. Add HTTPRoute
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

        # Verify CUE validation succeeds with new entries
        cue_client = CueClient(str(WORKSPACE_ROOT))
        ok, err = cue_client.vet()
        assert ok, f"Validation failed after adding dimensions: {err}"

        # Verify Sync to ApplicationGroups/
        sync_res = sync.sync_cue_to_dir()
        assert sync_res["total_updated"] > 0

        # Verify Consistency Audit passes
        audit = sync.check_consistency()
        assert audit["is_synced"] is True

        # Clean up test additions
        custom_file = WORKSPACE_ROOT / "cue" / "catalog" / "extensions" / "custom.cue"
        blank_custom = """package extensions

import (
\t"manifest.management/schema"
)

ext_environments: [string]: schema.#Environment
ext_environments: {}

ext_application_groups: [string]: schema.#ApplicationGroup
ext_application_groups: {}

ext_namespaces: [string]: schema.#Namespace
ext_namespaces: {}

ext_gateways: [string]: schema.#Gateway
ext_gateways: {}

ext_http_routes: [string]: schema.#HTTPRoute
ext_http_routes: {}

ext_services: [string]: schema.#Service
ext_services: {}

ext_service_defaults: [string]: schema.#ServiceDefaults
ext_service_defaults: {}

ext_proxy_defaults: [string]: schema.#ProxyDefaults
ext_proxy_defaults: {}

ext_reference_grants: [string]: schema.#ReferenceGrant
ext_reference_grants: {}

ext_service_resolvers: [string]: schema.#ServiceResolver
ext_service_resolvers: {}

ext_mesh_services: [string]: schema.#MeshService
ext_mesh_services: {}

ext_network_policies: [string]: schema.#NetworkPolicy
ext_network_policies: {}
"""
        custom_file.write_text(blank_custom, encoding="utf-8")

        # Prune generated directory
        app_groups_dir = WORKSPACE_ROOT / "ApplicationGroups"
        for item in app_groups_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        final_audit = sync.check_consistency()
        assert final_audit["is_synced"] is True
