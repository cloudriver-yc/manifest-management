import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from .markdown_db import MarkdownDB, find_workspace_root
from .graph import RelationalGraph


class ManifestGenerator:
    """Generates GitOps-ready Kubernetes and Consul Service Mesh YAML manifests."""

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root) if workspace_root else find_workspace_root()
        self.db = MarkdownDB(str(self.workspace_root))
        self.graph = RelationalGraph(self.db)

    def export_all(self, target_dir: Optional[str] = None, env_filter: Optional[str] = None) -> Dict[str, Any]:
        """Compiles and exports manifests across environments and clusters."""
        out_root = Path(target_dir) if target_dir else (self.workspace_root / "output")
        out_root.mkdir(parents=True, exist_ok=True)

        exported_files = []
        environments = self.graph.environments

        for env_name, env_data in environments.items():
            if env_filter and env_name.upper() != env_filter.upper():
                continue

            clusters = env_data.get("clusters", {})
            for cluster_name, cluster_data in clusters.items():
                cluster_dc = cluster_data.get("dc", "DCE")

                # Generate ProxyDefaults for this cluster
                for pd_key, pd in self.graph.proxy_defaults.items():
                    pd_env = pd.get("env", "ALL")
                    pd_cluster = pd.get("cluster", "ALL")
                    if (pd_env in [env_name, "ALL"]) and (pd_cluster in [cluster_name, "ALL"]):
                        pd_yaml = self._render_proxy_defaults(pd)
                        pd_file = out_root / env_name / cluster_name / "consul" / f"proxy-defaults-{pd.get('name')}.yaml"
                        pd_file.parent.mkdir(parents=True, exist_ok=True)
                        pd_file.write_text(pd_yaml, encoding="utf-8")
                        exported_files.append(str(pd_file))

                # Generate Gateways, HTTPRoutes, and ServiceDefaults for each APG and Region
                # Cross-DC Symmetry: DCE and DCW generate the same service configs
                for gw_key, gw in self.graph.gateways.items():
                    gw_env = gw.get("env")
                    if gw_env and gw_env.upper() != env_name.upper():
                        continue
                    gw_cluster = gw.get("cluster")
                    if gw_cluster and gw_cluster.lower() != cluster_name.lower():
                        continue
                    apg = gw.get("apg")
                    region = gw.get("region")
                    gw_yaml = self._render_gateway(gw)
                    gw_file = out_root / env_name / cluster_name / apg / region / f"gateway-{gw.get('name')}.yaml"
                    gw_file.parent.mkdir(parents=True, exist_ok=True)
                    gw_file.write_text(gw_yaml, encoding="utf-8")
                    exported_files.append(str(gw_file))

                for route_key, route in self.graph.http_routes.items():
                    r_env = route.get("env")
                    if r_env and r_env.upper() != env_name.upper():
                        continue
                    r_cluster = route.get("cluster")
                    if r_cluster and r_cluster.lower() != cluster_name.lower():
                        continue
                    apg = route.get("apg")
                    region = route.get("region")
                    route_yaml = self._render_http_route(route)
                    route_file = out_root / env_name / cluster_name / apg / region / f"httproute-{route.get('name')}.yaml"
                    route_file.parent.mkdir(parents=True, exist_ok=True)
                    route_file.write_text(route_yaml, encoding="utf-8")
                    exported_files.append(str(route_file))

                for sd_key, sd in self.graph.service_defaults.items():
                    sd_env = sd.get("env")
                    if sd_env and sd_env.upper() != env_name.upper():
                        continue
                    sd_cluster = sd.get("cluster")
                    if sd_cluster and sd_cluster.lower() != cluster_name.lower():
                        continue
                    apg = sd.get("apg")
                    region = sd.get("region")
                    sd_yaml = self._render_service_defaults(sd)
                    sd_file = out_root / env_name / cluster_name / apg / region / f"service-defaults-{sd.get('service')}.yaml"
                    sd_file.parent.mkdir(parents=True, exist_ok=True)
                    sd_file.write_text(sd_yaml, encoding="utf-8")
                    exported_files.append(str(sd_file))


                for rg_key, rg in self.graph.reference_grants.items():
                    rg_env = rg.get("env")
                    if rg_env and rg_env.upper() != env_name.upper():
                        continue
                    rg_cluster = rg.get("cluster")
                    if rg_cluster and rg_cluster.lower() != cluster_name.lower():
                        continue
                    apg = rg.get("apg")
                    region = rg.get("region")
                    rg_yaml = self._render_reference_grant(rg)
                    rg_file = out_root / env_name / cluster_name / apg / region / f"referencegrant-{rg.get('name')}.yaml"
                    rg_file.parent.mkdir(parents=True, exist_ok=True)
                    rg_file.write_text(rg_yaml, encoding="utf-8")
                    exported_files.append(str(rg_file))

        return {
            "output_dir": str(out_root),
            "total_files": len(exported_files),
            "files": exported_files,
        }

    def _render_gateway(self, gw: Dict[str, Any]) -> str:
        doc = {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "Gateway",
            "metadata": {
                "name": gw.get("name"),
                "namespace": gw.get("namespace"),
                "labels": {
                    "apg": gw.get("apg"),
                    "cell": gw.get("cell"),
                    "region": gw.get("region"),
                },
            },
            "spec": {
                "gatewayClassName": "consul-api-gateway",
                "listeners": [
                    {
                        "name": l.get("name", "http"),
                        "port": l.get("port", 8080),
                        "protocol": l.get("protocol", "HTTP"),
                        "allowedRoutes": {
                            "namespaces": {"from": "Same"},
                        },
                    }
                    for l in gw.get("listeners", [])
                ],
            },
        }
        return yaml.dump(doc, sort_keys=False)

    def _render_http_route(self, route: Dict[str, Any]) -> str:
        rules = []
        for r in route.get("rules", []):
            rule_entry = {
                "matches": [
                    {
                        "path": {
                            "type": m.get("path", {}).get("type", "PathPrefix"),
                            "value": m.get("path", {}).get("value"),
                        }
                    }
                    for m in r.get("matches", [])
                ],
                "backendRefs": [
                    {
                        "name": b.get("service"),
                        "namespace": b.get("namespace"),
                        "port": b.get("port", 8080),
                        "weight": b.get("weight", 100),
                    }
                    for b in r.get("backendRefs", [])
                ],
            }
            rules.append(rule_entry)

        doc = {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "HTTPRoute",
            "metadata": {
                "name": route.get("name"),
                "namespace": route.get("namespace"),
                "labels": {
                    "apg": route.get("apg"),
                    "cell": route.get("cell"),
                    "region": route.get("region"),
                },
            },
            "spec": {
                "parentRefs": [
                    {"name": route.get("parent_agw")},
                ],
                "rules": rules,
            },
        }
        return yaml.dump(doc, sort_keys=False)

    def _render_service_defaults(self, sd: Dict[str, Any]) -> str:
        doc = {
            "apiVersion": "consul.hashicorp.com/v1alpha1",
            "kind": "ServiceDefaults",
            "metadata": {
                "name": sd.get("service"),
                "namespace": sd.get("namespace"),
                "labels": {
                    "apg": sd.get("apg"),
                    "cell": sd.get("cell"),
                    "region": sd.get("region"),
                },
            },
            "spec": {
                "protocol": sd.get("protocol", "http"),
                "mutualTLSMode": sd.get("mutualTLSMode", "strict"),
            },
        }
        if "meshGateway" in sd:
            doc["spec"]["meshGateway"] = sd["meshGateway"]
        return yaml.dump(doc, sort_keys=False)

    def _render_proxy_defaults(self, pd: Dict[str, Any]) -> str:
        config = pd.get("config", {})
        doc = {
            "apiVersion": "consul.hashicorp.com/v1alpha1",
            "kind": "ProxyDefaults",
            "metadata": {
                "name": pd.get("name", "global"),
                "labels": {
                    "env": pd.get("env"),
                    "cluster": pd.get("cluster"),
                },
            },
            "spec": {
                "config": config,
            },
        }
        if pd.get("cell"):
            doc["metadata"]["labels"]["cell"] = pd["cell"]
        if pd.get("region"):
            doc["metadata"]["labels"]["region"] = pd["region"]
        return yaml.dump(doc, sort_keys=False)

    def _render_reference_grant(self, rg: Dict[str, Any]) -> str:
        doc = {
            "apiVersion": "gateway.networking.k8s.io/v1beta1",
            "kind": "ReferenceGrant",
            "metadata": {
                "name": rg.get("name"),
                "namespace": rg.get("namespace"),
                "labels": {
                    "component": f"{rg.get('apg')}-banking-{rg.get('env', 'uat').lower()}",
                    "deployment": rg.get("region"),
                    "environment": rg.get("env", "uat").lower(),
                },
            },
            "spec": {
                "from": [
                    {
                        "group": f.get("group", "gateway.networking.k8s.io"),
                        "kind": f.get("kind", "HTTPRoute"),
                        "namespace": f.get("namespace", rg.get("namespace")),
                    }
                    for f in rg.get("from", [])
                ],
                "to": [
                    {
                        "group": t.get("group", ""),
                        "kind": t.get("kind", "Service"),
                    }
                    for t in rg.get("to", [])
                ],
            },
        }
        return yaml.dump(doc, sort_keys=False)
