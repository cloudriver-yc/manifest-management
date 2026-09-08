from typing import Any, Dict, List, Optional
from .markdown_db import MarkdownDB


class RelationalGraph:
    """In-memory relational query graph indexing Markdown configurations."""

    def __init__(self, db: Optional[MarkdownDB] = None):
        self.db = db or MarkdownDB()
        self.data: Dict[str, Any] = {}
        self.refresh()

    def refresh(self):
        """Reloads the unified data from Markdown relations."""
        self.data = self.db.export_system()

    @property
    def environments(self) -> Dict[str, Any]:
        return self.data.get("environments", {})

    @property
    def application_groups(self) -> Dict[str, Any]:
        return self.data.get("application_groups", {})

    @property
    def namespaces(self) -> Dict[str, Any]:
        return self.data.get("namespaces", {})

    @property
    def gateways(self) -> Dict[str, Any]:
        return self.data.get("gateways", {})

    @property
    def http_routes(self) -> Dict[str, Any]:
        return self.data.get("http_routes", {})

    @property
    def services(self) -> Dict[str, Any]:
        return self.data.get("services", {})

    @property
    def service_defaults(self) -> Dict[str, Any]:
        return self.data.get("service_defaults", {})

    @property
    def proxy_defaults(self) -> Dict[str, Any]:
        return self.data.get("proxy_defaults", {})

    @property
    def reference_grants(self) -> Dict[str, Any]:
        return self.data.get("reference_grants", {})

    def find_routes_for_path(self, target_path: str) -> List[Dict[str, Any]]:
        """Challenge 1: Find which AGW and HTTPRoute currently accommodates a given url-path."""
        matches = []
        clean_target = target_path.strip()

        for route_id, route in self.http_routes.items():
            parent_agw_name = route.get("parent_agw")
            agw = self.gateways.get(parent_agw_name, {})

            for rule in route.get("rules", []):
                for match in rule.get("matches", []):
                    path_spec = match.get("path", {})
                    path_val = path_spec.get("value", "")
                    match_type = path_spec.get("type", "PathPrefix")

                    matched = False
                    if match_type == "PathPrefix":
                        # Prefix match: target_path starts with prefix OR prefix starts with target_path
                        if clean_target.startswith(path_val) or path_val.startswith(clean_target):
                            matched = True
                    elif match_type == "Exact":
                        if clean_target == path_val:
                            matched = True

                    if matched:
                        matches.append({
                            "route_name": route.get("name"),
                            "parent_agw": parent_agw_name,
                            "agw_details": {
                                "namespace": agw.get("namespace"),
                                "cell": agw.get("cell"),
                                "region": agw.get("region"),
                                "apg": agw.get("apg"),
                            },
                            "matched_path": path_val,
                            "match_type": match_type,
                            "rule_name": rule.get("name"),
                            "route_namespace": route.get("namespace"),
                            "apg": route.get("apg"),
                            "cell": route.get("cell"),
                            "region": route.get("region"),
                            "backend_services": rule.get("backendRefs", []),
                        })
        return matches

    def get_agw_inventory(self, agw_name: str) -> Optional[Dict[str, Any]]:
        """Challenge 3: How many httproutes are bonded to a particular AGW, and how many services accommodated?"""
        # Case-insensitive search or exact
        target_agw = None
        target_key = None
        for k, v in self.gateways.items():
            if k.lower() == agw_name.lower() or v.get("name", "").lower() == agw_name.lower():
                target_key = k
                target_agw = v
                break

        if not target_agw:
            return None

        bonded_routes = []
        accommodated_services = set()
        service_details = []

        for route_id, route in self.http_routes.items():
            if route.get("parent_agw") == target_agw.get("name"):
                route_paths = []
                for rule in route.get("rules", []):
                    for m in rule.get("matches", []):
                        route_paths.append(m.get("path", {}).get("value", ""))
                    for b in rule.get("backendRefs", []):
                        svc_key = f"{b.get('service')} ({b.get('namespace')}:{b.get('port')})"
                        accommodated_services.add(svc_key)
                        service_details.append({
                            "service": b.get("service"),
                            "namespace": b.get("namespace"),
                            "port": b.get("port"),
                            "weight": b.get("weight", 100),
                            "route": route.get("name"),
                        })

                bonded_routes.append({
                    "name": route.get("name"),
                    "namespace": route.get("namespace"),
                    "paths": route_paths,
                    "cell": route.get("cell"),
                    "region": route.get("region"),
                })

        return {
            "agw_name": target_agw.get("name"),
            "apg": target_agw.get("apg"),
            "cell": target_agw.get("cell"),
            "region": target_agw.get("region"),
            "namespace": target_agw.get("namespace"),
            "listeners": target_agw.get("listeners", []),
            "bonded_route_count": len(bonded_routes),
            "bonded_routes": bonded_routes,
            "accommodated_service_count": len(accommodated_services),
            "accommodated_services": sorted(list(accommodated_services)),
            "service_bindings": service_details,
        }

    def get_proxy_defaults(
        self,
        env: str,
        cluster: str,
        cell: Optional[str] = None,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Challenge 2: Query the ProxyDefaults for a Consul cluster.
        Note: In Consul Service Mesh, ProxyDefaults is a mesh-wide global configuration.
        Each Consul cluster has exactly 1 ProxyDefaults ('global') applying across all cells & regions.
        """
        env_upper = env.upper()
        cluster_lower = cluster.lower()

        matched_entry = None
        match_level = "none"

        for k, pd in self.proxy_defaults.items():
            pd_env = pd.get("env", "").upper()
            pd_cluster = pd.get("cluster", "").lower()

            if (pd_env == env_upper or pd_env == "ALL") and (pd_cluster == cluster_lower or pd_cluster == "all"):
                if pd_cluster == cluster_lower:
                    matched_entry = pd
                    match_level = "cluster_global"
                    break
                elif pd_env == "ALL" and pd_cluster == "ALL" and match_level == "none":
                    matched_entry = pd
                    match_level = "global_default"

        scope_note = None
        if cell or region:
            scope_note = (
                f"Note: ProxyDefaults is a mesh-wide global configuration in Consul Service Mesh. "
                f"Consul cluster on '{cluster_lower}' ({env_upper}) has exactly 1 ProxyDefaults ('global') "
                f"which applies globally across all cells ({cell or 'all cells'}) and regions ({region or 'all regions'})."
            )

        return {
            "query": {
                "env": env_upper,
                "cluster": cluster_lower,
                "cell": cell,
                "region": region,
            },
            "match_level": match_level,
            "scope_note": scope_note,
            "proxy_defaults": matched_entry,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Provides high-level dashboard metrics."""
        return {
            "environments": list(self.environments.keys()),
            "application_groups": list(self.application_groups.keys()),
            "total_namespaces": len(self.namespaces),
            "total_gateways": len(self.gateways),
            "total_http_routes": len(self.http_routes),
            "total_services": len(self.services),
            "total_service_defaults": len(self.service_defaults),
            "total_proxy_defaults": len(self.proxy_defaults),
        }
