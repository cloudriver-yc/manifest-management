import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml

from .cue_client import CueClient, find_workspace_root
from .dimension_mgr import DimensionManager
from .generator import ManifestGenerator
from .graph import RelationalGraph


# Canonical APG folder names mapping
APG_DIR_MAP = {
    "ncbs": "NCBS",
    "branch-connect": "branch-connect",
}

# Reverse mapping
DIR_TO_APG_MAP = {
    "ncbs": "ncbs",
    "branch-connect": "branch-connect",
    "branchconnect": "branch-connect",
}

# Supported Config-Items folders and their canonical kinds
KIND_FOLDER_MAP = {
    "httproutes": "HTTPRoute",
    "httproute": "HTTPRoute",
    "gateway": "Gateway",
    "gateways": "Gateway",
    "servicedefaults": "ServiceDefaults",
    "service-defaults": "ServiceDefaults",
    "proxydefaults": "ProxyDefaults",
    "proxy-defaults": "ProxyDefaults",
    "referencegrant": "ReferenceGrant",
    "reference-grant": "ReferenceGrant",
    "meshservice": "MeshService",
    "mesh-service": "MeshService",
    "serviceresolver": "ServiceResolver",
    "service-resolver": "ServiceResolver",
    "networkpolicy": "NetworkPolicy",
    "network-policy": "NetworkPolicy",
}

REVERSE_KIND_FOLDER = {
    "HTTPRoute": "httproutes",
    "Gateway": "gateway",
    "ServiceDefaults": "servicedefaults",
    "ProxyDefaults": "proxydefaults",
    "ReferenceGrant": "referencegrant",
    "MeshService": "meshservice",
    "ServiceResolver": "serviceresolver",
    "NetworkPolicy": "networkpolicy",
}


class SyncEngine:
    """Bidirectional synchronization engine between CUE configurations and
    the hierarchical directory structure:
    <Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/<Config-Items>/
    """

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root) if workspace_root else find_workspace_root()
        self.app_groups_dir = self.workspace_root / "ApplicationGroups"
        self.cue_client = CueClient(str(self.workspace_root))
        self.graph = RelationalGraph(self.cue_client)
        self.dim_mgr = DimensionManager(str(self.workspace_root))
        self.generator = ManifestGenerator(str(self.workspace_root))

    def refresh(self):
        """Reloads graph and dimensions from CUE."""
        self.graph.refresh()

    def get_apg_dir_name(self, apg: str) -> str:
        return APG_DIR_MAP.get(apg.lower(), apg)

    def resolve_apg_from_dir(self, dir_name: str) -> str:
        return DIR_TO_APG_MAP.get(dir_name.lower(), dir_name.lower())

    # -------------------------------------------------------------------------
    # CUE -> Directory Synchronization
    # -------------------------------------------------------------------------
    def sync_cue_to_dir(
        self,
        env_filter: Optional[str] = None,
        prune: bool = False,
    ) -> Dict[str, Any]:
        """Exports the CUE state to the hierarchical directory tree."""
        self.refresh()
        created_or_updated: List[str] = []
        expected_paths: Set[Path] = set()

        environments = self.graph.environments
        apgs = self.graph.application_groups

        for env_name, env_data in environments.items():
            if env_filter and env_name.upper() != env_filter.upper():
                continue

            env_lower = env_name.lower()
            clusters = env_data.get("clusters", {})

            for cluster_name, cluster_data in clusters.items():
                cluster_lower = cluster_name.lower()
                dc = cluster_data.get("dc", "DCE").upper()

                # For each APG defined in the system
                for apg_name, apg_data in apgs.items():
                    apg_dir = self.get_apg_dir_name(apg_name)
                    cells = apg_data.get("cells", {})

                    for cell_name in cells.keys():
                        cell_lower = cell_name.lower()
                        base_cell_path = self.app_groups_dir / apg_dir / env_lower / cell_lower / dc / cluster_lower

                        # 1. Gateways
                        for gw_id, gw in self.graph.gateways.items():
                            gw_env = gw.get("env")
                            if gw_env and gw_env.upper() != env_name.upper():
                                continue
                            gw_cluster = gw.get("cluster")
                            if gw_cluster and gw_cluster.lower() != cluster_lower:
                                continue
                            if gw.get("apg", "").lower() == apg_name.lower() and gw.get("cell", "").lower() == cell_lower:
                                file_path = base_cell_path / "gateway" / f"{gw.get('name')}.yaml"
                                expected_paths.add(file_path.resolve())
                                content = self.generator._render_gateway(gw)
                                if self._write_if_changed(file_path, content):
                                    created_or_updated.append(str(file_path.relative_to(self.workspace_root)))

                        # 2. HTTPRoutes
                        for route_id, route in self.graph.http_routes.items():
                            r_env = route.get("env")
                            if r_env and r_env.upper() != env_name.upper():
                                continue
                            r_cluster = route.get("cluster")
                            if r_cluster and r_cluster.lower() != cluster_lower:
                                continue
                            if route.get("apg", "").lower() == apg_name.lower() and route.get("cell", "").lower() == cell_lower:
                                file_path = base_cell_path / "httproutes" / f"{route.get('name')}.yaml"
                                expected_paths.add(file_path.resolve())
                                content = self.generator._render_http_route(route)
                                if self._write_if_changed(file_path, content):
                                    created_or_updated.append(str(file_path.relative_to(self.workspace_root)))

                        # 3. ServiceDefaults
                        for sd_id, sd in self.graph.service_defaults.items():
                            sd_env = sd.get("env")
                            if sd_env and sd_env.upper() != env_name.upper():
                                continue
                            sd_cluster = sd.get("cluster")
                            if sd_cluster and sd_cluster.lower() != cluster_lower:
                                continue
                            if sd.get("apg", "").lower() == apg_name.lower() and sd.get("cell", "").lower() == cell_lower:
                                svc_name = sd.get("service")
                                region = sd.get("region", "")
                                filename = f"{svc_name}-{region}.yaml" if region else f"{svc_name}.yaml"
                                file_path = base_cell_path / "servicedefaults" / filename
                                expected_paths.add(file_path.resolve())
                                content = self.generator._render_service_defaults(sd)
                                if self._write_if_changed(file_path, content):
                                    created_or_updated.append(str(file_path.relative_to(self.workspace_root)))


                        # 4. ReferenceGrants
                        for rg_id, rg in self.graph.reference_grants.items():
                            rg_env = rg.get("env")
                            if rg_env and rg_env.upper() != env_name.upper():
                                continue
                            rg_cluster = rg.get("cluster")
                            if rg_cluster and rg_cluster.lower() != cluster_lower:
                                continue
                            if rg.get("apg", "").lower() == apg_name.lower() and rg.get("cell", "").lower() == cell_lower:
                                file_path = base_cell_path / "referencegrant" / f"{rg.get('name')}.yaml"
                                expected_paths.add(file_path.resolve())
                                content = self.generator._render_reference_grant(rg)
                                if self._write_if_changed(file_path, content):
                                    created_or_updated.append(str(file_path.relative_to(self.workspace_root)))

                        # 5. ProxyDefaults (Cluster-global singleton)
                        pd_res = self.graph.get_proxy_defaults(env=env_name, cluster=cluster_name)
                        if pd_res.get("proxy_defaults"):
                            pd = pd_res["proxy_defaults"]
                            file_path = base_cell_path / "proxydefaults" / f"{pd.get('name', 'global')}.yaml"
                            expected_paths.add(file_path.resolve())
                            content = self.generator._render_proxy_defaults(pd)
                            if self._write_if_changed(file_path, content):
                                created_or_updated.append(str(file_path.relative_to(self.workspace_root)))

        pruned: List[str] = []
        if prune:
            for existing_file in self._discover_all_hierarchy_files():
                if existing_file.resolve() not in expected_paths:
                    existing_file.unlink()
                    pruned.append(str(existing_file.relative_to(self.workspace_root)))

        return {
            "created_or_updated": created_or_updated,
            "total_updated": len(created_or_updated),
            "pruned": pruned,
            "total_pruned": len(pruned),
        }

    # -------------------------------------------------------------------------
    # Directory -> CUE Synchronization
    # -------------------------------------------------------------------------
    def sync_dir_to_cue(self) -> Dict[str, Any]:
        """Ingests all files found in the directory hierarchy into CUE."""
        self.refresh()
        files = self._discover_all_hierarchy_files()
        processed: List[Dict[str, Any]] = []

        for fpath in files:
            dim = self.parse_path_to_dimensions(fpath)
            if not dim:
                continue

            try:
                raw_yaml = fpath.read_text(encoding="utf-8")
                docs = list(yaml.safe_load_all(raw_yaml))
            except Exception as e:
                print(f"[!] Warning: Failed to parse YAML file {fpath}: {e}")
                continue

            for doc in docs:
                if not doc or not isinstance(doc, dict):
                    continue
                res = self._ingest_manifest_doc(doc, dim, fpath)
                if res:
                    processed.append(res)

        # Validate unified CUE catalog
        ok, err = self.cue_client.vet()
        if not ok:
            raise RuntimeError(f"CUE validation failed after ingesting directory files:\n{err}")

        self.refresh()
        return {
            "processed": processed,
            "total_processed": len(processed),
        }

    def _ingest_manifest_doc(self, doc: Dict[str, Any], dim: Dict[str, str], fpath: Path) -> Optional[Dict[str, Any]]:
        """Processes and registers a single manifest document into CUE."""
        kind = doc.get("kind") or dim.get("kind")
        metadata = doc.get("metadata", {})
        spec = doc.get("spec", {})
        name = metadata.get("name") or fpath.stem
        labels = metadata.get("labels", {})
        namespace = metadata.get("namespace", "")

        apg = dim["apg"]
        env = dim["env"]
        cell = dim["cell"]
        dc = dim["dc"]
        cluster = dim["cluster"]

        # Infer region from labels, namespace suffix, or filename
        region = labels.get("deployment") or labels.get("region")
        if not region:
            if namespace.endswith("-1") or "-blue" in name or "-blue" in fpath.stem:
                region = "blue"
            elif namespace.endswith("-2") or "-green" in name or "-green" in fpath.stem:
                region = "green"
            else:
                region = "blue"

        # Ensure environment and cluster are registered
        if env not in self.graph.environments:
            self.dim_mgr.add_environment(env)
            self.refresh()

        env_clusters = self.graph.environments.get(env, {}).get("clusters", {})
        if cluster not in env_clusters:
            self.dim_mgr.add_cluster(env=env, cluster=cluster, dc=dc)
            self.refresh()

        # Ensure APG and cell are registered
        if apg not in self.graph.application_groups:
            self.dim_mgr.add_application_group(apg)
            self.refresh()

        apg_cells = self.graph.application_groups.get(apg, {}).get("cells", {})
        if cell not in apg_cells:
            self.dim_mgr.add_cell(apg=apg, cell=cell)
            self.refresh()

        # Route by Kind
        if kind == "ServiceDefaults":
            svc_name = name or spec.get("service")
            sd_key = f"{svc_name}-{region}-sd"
            if sd_key in self.graph.service_defaults:
                existing_sd = self.graph.service_defaults[sd_key]
                if (existing_sd.get("protocol") == spec.get("protocol", "http")
                    and existing_sd.get("cell") == cell
                    and existing_sd.get("apg") == apg):
                    return None

            protocol = spec.get("protocol", "http")
            mgw_mode = spec.get("meshGateway", {}).get("mode", "none")
            self.dim_mgr.add_service_defaults(
                service=svc_name,
                namespace=namespace or f"{apg}-{cell}-1",
                apg=apg,
                cell=cell,
                region=region,
                protocol=protocol,
                mesh_gateway_mode=mgw_mode,
            )
            return {"kind": kind, "name": svc_name, "apg": apg, "env": env, "cell": cell}

        elif kind == "HTTPRoute":
            if name in self.graph.http_routes:
                existing_r = self.graph.http_routes[name]
                if existing_r.get("apg") == apg and existing_r.get("cell") == cell:
                    return None

            parent_agw = ""
            for p in spec.get("parentRefs", []):
                parent_agw = p.get("name")
                break
            if not parent_agw:
                parent_agw = f"agw-{apg}-{cell}-{region}"

            target_svc = ""
            path = "/"
            port = 8080
            for r in spec.get("rules", []):
                for m in r.get("matches", []):
                    path = m.get("path", {}).get("value", path)
                for b in r.get("backendRefs", []):
                    target_svc = b.get("name", "")
                    port = b.get("port", port)
                    break
                break

            if not target_svc:
                target_svc = f"{name}-svc"

            self.dim_mgr.add_route(
                name=name,
                namespace=namespace or f"{apg}-{cell}-1",
                apg=apg,
                cell=cell,
                region=region,
                parent_agw=parent_agw,
                path=path,
                target_service=target_svc,
                target_port=port,
            )
            return {"kind": kind, "name": name, "apg": apg, "env": env, "cell": cell}

        elif kind == "Gateway":
            if name in self.graph.gateways:
                existing_gw = self.graph.gateways[name]
                if existing_gw.get("apg") == apg and existing_gw.get("cell") == cell:
                    return None

            port = 8080
            for l in spec.get("listeners", []):
                port = l.get("port", port)
                break
            self.dim_mgr.add_gateway(
                name=name,
                apg=apg,
                cell=cell,
                region=region,
                namespace=namespace or f"{apg}-{cell}-1",
                port=port,
            )
            return {"kind": kind, "name": name, "apg": apg, "env": env, "cell": cell}

        elif kind == "ReferenceGrant":
            if name in self.graph.reference_grants:
                existing_rg = self.graph.reference_grants[name]
                if existing_rg.get("apg") == apg and existing_rg.get("cell") == cell:
                    return None

            from_list = spec.get("from", [])
            to_list = spec.get("to", [])
            self.dim_mgr.add_reference_grant(
                name=name,
                namespace=namespace or f"{apg}-{cell}-1",
                apg=apg,
                cell=cell,
                region=region,
                env=env,
                from_list=from_list,
                to_list=to_list,
            )
            return {"kind": kind, "name": name, "apg": apg, "env": env, "cell": cell}

        elif kind == "ProxyDefaults":
            pd_res = self.graph.get_proxy_defaults(env=env, cluster=cluster)
            if pd_res.get("proxy_defaults") and pd_res["match_level"] == "cluster_global":
                return None

            cfg = spec.get("config", {})
            self.dim_mgr.add_proxy_defaults(
                cluster=cluster,
                env=env,
                config=cfg,
                apg=apg,
            )
            return {"kind": kind, "name": name, "cluster": cluster, "env": env}


        elif kind == "ServiceResolver":
            subsets = spec.get("subsets", {})
            def_subset = spec.get("defaultSubset")
            self.dim_mgr.add_service_resolver(
                name=name,
                namespace=namespace or f"{apg}-{cell}-1",
                apg=apg,
                cell=cell,
                region=region,
                default_subset=def_subset,
            )
            return {"kind": kind, "name": name, "apg": apg, "env": env, "cell": cell}

        elif kind == "MeshService":
            port = spec.get("port", 8080)
            self.dim_mgr.add_mesh_service(
                name=name,
                namespace=namespace or f"{apg}-{cell}-1",
                apg=apg,
                cell=cell,
                region=region,
                port=port,
            )
            return {"kind": kind, "name": name, "apg": apg, "env": env, "cell": cell}

        elif kind == "NetworkPolicy":
            self.dim_mgr.add_network_policy(
                name=name,
                namespace=namespace or f"{apg}-{cell}-1",
                apg=apg,
                cell=cell,
                region=region,
            )
            return {"kind": kind, "name": name, "apg": apg, "env": env, "cell": cell}

        return None

    # -------------------------------------------------------------------------
    # Consistency & Divergence Checking
    # -------------------------------------------------------------------------
    def check_consistency(self) -> Dict[str, Any]:
        """Performs a comprehensive bidirectional audit between CUE and disk."""
        self.refresh()
        ok_vet, vet_err = self.cue_client.vet()
        schema_errors = []
        if not ok_vet:
            schema_errors.append(vet_err)

        dir_files = self._discover_all_hierarchy_files()
        dir_file_set = {f.resolve(): f for f in dir_files}

        expected_file_map: Dict[Path, str] = {}  # Path -> expected rendered content
        environments = self.graph.environments
        apgs = self.graph.application_groups

        for env_name, env_data in environments.items():
            env_lower = env_name.lower()
            clusters = env_data.get("clusters", {})
            for cluster_name, cluster_data in clusters.items():
                cluster_lower = cluster_name.lower()
                dc = cluster_data.get("dc", "DCE").upper()

                for apg_name, apg_data in apgs.items():
                    apg_dir = self.get_apg_dir_name(apg_name)
                    cells = apg_data.get("cells", {})

                    for cell_name in cells.keys():
                        cell_lower = cell_name.lower()
                        base = self.app_groups_dir / apg_dir / env_lower / cell_lower / dc / cluster_lower

                        # Gateways
                        for _, gw in self.graph.gateways.items():
                            gw_env = gw.get("env")
                            if gw_env and gw_env.upper() != env_name.upper():
                                continue
                            gw_cluster = gw.get("cluster")
                            if gw_cluster and gw_cluster.lower() != cluster_lower:
                                continue
                            if gw.get("apg", "").lower() == apg_name.lower() and gw.get("cell", "").lower() == cell_lower:
                                fp = (base / "gateway" / f"{gw.get('name')}.yaml").resolve()
                                expected_file_map[fp] = self.generator._render_gateway(gw)

                        # HTTPRoutes
                        for _, route in self.graph.http_routes.items():
                            r_env = route.get("env")
                            if r_env and r_env.upper() != env_name.upper():
                                continue
                            r_cluster = route.get("cluster")
                            if r_cluster and r_cluster.lower() != cluster_lower:
                                continue
                            if route.get("apg", "").lower() == apg_name.lower() and route.get("cell", "").lower() == cell_lower:
                                fp = (base / "httproutes" / f"{route.get('name')}.yaml").resolve()
                                expected_file_map[fp] = self.generator._render_http_route(route)

                        # ServiceDefaults
                        for _, sd in self.graph.service_defaults.items():
                            sd_env = sd.get("env")
                            if sd_env and sd_env.upper() != env_name.upper():
                                continue
                            sd_cluster = sd.get("cluster")
                            if sd_cluster and sd_cluster.lower() != cluster_lower:
                                continue
                            if sd.get("apg", "").lower() == apg_name.lower() and sd.get("cell", "").lower() == cell_lower:
                                svc = sd.get("service")
                                reg = sd.get("region", "")
                                fn = f"{svc}-{reg}.yaml" if reg else f"{svc}.yaml"
                                fp = (base / "servicedefaults" / fn).resolve()
                                expected_file_map[fp] = self.generator._render_service_defaults(sd)


                        # ReferenceGrants
                        for _, rg in self.graph.reference_grants.items():
                            rg_env = rg.get("env")
                            if rg_env and rg_env.upper() != env_name.upper():
                                continue
                            rg_cluster = rg.get("cluster")
                            if rg_cluster and rg_cluster.lower() != cluster_lower:
                                continue
                            if rg.get("apg", "").lower() == apg_name.lower() and rg.get("cell", "").lower() == cell_lower:
                                fp = (base / "referencegrant" / f"{rg.get('name')}.yaml").resolve()
                                expected_file_map[fp] = self.generator._render_reference_grant(rg)

                        # ProxyDefaults
                        pd_res = self.graph.get_proxy_defaults(env=env_name, cluster=cluster_name)
                        if pd_res.get("proxy_defaults"):
                            pd = pd_res["proxy_defaults"]
                            fp = (base / "proxydefaults" / f"{pd.get('name', 'global')}.yaml").resolve()
                            expected_file_map[fp] = self.generator._render_proxy_defaults(pd)

        # 1. Missing in directory (Defined in CUE but absent on disk)
        missing_in_dir: List[str] = []
        for exp_path in expected_file_map.keys():
            if exp_path not in dir_file_set:
                missing_in_dir.append(str(exp_path.relative_to(self.workspace_root)))

        # 2. Missing in CUE / Orphaned files (Present on disk but not in expected CUE items)
        missing_in_cue: List[str] = []
        for disk_path in dir_file_set.keys():
            if disk_path not in expected_file_map:
                missing_in_cue.append(str(disk_path.relative_to(self.workspace_root)))

        # 3. Content drift
        content_drift: List[Dict[str, Any]] = []
        for path, expected_content in expected_file_map.items():
            if path in dir_file_set:
                actual_content = path.read_text(encoding="utf-8")
                try:
                    exp_yaml = yaml.safe_load(expected_content)
                    act_yaml = yaml.safe_load(actual_content)
                    if exp_yaml != act_yaml:
                        content_drift.append({
                            "file": str(path.relative_to(self.workspace_root)),
                            "status": "spec_mismatch",
                        })
                except Exception as e:
                    content_drift.append({
                        "file": str(path.relative_to(self.workspace_root)),
                        "error": str(e),
                    })

        # 4. Cross-DC Symmetry verification
        cross_dc_asymmetry: List[Dict[str, Any]] = []
        for env_name, env_data in environments.items():
            if not env_data.get("peering_enabled"):
                continue
            clusters = env_data.get("clusters", {})
            dce_clusters = [c for c, cd in clusters.items() if cd.get("dc", "DCE").upper() == "DCE"]
            dcw_clusters = [c for c, cd in clusters.items() if cd.get("dc", "DCW").upper() == "DCW"]

            for dce_c in dce_clusters:
                for dcw_c in dcw_clusters:
                    for apg_name in apgs.keys():
                        apg_dir = self.get_apg_dir_name(apg_name)
                        dce_root = self.app_groups_dir / apg_dir / env_name.lower()
                        dce_files = list(dce_root.glob(f"*/DCE/{dce_c.lower()}/*/*.yaml"))
                        for dce_f in dce_files:
                            rel_subpath = dce_f.relative_to(self.app_groups_dir / apg_dir / env_name.lower())
                            parts = list(rel_subpath.parts)
                            if len(parts) == 5 and parts[1] == "DCE":
                                kind_folder = parts[3]
                                if kind_folder == "proxydefaults":
                                    # ProxyDefaults is cluster-scoped singleton (per-cluster log formats/labels)
                                    continue

                                # Check if resource is explicitly cluster-scoped in CUE
                                r_name = dce_f.stem
                                is_cluster_scoped = False
                                for r in self.graph.http_routes.values():
                                    if r.get("name") == r_name and r.get("cluster"):
                                        is_cluster_scoped = True
                                        break
                                for g in self.graph.gateways.values():
                                    if g.get("name") == r_name and g.get("cluster"):
                                        is_cluster_scoped = True
                                        break
                                for s in self.graph.service_defaults.values():
                                    if f"{s.get('service')}-{s.get('region', '')}" == r_name and s.get("cluster"):
                                        is_cluster_scoped = True
                                        break
                                for rg in self.graph.reference_grants.values():
                                    if rg.get("name") == r_name and rg.get("cluster"):
                                        is_cluster_scoped = True
                                        break
                                if is_cluster_scoped:
                                    continue

                                dcw_eq = self.app_groups_dir / apg_dir / env_name.lower() / parts[0] / "DCW" / dcw_c.lower() / parts[3] / parts[4]


                                if not dcw_eq.exists():
                                    cross_dc_asymmetry.append({
                                        "env": env_name,
                                        "reason": f"Missing symmetric manifest in DCW: {dcw_eq.name}",
                                        "dce_file": str(dce_f.relative_to(self.workspace_root)),
                                        "dcw_file": str(dcw_eq.relative_to(self.workspace_root)),
                                    })
                                else:
                                    try:
                                        dce_y = yaml.safe_load(dce_f.read_text(encoding="utf-8"))
                                        dcw_y = yaml.safe_load(dcw_eq.read_text(encoding="utf-8"))
                                        if dce_y.get("spec") != dcw_y.get("spec"):
                                            cross_dc_asymmetry.append({
                                                "env": env_name,
                                                "reason": f"Content mismatch between DCE and DCW manifests: {dce_f.name}",
                                                "dce_file": str(dce_f.relative_to(self.workspace_root)),
                                                "dcw_file": str(dcw_eq.relative_to(self.workspace_root)),
                                            })
                                    except Exception:
                                        pass

        is_synced = (
            len(missing_in_dir) == 0
            and len(missing_in_cue) == 0
            and len(content_drift) == 0
            and len(cross_dc_asymmetry) == 0
            and len(schema_errors) == 0
        )

        return {
            "is_synced": is_synced,
            "schema_errors": schema_errors,
            "missing_in_dir": missing_in_dir,
            "missing_in_cue": missing_in_cue,
            "content_drift": content_drift,
            "cross_dc_asymmetry": cross_dc_asymmetry,
            "stats": {
                "total_expected_manifests": len(expected_file_map),
                "total_disk_manifests": len(dir_files),
            },
        }

    # -------------------------------------------------------------------------
    # Helper Utilities
    # -------------------------------------------------------------------------
    def parse_path_to_dimensions(self, file_path: Path) -> Optional[Dict[str, str]]:
        """Extracts hierarchy dimensions from a path.
        Format: ApplicationGroups/<Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/<Config-Items>/<name>.yaml
        Also supports direct <Application>/<Environment>/... paths for backwards compatibility.
        """
        try:
            rel = file_path.resolve().relative_to(self.workspace_root.resolve())
        except ValueError:
            return None

        parts = rel.parts
        if len(parts) >= 8 and parts[0].lower() in ["applicationgroups", "application_groups"]:
            parts = parts[1:]
        elif len(parts) < 7:
            return None

        app_dir = parts[0]
        env_dir = parts[1]
        cell_dir = parts[2]
        dc_dir = parts[3]
        cluster_dir = parts[4]
        kind_dir = parts[5]
        filename = parts[6]

        apg = self.resolve_apg_from_dir(app_dir)
        env = env_dir.upper()
        cell = cell_dir.lower()
        dc = dc_dir.upper()
        cluster = cluster_dir.lower()
        kind = KIND_FOLDER_MAP.get(kind_dir.lower(), kind_dir)

        return {
            "apg": apg,
            "env": env,
            "cell": cell,
            "dc": dc,
            "cluster": cluster,
            "kind": kind,
            "filename": filename,
        }

    def _discover_all_hierarchy_files(self) -> List[Path]:
        """Finds all YAML manifests inside ApplicationGroups directory."""
        discovered: List[Path] = []
        scan_roots = []
        if self.app_groups_dir.exists():
            scan_roots.append(self.app_groups_dir)
        else:
            scan_roots.append(self.workspace_root)

        for sroot in scan_roots:
            for yaml_file in sroot.glob("**/*.yaml"):
                if self.parse_path_to_dimensions(yaml_file):
                    discovered.append(yaml_file)
            for yml_file in sroot.glob("**/*.yml"):
                if self.parse_path_to_dimensions(yml_file):
                    discovered.append(yml_file)

        return sorted(discovered)

    def _write_if_changed(self, file_path: Path, new_content: str) -> bool:
        """Writes content to file only if it is newly created or changed."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.exists():
            existing = file_path.read_text(encoding="utf-8")
            if existing == new_content:
                return False
        file_path.write_text(new_content, encoding="utf-8")
        return True
