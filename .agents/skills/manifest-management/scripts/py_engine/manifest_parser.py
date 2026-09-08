import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from .markdown_db import MarkdownDB, find_workspace_root
from .dimension_mgr import DimensionManager
from .graph import RelationalGraph


class ManifestParser:
    """Ingests raw YAML/JSON manifests and updates the Markdown configuration."""

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root) if workspace_root else find_workspace_root()
        self.db = MarkdownDB(str(self.workspace_root))
        self.graph = RelationalGraph(self.db)
        self.dim_mgr = DimensionManager(str(self.workspace_root))

    def parse_manifest_file(
        self,
        file_path: str,
        env: Optional[str] = None,
        cluster: Optional[str] = None,
        apg: Optional[str] = None,
        cell: Optional[str] = None,
        agw: Optional[str] = None,
        path: Optional[str] = None,
        port: int = 8080,
    ) -> Dict[str, Any]:
        """Parses a YAML/JSON manifest file, infers dimensions, and registers relations."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Manifest file not found: {file_path}")

        raw_content = p.read_text(encoding="utf-8")
        docs = list(yaml.safe_load_all(raw_content))
        results = []

        for doc in docs:
            if not doc or not isinstance(doc, dict):
                continue
            res = self.ingest_single_doc(
                doc,
                env=env,
                cluster=cluster,
                apg=apg,
                cell=cell,
                agw=agw,
                path=path,
                port=port,
            )
            results.append(res)

        return {"file": str(file_path), "processed": results}

    def ingest_single_doc(
        self,
        doc: Dict[str, Any],
        env: Optional[str] = None,
        cluster: Optional[str] = None,
        apg: Optional[str] = None,
        cell: Optional[str] = None,
        agw: Optional[str] = None,
        path: Optional[str] = None,
        port: int = 8080,
    ) -> Dict[str, Any]:
        kind = doc.get("kind", "")
        metadata = doc.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "default")
        labels = metadata.get("labels", {})
        annotations = metadata.get("annotations", {})
        agw_hint = agw or annotations.get("manifest.management/agw") or labels.get("agw")
        path_hint = path or annotations.get("manifest.management/path") or labels.get("path")
        port_hint = int(annotations.get("manifest.management/port", labels.get("port", port)))
        apg_hint = apg or annotations.get("manifest.management/apg") or labels.get("apg")
        cell_hint = cell or annotations.get("manifest.management/cell") or labels.get("cell")
        env_hint = env or annotations.get("manifest.management/env") or labels.get("environment") or labels.get("env")
        if env_hint:
            env_hint = env_hint.upper()
        cluster_hint = cluster or annotations.get("manifest.management/cluster") or labels.get("cluster")
        if cluster_hint:
            cluster_hint = cluster_hint.lower()


        # Infer region from namespace suffix: -1 -> blue, -2 -> green
        region = "blue"
        if namespace.endswith("-1"):
            region = "blue"
        elif namespace.endswith("-2"):
            region = "green"
        elif labels.get("deployment") in ["blue", "green"]:
            region = labels.get("deployment")

        # If APG is unknown, DO NOT GUESS: prompt user if interactive, otherwise raise error
        if not apg_hint:
            if sys.stdin and sys.stdin.isatty():
                try:
                    prompt_val = input(f"Unknown Application Group (APG) for manifest '{name}' (namespace: '{namespace}'). Enter APG (e.g. ncbs, branch-connect): ").strip()
                    if prompt_val:
                        apg_hint = prompt_val
                except (EOFError, KeyboardInterrupt):
                    pass

            if not apg_hint:
                raise ValueError(
                    f"Unknown Application Group (APG) for manifest '{name}' (namespace: '{namespace}'). "
                    f"Please specify --apg or provide the APG."
                )

        # If Cell is unknown, check known namespace or prompt user, DO NOT guess silently
        if not cell_hint:
            known_ns = self.graph.namespaces.get(namespace)
            if known_ns and known_ns.get("cell"):
                cell_hint = known_ns.get("cell")
            elif sys.stdin and sys.stdin.isatty():
                try:
                    prompt_val = input(f"Unknown Cell for namespace '{namespace}' (APG: '{apg_hint}'). Enter Cell (e.g. retail, common, paylah): ").strip()
                    if prompt_val:
                        cell_hint = prompt_val
                except (EOFError, KeyboardInterrupt):
                    pass

            if not cell_hint:
                raise ValueError(
                    f"Unknown Cell for manifest '{name}' (namespace: '{namespace}'). "
                    f"Please specify --cell or provide the Cell."
                )

        if kind == "ServiceDefaults":
            spec = doc.get("spec", {})
            protocol = spec.get("protocol", "http")
            mesh_gw_mode = spec.get("meshGateway", {}).get("mode", "none")

            # 1. Register namespace if not present
            if namespace not in self.graph.namespaces:
                self.dim_mgr.add_namespace(name=namespace, apg=apg_hint, cell=cell_hint, region=region)

            # 2. Register Service
            self.dim_mgr.add_service(
                name=name,
                namespace=namespace,
                apg=apg_hint,
                cell=cell_hint,
                region=region,
                port=port_hint,
                protocol=protocol,
            )

            # 3. Register ServiceDefaults
            sd_res = self.dim_mgr.add_service_defaults(
                service=name,
                namespace=namespace,
                apg=apg_hint,
                cell=cell_hint,
                region=region,
                protocol=protocol,
                mesh_gateway_mode=mesh_gw_mode,
                env=env_hint,
                cluster=cluster_hint,
            )

            # 4. If AGW and path are provided, automatically generate and link the HTTPRoute!
            route_res = None
            if agw_hint and path_hint:
                route_name = f"{name}-{region}-route"
                route_res = self.dim_mgr.add_route(
                    name=route_name,
                    namespace=namespace,
                    apg=apg_hint,
                    cell=cell_hint,
                    region=region,
                    parent_agw=agw_hint,
                    path=path_hint,
                    target_service=name,
                    target_port=port_hint,
                    env=env_hint,
                    cluster=cluster_hint,
                )

            # Refresh graph
            self.graph.refresh()

            return {
                "kind": "ServiceDefaults",
                "service": name,
                "namespace": namespace,
                "region": region,
                "env": env_hint,
                "cluster": cluster_hint,
                "apg": apg_hint,
                "cell": cell_hint,
                "protocol": protocol,
                "linked_agw": agw_hint,
                "linked_path": path_hint,
                "route_created": bool(route_res),
            }

        elif kind == "HTTPRoute":
            spec = doc.get("spec", {})
            parent_refs = spec.get("parentRefs", [])
            parent_agw = parent_refs[0].get("name") if parent_refs else (agw_hint or "agw-default")
            rules = spec.get("rules", [])

            # For each rule, add to CUE
            created_routes = []
            for idx, r in enumerate(rules):
                matches = r.get("matches", [])
                backends = r.get("backendRefs", [])
                for m in matches:
                    p_val = m.get("path", {}).get("value", "")
                    for b in backends:
                        b_svc = b.get("name")
                        b_port = b.get("port", 8080)
                        route_name = f"{name}-{idx}" if len(rules) > 1 else name
                        self.dim_mgr.add_route(
                            name=route_name,
                            namespace=namespace,
                            apg=apg_hint,
                            cell=cell_hint,
                            region=region,
                            parent_agw=parent_agw,
                            path=p_val,
                            target_service=b_svc,
                            target_port=b_port,
                            env=env_hint,
                            cluster=cluster_hint,
                        )
                        created_routes.append({
                            "route": route_name,
                            "path": p_val,
                            "service": b_svc,
                            "parent_agw": parent_agw,
                        })

            self.graph.refresh()
            return {
                "kind": "HTTPRoute",
                "name": name,
                "namespace": namespace,
                "parent_agw": parent_agw,
                "region": region,
                "env": env_hint,
                "cluster": cluster_hint,
                "cell": cell_hint,
                "apg": apg_hint,
                "routes": created_routes,
            }



        elif kind == "ReferenceGrant":
            labels = metadata.get("labels", {})
            env_hint = env or labels.get("environment")
            deployment = labels.get("deployment", region)
            if deployment in ["blue", "green"]:
                region = deployment

            spec = doc.get("spec", {})
            from_items = spec.get("from", [])
            if not isinstance(from_items, list):
                from_items = []
            if len(from_items) > 0 and isinstance(from_items[0], dict):
                first_from = from_items[0]
                if "kind" not in first_from and spec.get("kind"):
                    first_from["kind"] = spec.get("kind")
                if "namespace" not in first_from and spec.get("namespace"):
                    first_from["namespace"] = spec.get("namespace")
                if "group" not in first_from:
                    first_from["group"] = "gateway.networking.k8s.io"
                if "kind" not in first_from:
                    first_from["kind"] = "HTTPRoute"
                if "namespace" not in first_from:
                    first_from["namespace"] = namespace

            to_items = spec.get("to", [])
            if not isinstance(to_items, list) or len(to_items) == 0:
                to_items = [{"group": "", "kind": "Service"}]

            res = self.dim_mgr.add_reference_grant(
                name=name,
                namespace=namespace,
                apg=apg_hint,
                cell=cell_hint,
                region=region,
                env=env_hint,
                cluster=cluster_hint,
                from_list=from_items,
                to_list=to_items,
            )
            self.graph.refresh()
            return {
                "kind": "ReferenceGrant",
                "name": name,
                "namespace": namespace,
                "apg": apg_hint,
                "cell": cell_hint,
                "region": region,
                "env": env_hint,
                "cluster": cluster_hint,
                "from": from_items,
                "to": to_items,
            }

        else:
            return {"kind": kind, "status": "unsupported_kind"}
