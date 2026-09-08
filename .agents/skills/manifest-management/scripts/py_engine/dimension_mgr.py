import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from .markdown_db import MarkdownDB, find_workspace_root


class DimensionManager:
    """Manages dynamic CRUD for dimensions and manifest entries in relations/*.md."""

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root) if workspace_root else find_workspace_root()
        self.db = MarkdownDB(str(self.workspace_root))
        self.relations_dir = self.db.relations_dir

    def add_environment(
        self,
        name: str,
        clusters: Optional[Dict[str, Dict[str, Any]]] = None,
        peering_enabled: bool = False,
    ) -> Dict[str, Any]:
        """Adds a new environment dimension item to relations/environments.md."""
        env_name = name.upper()
        fp = self.relations_dir / "environments.md"
        headers = ["Environment", "Cluster", "Data Center", "Consul Cluster", "Peering Enabled", "Peering Target"]
        rows = self.db.parse_table(fp)

        # Remove existing rows for this environment
        rows = [r for r in rows if r.get("environment", "").upper() != env_name]

        if clusters:
            for cname, cdata in clusters.items():
                dc = cdata.get("dc", "DCE").upper()
                consul = cdata.get("consul_cluster", f"consul-{env_name.lower()}-{dc.lower()}")
                peering_target = cdata.get("peering_target_cluster", "-")
                rows.append({
                    "environment": env_name,
                    "cluster": cname.lower(),
                    "data_center": dc,
                    "consul_cluster": consul,
                    "peering_enabled": "true" if peering_enabled else "false",
                    "peering_target": peering_target,
                })
        else:
            default_cluster = f"ocp-{env_name.lower()}"
            rows.append({
                "environment": env_name,
                "cluster": default_cluster,
                "data_center": "DCE",
                "consul_cluster": f"consul-{env_name.lower()}-dce",
                "peering_enabled": "true" if peering_enabled else "false",
                "peering_target": "-",
            })

        self.db.write_table(fp, "Environments & Clusters Topology", headers, rows)
        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed to add environment {env_name}: {err}")
        return {"environment": env_name, "peering_enabled": peering_enabled}

    def add_cluster(
        self,
        env: str,
        cluster: str,
        dc: str = "DCE",
        consul_cluster: Optional[str] = None,
        peering_target: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds or updates a cluster in relations/environments.md."""
        env_upper = env.upper()
        cluster_lower = cluster.lower()
        dc_upper = dc.upper()
        consul = consul_cluster or f"consul-{env_upper.lower()}-{dc_upper.lower()}"

        fp = self.relations_dir / "environments.md"
        headers = ["Environment", "Cluster", "Data Center", "Consul Cluster", "Peering Enabled", "Peering Target"]
        rows = self.db.parse_table(fp)

        # Update if exists, or append
        found = False
        for r in rows:
            if r.get("environment", "").upper() == env_upper and r.get("cluster", "").lower() == cluster_lower:
                r["data_center"] = dc_upper
                r["consul_cluster"] = consul
                r["peering_target"] = peering_target or r.get("peering_target", "-")
                found = True
                break

        if not found:
            rows.append({
                "environment": env_upper,
                "cluster": cluster_lower,
                "data_center": dc_upper,
                "consul_cluster": consul,
                "peering_enabled": "false",
                "peering_target": peering_target or "-",
            })

        self.db.write_table(fp, "Environments & Clusters Topology", headers, rows)
        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed to add cluster {cluster_lower} to environment {env_upper}: {err}")
        return {"environment": env_upper, "cluster": cluster_lower, "dc": dc_upper}

    def add_application_group(self, name: str, description: str = "") -> Dict[str, Any]:
        """Adds a new Application Group (APG) to relations/application_groups.md."""
        apg_name = name.lower()
        fp = self.relations_dir / "application_groups.md"
        headers = ["Application Group", "Cell", "Description"]
        rows = self.db.parse_table(fp)

        # Check if already present
        exists = any(r.get("application_group", "").lower() == apg_name for r in rows)
        if not exists:
            rows.append({
                "application_group": apg_name,
                "cell": "-",
                "description": description or f"{apg_name.upper()} Application Group",
            })
            self.db.write_table(fp, "Application Groups & Logical Cells", headers, rows)

        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed to add APG {apg_name}: {err}")
        return {"application_group": apg_name}

    def add_cell(self, apg: str, cell: str, description: str = "") -> Dict[str, Any]:
        """Adds a Cell under an APG in relations/application_groups.md."""
        apg_name = apg.lower()
        cell_name = cell.lower()
        fp = self.relations_dir / "application_groups.md"
        headers = ["Application Group", "Cell", "Description"]
        rows = self.db.parse_table(fp)

        # If APG has a placeholder row with cell='-', update it
        updated = False
        for r in rows:
            if r.get("application_group", "").lower() == apg_name and r.get("cell", "") in ["-", ""]:
                r["cell"] = cell_name
                r["description"] = description or f"{cell_name.capitalize()} Cell"
                updated = True
                break
            elif r.get("application_group", "").lower() == apg_name and r.get("cell", "").lower() == cell_name:
                r["description"] = description or r.get("description", "")
                updated = True
                break

        if not updated:
            rows.append({
                "application_group": apg_name,
                "cell": cell_name,
                "description": description or f"{cell_name.capitalize()} Cell",
            })

        self.db.write_table(fp, "Application Groups & Logical Cells", headers, rows)
        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed to add Cell {cell_name} to APG {apg_name}: {err}")
        return {"apg": apg_name, "cell": cell_name}

    def add_namespace(self, name: str, apg: str, cell: str, region: Optional[str] = None) -> Dict[str, Any]:
        """Adds a namespace to relations/namespaces.md."""
        if not region:
            if name.endswith("-1"):
                region = "blue"
            elif name.endswith("-2"):
                region = "green"
            else:
                region = "blue"

        fp = self.relations_dir / "namespaces.md"
        headers = ["Namespace", "Application Group", "Cell", "Region"]
        rows = self.db.parse_table(fp)

        rows = [r for r in rows if r.get("namespace", "").lower() != name.lower()]
        rows.append({
            "namespace": name,
            "application_group": apg.lower(),
            "cell": cell.lower(),
            "region": region.lower(),
        })

        self.db.write_table(fp, "Namespaces & Regional Placement", headers, rows)
        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed to add namespace {name}: {err}")
        return {"namespace": name, "region": region, "cell": cell, "apg": apg}

    def add_service(
        self,
        name: str,
        namespace: str,
        apg: str,
        cell: str,
        region: str,
        version: str = "v1.0.0",
        port: int = 8080,
        protocol: str = "http",
    ) -> Dict[str, Any]:
        """Registers a service in relations/services.md."""
        fp = self.relations_dir / "services.md"
        headers = ["Service", "Namespace", "Application Group", "Cell", "Region", "Port", "Protocol", "Version"]
        rows = self.db.parse_table(fp)

        rows = [r for r in rows if not (r.get("service") == name and r.get("region") == region.lower())]
        rows.append({
            "service": name,
            "namespace": namespace,
            "application_group": apg.lower(),
            "cell": cell.lower(),
            "region": region.lower(),
            "port": str(port),
            "protocol": protocol.lower(),
            "version": version,
        })

        self.db.write_table(fp, "Services Catalog", headers, rows)
        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed to add service {name}: {err}")
        return {"service": name, "region": region, "version": version, "namespace": namespace}

    def add_gateway(
        self,
        name: str,
        apg: str,
        cell: str,
        region: str,
        namespace: str,
        port: int = 8080,
        protocol: str = "HTTP",
        env: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds an AGW in relations/gateways.md."""
        fp = self.relations_dir / "gateways.md"
        headers = ["Gateway Name", "Namespace", "Application Group", "Cell", "Region", "Port", "Protocol", "Route Allowed From"]
        rows = self.db.parse_table(fp)

        rows = [r for r in rows if r.get("gateway_name") != name]
        rows.append({
            "gateway_name": name,
            "namespace": namespace,
            "application_group": apg.lower(),
            "cell": cell.lower(),
            "region": region.lower(),
            "port": str(port),
            "protocol": protocol.upper(),
            "route_allowed_from": "Same",
        })

        self.db.write_table(fp, "Gateways (Consul API Gateways)", headers, rows)
        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed to add gateway {name}: {err}")
        return {"gateway": name, "namespace": namespace, "apg": apg, "cell": cell, "region": region}

    def add_route(
        self,
        name: str,
        namespace: str,
        apg: str,
        cell: str,
        region: str,
        parent_agw: str,
        path: str,
        target_service: str,
        target_port: int = 8080,
        weight: int = 100,
        env: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds an HTTPRoute in relations/http_routes.md."""
        fp = self.relations_dir / "http_routes.md"
        headers = ["Route Name", "Namespace", "Application Group", "Cell", "Region", "Parent Gateway", "Path", "Match Type", "Target Service", "Target Port", "Weight", "Env Scope", "Cluster Scope"]
        rows = self.db.parse_table(fp)

        rows = [r for r in rows if r.get("route_name") != name]
        rows.append({
            "route_name": name,
            "namespace": namespace,
            "application_group": apg.lower(),
            "cell": cell.lower(),
            "region": region.lower(),
            "parent_gateway": parent_agw,
            "path": path,
            "match_type": "PathPrefix",
            "target_service": target_service,
            "target_port": str(target_port),
            "weight": str(weight),
            "env_scope": env.upper() if env else "ALL",
            "cluster_scope": cluster.lower() if cluster else "ALL",
        })

        self.db.write_table(fp, "HTTPRoutes & Path Bindings", headers, rows)
        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed to add route {name}: {err}")
        return {"route": name, "path": path, "parent_agw": parent_agw, "target_service": target_service}

    def add_service_defaults(
        self,
        service: str,
        namespace: str,
        apg: str,
        cell: str,
        region: str,
        protocol: str = "http",
        mesh_gateway_mode: str = "none",
        env: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds a ServiceDefaults entry in relations/service_defaults.md."""
        fp = self.relations_dir / "service_defaults.md"
        headers = ["Service", "Namespace", "Application Group", "Cell", "Region", "Protocol", "Mutual TLS Mode", "Mesh Gateway Mode", "Env Scope", "Cluster Scope"]
        rows = self.db.parse_table(fp)

        rows = [r for r in rows if not (r.get("service") == service and r.get("region") == region.lower())]
        rows.append({
            "service": service,
            "namespace": namespace,
            "application_group": apg.lower(),
            "cell": cell.lower(),
            "region": region.lower(),
            "protocol": protocol.lower(),
            "mutual_tls_mode": "strict",
            "mesh_gateway_mode": mesh_gateway_mode,
            "env_scope": env.upper() if env else "ALL",
            "cluster_scope": cluster.lower() if cluster else "ALL",
        })

        self.db.write_table(fp, "ServiceDefaults (Consul Service Mesh)", headers, rows)
        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed to add ServiceDefaults for {service}: {err}")
        return {"service": service, "namespace": namespace, "protocol": protocol}

    def add_proxy_defaults(
        self,
        cluster: str,
        env: str,
        config: Optional[Dict[str, Any]] = None,
        apg: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds a ProxyDefaults definition for a cluster in relations/proxy_defaults.md."""
        cluster_lower = cluster.lower()
        env_upper = env.upper()
        fp = self.relations_dir / "proxy_defaults.md"
        headers = ["Name", "Environment", "Cluster", "Protocol", "Mesh Gateway Mode", "Connect Timeout (ms)"]
        rows = self.db.parse_table(fp)

        rows = [r for r in rows if not (r.get("environment", "").upper() == env_upper and r.get("cluster", "").lower() == cluster_lower)]
        rows.append({
            "name": "global",
            "environment": env_upper,
            "cluster": cluster_lower,
            "protocol": "http",
            "mesh_gateway_mode": "local",
            "connect_timeout_ms": "5000",
        })

        self.db.write_table(fp, "ProxyDefaults (Cluster-Global Singletons)", headers, rows)
        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed to add ProxyDefaults for {cluster_lower}: {err}")
        return {"name": "global", "cluster": cluster_lower, "env": env_upper}

    def add_reference_grant(
        self,
        name: str,
        namespace: str,
        apg: str,
        cell: str,
        region: str,
        env: Optional[str] = None,
        cluster: Optional[str] = None,
        from_list: Optional[List[Dict[str, Any]]] = None,
        to_list: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Adds a ReferenceGrant in relations/reference_grants.md."""
        from_item = (from_list or [{}])[0]
        to_item = (to_list or [{}])[0]

        fp = self.relations_dir / "reference_grants.md"
        headers = ["Name", "Namespace", "Application Group", "Cell", "Region", "From Group", "From Kind", "From Namespace", "To Group", "To Kind"]
        rows = self.db.parse_table(fp)

        rows = [r for r in rows if r.get("name") != name]
        rows.append({
            "name": name,
            "namespace": namespace,
            "application_group": apg.lower(),
            "cell": cell.lower(),
            "region": region.lower(),
            "from_group": from_item.get("group", "gateway.networking.k8s.io"),
            "from_kind": from_item.get("kind", "HTTPRoute"),
            "from_namespace": from_item.get("namespace", namespace),
            "to_group": to_item.get("group", ""),
            "to_kind": to_item.get("kind", "Service"),
        })

        self.db.write_table(fp, "ReferenceGrants (Gateway API Cross-Namespace Routing)", headers, rows)
        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed to add ReferenceGrant {name}: {err}")
        return {"name": name, "namespace": namespace, "apg": apg, "cell": cell, "region": region}

    def delete_item(self, category: str, key: str) -> bool:
        """Deletes an item from the matching relations/*.md table."""
        file_map = {
            "environments": ("environments.md", "environment", "Environments & Clusters Topology"),
            "application_groups": ("application_groups.md", "application_group", "Application Groups & Logical Cells"),
            "namespaces": ("namespaces.md", "namespace", "Namespaces & Regional Placement"),
            "services": ("services.md", "service", "Services Catalog"),
            "gateways": ("gateways.md", "gateway_name", "Gateways (Consul API Gateways)"),
            "http_routes": ("http_routes.md", "route_name", "HTTPRoutes & Path Bindings"),
            "service_defaults": ("service_defaults.md", "service", "ServiceDefaults (Consul Service Mesh)"),
            "proxy_defaults": ("proxy_defaults.md", "cluster", "ProxyDefaults (Cluster-Global Singletons)"),
            "reference_grants": ("reference_grants.md", "name", "ReferenceGrants (Gateway API Cross-Namespace Routing)"),
        }
        if category not in file_map:
            return False

        fname, key_field, title = file_map[category]
        fp = self.relations_dir / fname
        if not fp.exists():
            return False

        rows = self.db.parse_table(fp)
        orig_len = len(rows)

        # For services and service defaults, key might be 'service-region' or 'service'
        filtered_rows = []
        for r in rows:
            val = r.get(key_field, "")
            if val == key or f"{val}-{r.get('region', '')}" == key or f"{val}-{r.get('region', '')}-sd" == key:
                continue
            filtered_rows.append(r)

        if len(filtered_rows) == orig_len:
            return False

        # Extract headers from original table
        lines = [line.strip() for line in fp.read_text(encoding="utf-8").splitlines()]
        table_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]
        headers = [c.strip() for c in table_lines[0].strip("|").split("|")]

        self.db.write_table(fp, title, headers, filtered_rows)
        ok, err = self.db.vet()
        if not ok:
            raise RuntimeError(f"Failed after deleting {category} {key}: {err}")
        return True
