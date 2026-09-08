import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def find_workspace_root(start_path: Optional[Path] = None) -> Path:
    """Finds the workspace root directory by searching parents for relations/ or GEMINI.md."""
    if "WORKSPACE_ROOT" in os.environ:
        return Path(os.environ["WORKSPACE_ROOT"])
    curr = (start_path or Path.cwd()).resolve()
    for p in [curr, *curr.parents]:
        if (p / "relations").is_dir() or (p / "GEMINI.md").is_file():
            return p
    return Path.cwd()


class MarkdownDB:
    """Pure Markdown-driven Relational Database engine.

    Parses, validates, and manages multi-dimensional relations in relations/*.md.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        if workspace_root is None:
            self.workspace_root = find_workspace_root(Path(__file__).resolve())
        else:
            self.workspace_root = Path(workspace_root)
        self.relations_dir = self.workspace_root / "relations"

    @staticmethod
    def parse_table(file_path: Path) -> List[Dict[str, str]]:
        """Parses a GitHub Flavored Markdown table into a list of row dictionaries."""
        if not file_path.exists():
            return []

        lines = [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines()]
        table_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]
        if len(table_lines) < 2:
            return []

        # Parse header
        raw_headers = [c.strip() for c in table_lines[0].strip("|").split("|")]
        header_keys = [h.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_") for h in raw_headers]

        # Ignore separator (line index 1)
        rows: List[Dict[str, str]] = []
        for line in table_lines[2:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) != len(header_keys):
                continue
            row_dict = {}
            for k, val in zip(header_keys, cells):
                row_dict[k] = "" if val in ["-", ""] else val
            rows.append(row_dict)
        return rows

    @staticmethod
    def write_table(file_path: Path, title: str, headers: List[str], rows: List[Dict[str, Any]]):
        """Writes a formatted, aligned GFM table to a Markdown file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        header_keys = [h.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_") for h in headers]

        # Compute column widths
        widths = [len(h) for h in headers]
        for row in rows:
            for i, k in enumerate(header_keys):
                val_str = str(row.get(k, "") or "-")
                if len(val_str) > widths[i]:
                    widths[i] = len(val_str)

        header_line = "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |"
        sep_line = "|-" + "-|-".join("-" * widths[i] for i in range(len(headers))) + "-|"

        data_lines = []
        for row in rows:
            line_cells = []
            for i, k in enumerate(header_keys):
                raw_val = row.get(k, "")
                val_str = str(raw_val) if raw_val not in ["", None] else "-"
                line_cells.append(val_str.ljust(widths[i]))
            data_lines.append("| " + " | ".join(line_cells) + " |")

        content = f"# {title}\n\n{header_line}\n{sep_line}\n"
        if data_lines:
            content += "\n".join(data_lines) + "\n"
        file_path.write_text(content, encoding="utf-8")

    def export_system(self) -> Dict[str, Any]:
        """Loads and converts all relations/*.md tables into the canonical system dictionary."""
        envs_data: Dict[str, Any] = {}
        env_rows = self.parse_table(self.relations_dir / "environments.md")
        for r in env_rows:
            env_name = r.get("environment", "").upper()
            cluster = r.get("cluster", "").lower()
            dc = r.get("data_center", "DCE").upper()
            consul = r.get("consul_cluster") or f"consul-{env_name.lower()}-{dc.lower()}"
            peering_raw = str(r.get("peering_enabled", "false")).lower()
            peering = peering_raw in ["true", "yes", "1"]
            peering_target = r.get("peering_target")

            if env_name not in envs_data:
                envs_data[env_name] = {
                    "name": env_name,
                    "peering_enabled": peering,
                    "clusters": {},
                }
            if cluster:
                c_dict: Dict[str, Any] = {
                    "name": cluster,
                    "dc": dc,
                    "consul_cluster": consul,
                }
                if peering_target and peering_target != "-":
                    c_dict["peering_target_cluster"] = peering_target
                envs_data[env_name]["clusters"][cluster] = c_dict

        # 2. Application Groups & Cells
        apgs_data: Dict[str, Any] = {}
        apg_rows = self.parse_table(self.relations_dir / "application_groups.md")
        for r in apg_rows:
            apg = r.get("application_group", "").lower()
            cell = r.get("cell", "").lower()
            desc = r.get("description", "")
            if not apg:
                continue
            if apg not in apgs_data:
                apgs_data[apg] = {"name": apg, "cells": {}}
            if cell:
                apgs_data[apg]["cells"][cell] = {"name": cell, "description": desc}

        # 3. Namespaces
        ns_data: Dict[str, Any] = {}
        ns_rows = self.parse_table(self.relations_dir / "namespaces.md")
        for r in ns_rows:
            ns_name = r.get("namespace", "").lower()
            apg = r.get("application_group", "").lower()
            cell = r.get("cell", "").lower()
            region = r.get("region", "").lower()
            if not region:
                region = "blue" if ns_name.endswith("-1") else "green"
            if ns_name:
                ns_data[ns_name] = {
                    "name": ns_name,
                    "apg": apg,
                    "cell": cell,
                    "region": region,
                }

        # 4. Gateways
        gw_data: Dict[str, Any] = {}
        gw_rows = self.parse_table(self.relations_dir / "gateways.md")
        for r in gw_rows:
            gw_name = r.get("gateway_name", "")
            ns = r.get("namespace", "")
            apg = r.get("application_group", "").lower()
            cell = r.get("cell", "").lower()
            region = r.get("region", "").lower()
            port_str = r.get("port", "8080")
            port = int(port_str) if port_str and port_str.isdigit() else 8080
            proto = r.get("protocol", "HTTP").upper()
            allowed = r.get("route_allowed_from", "Same")
            if gw_name:
                gw_data[gw_name] = {
                    "name": gw_name,
                    "namespace": ns,
                    "apg": apg,
                    "cell": cell,
                    "region": region,
                    "listeners": [
                        {
                            "name": "http",
                            "port": port,
                            "protocol": proto,
                            "allowedRoutes": {"namespaces": {"from": allowed}},
                        }
                    ],
                }

        # 5. Services
        svc_data: Dict[str, Any] = {}
        svc_rows = self.parse_table(self.relations_dir / "services.md")
        for r in svc_rows:
            svc_name = r.get("service", "")
            ns = r.get("namespace", "")
            apg = r.get("application_group", "").lower()
            cell = r.get("cell", "").lower()
            region = r.get("region", "").lower()
            port_str = r.get("port", "8080")
            port = int(port_str) if port_str and port_str.isdigit() else 8080
            proto = r.get("protocol", "http").lower()
            ver = r.get("version", "v1.0.0")
            if svc_name:
                svc_key = f"{svc_name}-{region}"
                svc_data[svc_key] = {
                    "name": svc_name,
                    "service": svc_name,
                    "namespace": ns,
                    "apg": apg,
                    "cell": cell,
                    "region": region,
                    "port": port,
                    "protocol": proto,
                    "version": ver,
                }

        # 6. HTTPRoutes
        routes_data: Dict[str, Any] = {}
        route_rows = self.parse_table(self.relations_dir / "http_routes.md")
        for r in route_rows:
            r_name = r.get("route_name", "")
            ns = r.get("namespace", "")
            apg = r.get("application_group", "").lower()
            cell = r.get("cell", "").lower()
            region = r.get("region", "").lower()
            parent_gw = r.get("parent_gateway", "")
            path_val = r.get("path", "")
            match_type = r.get("match_type", "PathPrefix")
            target_svc = r.get("target_service", "")
            port_str = r.get("target_port", "8080")
            port = int(port_str) if port_str and port_str.isdigit() else 8080
            weight_str = r.get("weight", "100")
            weight = int(weight_str) if weight_str and weight_str.isdigit() else 100
            env_scope = r.get("env_scope")
            if env_scope in ["ALL", "all", "", "-"]:
                env_scope = None
            cluster_scope = r.get("cluster_scope")
            if cluster_scope in ["ALL", "all", "", "-"]:
                cluster_scope = None

            if r_name:
                route_obj: Dict[str, Any] = {
                    "name": r_name,
                    "namespace": ns,
                    "apg": apg,
                    "cell": cell,
                    "region": region,
                    "parent_agw": parent_gw,
                    "rules": [
                        {
                            "name": f"{r_name}-rule",
                            "matches": [
                                {
                                    "path": {
                                        "type": match_type,
                                        "value": path_val,
                                    }
                                }
                            ],
                            "backendRefs": [
                                {
                                    "service": target_svc,
                                    "namespace": ns,
                                    "port": port,
                                    "weight": weight,
                                }
                            ],
                        }
                    ],
                }
                if env_scope:
                    route_obj["env"] = env_scope.upper()
                if cluster_scope:
                    route_obj["cluster"] = cluster_scope.lower()
                routes_data[r_name] = route_obj

        # 7. ServiceDefaults
        sd_data: Dict[str, Any] = {}
        sd_rows = self.parse_table(self.relations_dir / "service_defaults.md")
        for r in sd_rows:
            svc = r.get("service", "")
            ns = r.get("namespace", "")
            apg = r.get("application_group", "").lower()
            cell = r.get("cell", "").lower()
            region = r.get("region", "").lower()
            proto = r.get("protocol", "http").lower()
            mtls = r.get("mutual_tls_mode", "strict")
            mgw = r.get("mesh_gateway_mode")
            env_s = r.get("env_scope")
            if env_s in ["ALL", "all", "", "-"]:
                env_s = None
            cl_s = r.get("cluster_scope")
            if cl_s in ["ALL", "all", "", "-"]:
                cl_s = None

            if svc:
                sd_key = f"{svc}-{region}-sd"
                sd_obj: Dict[str, Any] = {
                    "service": svc,
                    "namespace": ns,
                    "apg": apg,
                    "cell": cell,
                    "region": region,
                    "protocol": proto,
                    "mutualTLSMode": mtls,
                }
                if mgw and mgw != "-":
                    sd_obj["meshGateway"] = {"mode": mgw}
                if env_s:
                    sd_obj["env"] = env_s.upper()
                if cl_s:
                    sd_obj["cluster"] = cl_s.lower()
                sd_data[sd_key] = sd_obj

        # 8. ProxyDefaults
        pd_data: Dict[str, Any] = {}
        pd_rows = self.parse_table(self.relations_dir / "proxy_defaults.md")
        for r in pd_rows:
            name = r.get("name", "global")
            env = r.get("environment", "").upper()
            cluster = r.get("cluster", "").lower()
            proto = r.get("protocol", "http")
            mgw = r.get("mesh_gateway_mode", "local")
            timeout_str = r.get("connect_timeout_ms", "5000")
            timeout = int(timeout_str) if timeout_str and timeout_str.isdigit() else 5000

            if env and cluster:
                pd_key = f"pd-{env.lower()}-{cluster}"
                pd_data[pd_key] = {
                    "name": name,
                    "env": env,
                    "cluster": cluster,
                    "config": {
                        "protocol": proto,
                        "connectTimeoutMs": timeout,
                        "meshGateway": {"mode": mgw},
                    },
                }

        # 9. ReferenceGrants
        rg_data: Dict[str, Any] = {}
        rg_rows = self.parse_table(self.relations_dir / "reference_grants.md")
        for r in rg_rows:
            name = r.get("name", "")
            ns = r.get("namespace", "")
            apg = r.get("application_group", "").lower()
            cell = r.get("cell", "").lower()
            region = r.get("region", "").lower()
            f_group = r.get("from_group", "gateway.networking.k8s.io")
            f_kind = r.get("from_kind", "HTTPRoute")
            f_ns = r.get("from_namespace", ns)
            t_group = r.get("to_group", "")
            t_kind = r.get("to_kind", "Service")
            if name:
                rg_data[name] = {
                    "name": name,
                    "namespace": ns,
                    "apg": apg,
                    "cell": cell,
                    "region": region,
                    "from": [{"group": f_group, "kind": f_kind, "namespace": f_ns}],
                    "to": [{"group": t_group, "kind": t_kind}],
                }

        return {
            "environments": envs_data,
            "application_groups": apgs_data,
            "namespaces": ns_data,
            "gateways": gw_data,
            "http_routes": routes_data,
            "services": svc_data,
            "service_defaults": sd_data,
            "proxy_defaults": pd_data,
            "reference_grants": rg_data,
        }

    def eval_expression(self, expr: str) -> Any:
        """Evaluates a dot-path expression against the exported system catalog."""
        data = self.export_system()
        parts = expr.strip().split(".")
        if parts[0] == "system":
            parts = parts[1:]
        curr = data
        for p in parts:
            if not p:
                continue
            if isinstance(curr, dict) and p in curr:
                curr = curr[p]
            else:
                return {}
        return curr

    def vet(self) -> Tuple[bool, str]:
        """Validates referential integrity, schemas, and invariants across all Markdown tables."""
        errors: List[str] = []

        # 1. Check table existence
        required_files = [
            "environments.md",
            "application_groups.md",
            "namespaces.md",
            "services.md",
            "gateways.md",
            "http_routes.md",
            "service_defaults.md",
            "proxy_defaults.md",
            "reference_grants.md",
        ]
        for rf in required_files:
            fp = self.relations_dir / rf
            if not fp.exists():
                errors.append(f"Missing required relation file: relations/{rf}")

        if errors:
            return False, "\n".join(errors)

        try:
            sys_data = self.export_system()
        except Exception as e:
            return False, f"Failed to parse Markdown relations: {e}"

        envs = sys_data["environments"]
        apgs = sys_data["application_groups"]
        namespaces = sys_data["namespaces"]
        gateways = sys_data["gateways"]
        routes = sys_data["http_routes"]
        services = sys_data["services"]
        proxy_defaults = sys_data["proxy_defaults"]

        # Validate Clusters & Data Centers
        valid_clusters = set()
        for env_name, env_data in envs.items():
            for cname, cdata in env_data.get("clusters", {}).items():
                valid_clusters.add(cname.lower())
                dc = cdata.get("dc", "")
                if dc not in ["DCE", "DCW"]:
                    errors.append(f"Environment '{env_name}' cluster '{cname}' has invalid DC '{dc}' (must be DCE or DCW).")

        # Validate Namespaces
        for ns_name, ns in namespaces.items():
            apg = ns.get("apg")
            cell = ns.get("cell")
            reg = ns.get("region")
            if apg and apg not in apgs:
                errors.append(f"Namespace '{ns_name}' references unknown APG '{apg}'.")
            elif apg and cell and cell not in apgs[apg].get("cells", {}):
                errors.append(f"Namespace '{ns_name}' references unknown Cell '{cell}' in APG '{apg}'.")

            if reg == "blue" and not ns_name.endswith("-1"):
                errors.append(f"Blue namespace '{ns_name}' must end with '-1'.")
            elif reg == "green" and not ns_name.endswith("-2"):
                errors.append(f"Green namespace '{ns_name}' must end with '-2'.")
            elif ns_name.endswith("-1") and reg != "blue":
                errors.append(f"Namespace '{ns_name}' suffix '-1' indicates blue region, but region is '{reg}'.")
            elif ns_name.endswith("-2") and reg != "green":
                errors.append(f"Namespace '{ns_name}' suffix '-2' indicates green region, but region is '{reg}'.")

        # Validate Services
        for svc_key, svc in services.items():
            port = svc.get("port")
            if not isinstance(port, int) or not (1 <= port <= 65535):
                errors.append(f"Service '{svc.get('name')}' has invalid port '{port}' (must be 1-65535).")
            ns = svc.get("namespace")
            if ns and ns not in namespaces:
                errors.append(f"Service '{svc.get('name')}' references unregistered namespace '{ns}'.")

        # Validate Gateways
        for gw_name, gw in gateways.items():
            ns = gw.get("namespace")
            if ns and ns not in namespaces:
                errors.append(f"Gateway '{gw_name}' references unregistered namespace '{ns}'.")

        # Validate HTTPRoutes
        for r_name, r in routes.items():
            gw = r.get("parent_agw")
            if gw and gw not in gateways:
                errors.append(f"HTTPRoute '{r_name}' references unregistered parent gateway '{gw}'.")
            for rule in r.get("rules", []):
                for m in rule.get("matches", []):
                    path_val = m.get("path", {}).get("value", "")
                    if path_val and not path_val.startswith("/"):
                        errors.append(f"HTTPRoute '{r_name}' path prefix '{path_val}' must start with '/'.")

        # Validate ProxyDefaults (Strict Singleton: strictly 1 per cluster)
        seen_pd_clusters = set()
        for pd_key, pd in proxy_defaults.items():
            cluster = pd.get("cluster", "").lower()
            if cluster in seen_pd_clusters:
                errors.append(f"Consul cluster '{cluster}' violates ProxyDefaults singleton: multiple ProxyDefaults defined.")
            seen_pd_clusters.add(cluster)

        if errors:
            return False, "\n".join(f"[-] {e}" for e in errors)
        return True, ""
