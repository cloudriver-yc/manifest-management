import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from .cue_client import CueClient, find_workspace_root


class DimensionManager:
    """Manages dynamic CRUD for dimensions and manifest entries."""

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root) if workspace_root else find_workspace_root()
        self.cue_client = CueClient(str(self.workspace_root))
        self.extensions_file = self.cue_client.cue_root / "catalog" / "extensions" / "custom.cue"


    def _read_extensions(self) -> str:
        if not self.extensions_file.exists():
            return ""
        return self.extensions_file.read_text(encoding="utf-8")

    def _write_extensions(self, content: str):
        self.extensions_file.parent.mkdir(parents=True, exist_ok=True)
        self.extensions_file.write_text(content, encoding="utf-8")

    def add_environment(
        self,
        name: str,
        clusters: Optional[Dict[str, Dict[str, Any]]] = None,
        peering_enabled: bool = False,
    ) -> Dict[str, Any]:
        """Adds a new environment dimension item."""
        env_name = name.upper()
        content = self._read_extensions()

        cluster_block = ""
        if clusters:
            for cname, cdata in clusters.items():
                dc = cdata.get("dc", "DCE")
                consul = cdata.get("consul_cluster", f"consul-{env_name.lower()}-{dc.lower()}")
                peering = cdata.get("peering_target_cluster")
                peering_str = f'\n\t\t\t\tpeering_target_cluster: "{peering}"' if peering else ""
                cluster_block += f"""
\t\t\t"{cname}": {{
\t\t\t\tname: "{cname}"
\t\t\t\tdc: "{dc}"
\t\t\t\tconsul_cluster: "{consul}"{peering_str}
\t\t\t}},"""
        else:
            # Default single cluster
            cluster_block = f"""
\t\t\t"ocp-{env_name.lower()}": {{
\t\t\t\tname: "ocp-{env_name.lower()}"
\t\t\t\tdc: "DCE"
\t\t\t\tconsul_cluster: "consul-{env_name.lower()}-dce"
\t\t\t}},"""

        cue_entry = f"""
ext_environments: "{env_name}": {{
\tname: "{env_name}"
\tclusters: {{{cluster_block}
\t}}
\tpeering_enabled: {"true" if peering_enabled else "false"}
}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
        if not ok:
            raise RuntimeError(f"Failed to add environment {env_name}: {err}")
        return {"environment": env_name, "peering_enabled": peering_enabled}

    def add_application_group(self, name: str, description: str = "") -> Dict[str, Any]:
        """Adds a new Application Group (APG) dimension item."""
        apg_name = name.lower()
        content = self._read_extensions()

        cue_entry = f"""
ext_application_groups: "{apg_name}": {{
\tname: "{apg_name}"
\tcells: {{}}
}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
        if not ok:
            raise RuntimeError(f"Failed to add APG {apg_name}: {err}")
        return {"application_group": apg_name}

    def add_cell(self, apg: str, cell: str, description: str = "") -> Dict[str, Any]:
        """Adds a new Cell under an Application Group."""
        apg_name = apg.lower()
        cell_name = cell.lower()
        content = self._read_extensions()

        cue_entry = f"""
ext_application_groups: "{apg_name}": {{
\tname: "{apg_name}"
\tcells: "{cell_name}": {{
\t\tname: "{cell_name}"
\t\tapg: "{apg_name}"
\t\tdescription: "{description or cell_name.capitalize() + ' Cell'}"
\t}}
}}
"""

        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
        if not ok:
            raise RuntimeError(f"Failed to add Cell {cell_name} to APG {apg_name}: {err}")
        return {"apg": apg_name, "cell": cell_name}

    def add_namespace(self, name: str, apg: str, cell: str, region: Optional[str] = None) -> Dict[str, Any]:
        """Adds a namespace, automatically inferring region from suffix -1 / -2 if omitted."""
        if not region:
            if name.endswith("-1"):
                region = "blue"
            elif name.endswith("-2"):
                region = "green"
            else:
                region = "blue"

        base_name = re.sub(r"-[12]$", "", name)
        content = self._read_extensions()

        cue_entry = f"""
ext_namespaces: "{name}": {{
\tname: "{name}"
\tapg: "{apg.lower()}"
\tcell: "{cell.lower()}"
\tregion: "{region.lower()}"
\tbase_name: "{base_name}"
}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
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
        """Registers a service, supporting independent versions and services between Blue and Green."""
        service_key = f"{name}-{region.lower()}"
        content = self._read_extensions()

        cue_entry = f"""
ext_services: "{service_key}": {{
\tname: "{name}"
\tnamespace: "{namespace}"
\tapg: "{apg.lower()}"
\tcell: "{cell.lower()}"
\tregion: "{region.lower()}"
\tversion: "{version}"
\tport: {port}
\tprotocol: "{protocol.lower()}"
}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
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
        env: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds an AGW (Gateway)."""
        content = self._read_extensions()
        env_str = f'\tenv: "{env.upper()}"\n' if env else ""
        cluster_str = f'\tcluster: "{cluster.lower()}"\n' if cluster else ""

        cue_entry = f"""
ext_gateways: "{name}": {{
\tname: "{name}"
\tapg: "{apg.lower()}"
\tcell: "{cell.lower()}"
\tregion: "{region.lower()}"
{env_str}{cluster_str}\tnamespace: "{namespace}"
\tlisteners: [{{
\t\tname: "http"
\t\tport: {port}
\t\tprotocol: "HTTP"
\t}}]
}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
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
        env: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds an HTTPRoute binding a path to a service through an AGW."""
        content = self._read_extensions()
        env_str = f'\tenv: "{env.upper()}"\n' if env else ""
        cluster_str = f'\tcluster: "{cluster.lower()}"\n' if cluster else ""

        cue_entry = f"""
ext_http_routes: "{name}": {{
\tname: "{name}"
\tnamespace: "{namespace}"
\tapg: "{apg.lower()}"
\tcell: "{cell.lower()}"
\tregion: "{region.lower()}"
{env_str}{cluster_str}\tparent_agw: "{parent_agw}"
\trules: [{{
\t\tname: "{name}-rule"
\t\tmatches: [{{
\t\t\tpath: {{
\t\t\t\ttype: "PathPrefix"
\t\t\t\tvalue: "{path}"
\t\t\t}}
\t\t}}]
\t\tbackendRefs: [{{
\t\t\tservice: "{target_service}"
\t\t\tport: {target_port}
\t\t\tnamespace: "{namespace}"
\t\t\tweight: 100
\t\t}}]
\t}}]
}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
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
        """Adds a ServiceDefaults entry."""
        key = f"{service}-{region.lower()}-sd"
        content = self._read_extensions()
        env_str = f'\tenv: "{env.upper()}"\n' if env else ""
        cluster_str = f'\tcluster: "{cluster.lower()}"\n' if cluster else ""

        cue_entry = f"""
ext_service_defaults: "{key}": {{
\tservice: "{service}"
\tnamespace: "{namespace}"
\tapg: "{apg.lower()}"
\tcell: "{cell.lower()}"
\tregion: "{region.lower()}"
{env_str}{cluster_str}\tprotocol: "{protocol.lower()}"
\tmeshGateway: mode: "{mesh_gateway_mode}"
\tmutualTLSMode: "strict"
}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
        if not ok:
            raise RuntimeError(f"Failed to add ServiceDefaults for {service}: {err}")
        return {"service": service, "namespace": namespace, "protocol": protocol}


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
        """Adds a ReferenceGrant entry."""
        from_items = from_list or [{
            "group": "gateway.networking.k8s.io",
            "kind": "HTTPRoute",
            "namespace": namespace,
        }]
        to_items = to_list or [{
            "group": "",
            "kind": "Service",
        }]

        from_cues = []
        for f in from_items:
            f_grp = f.get("group", "gateway.networking.k8s.io")
            f_knd = f.get("kind", "HTTPRoute")
            f_ns = f.get("namespace", namespace)
            from_cues.append(f'{{group: "{f_grp}", kind: "{f_knd}", namespace: "{f_ns}"}}')

        to_cues = []
        for t in to_items:
            t_grp = t.get("group", "")
            t_knd = t.get("kind", "Service")
            t_name = f', name: "{t["name"]}"' if "name" in t else ""
            to_cues.append(f'{{group: "{t_grp}", kind: "{t_knd}"{t_name}}}')

        env_str = f'\tenv: "{env.upper()}"\n' if env else ""
        cluster_str = f'\tcluster: "{cluster.lower()}"\n' if cluster else ""
        content = self._read_extensions()

        cue_entry = f"""
ext_reference_grants: "{name}": {{
\tname: "{name}"
\tnamespace: "{namespace}"
\tapg: "{apg.lower()}"
\tcell: "{cell.lower()}"
\tregion: "{region.lower()}"
{env_str}{cluster_str}\tfrom: [{", ".join(from_cues)}]
\tto: [{", ".join(to_cues)}]
}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
        if not ok:
            raise RuntimeError(f"Failed to add ReferenceGrant {name}: {err}")
        return {"name": name, "namespace": namespace, "apg": apg, "cell": cell, "region": region}

    def add_cluster(
        self,
        env: str,
        cluster: str,
        dc: str = "DCE",
        consul_cluster: Optional[str] = None,
        peering_target: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds a cluster under an environment in custom.cue."""
        env_upper = env.upper()
        cluster_lower = cluster.lower()
        dc_upper = dc.upper()
        consul = consul_cluster or f"consul-{env_upper.lower()}-{dc_upper.lower()}"
        content = self._read_extensions()

        peering_str = f'\n\t\tpeering_target_cluster: "{peering_target}"' if peering_target else ""
        cue_entry = f"""
ext_environments: "{env_upper}": {{
\tname: "{env_upper}"
\tclusters: "{cluster_lower}": {{
\t\tname: "{cluster_lower}"
\t\tdc: "{dc_upper}"
\t\tconsul_cluster: "{consul}"{peering_str}
\t}}
}}
"""
        content += cue_entry
        self._write_extensions(content)

        ok, err = self.cue_client.vet()
        if not ok:
            raise RuntimeError(f"Failed to add cluster {cluster_lower} to environment {env_upper}: {err}")
        return {"environment": env_upper, "cluster": cluster_lower, "dc": dc_upper}

    def add_proxy_defaults(
        self,
        cluster: str,
        env: str,
        config: Optional[Dict[str, Any]] = None,
        apg: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds a ProxyDefaults definition for a cluster."""
        import json
        cluster_lower = cluster.lower()
        env_upper = env.upper()
        key = f"{env_upper.lower()}-{cluster_lower}-global"
        cfg = config or {
            "protocol": "http",
            "access_logs": {"enabled": True},
            "tracing": {"enabled": False},
        }
        cfg_cue = json.dumps(cfg)
        apg_str = f'\tapg: "{apg.lower()}"\n' if apg else ""
        content = self._read_extensions()
        cue_entry = f"""
ext_proxy_defaults: "{key}": {{
\tname: "global"
\tenv: "{env_upper}"
\tcluster: "{cluster_lower}"
{apg_str}\tconfig: {cfg_cue}
}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
        if not ok:
            raise RuntimeError(f"Failed to add ProxyDefaults for {cluster_lower}: {err}")
        return {"key": key, "cluster": cluster_lower, "env": env_upper}

    def add_service_resolver(
        self,
        name: str,
        namespace: str,
        apg: str,
        cell: str,
        region: Optional[str] = None,
        default_subset: Optional[str] = None,
        env: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds a ServiceResolver definition."""
        content = self._read_extensions()
        reg_str = f'\tregion: "{region.lower()}"\n' if region else ""
        sub_str = f'\tdefaultSubset: "{default_subset}"\n' if default_subset else ""
        env_str = f'\tenv: "{env.upper()}"\n' if env else ""
        cls_str = f'\tcluster: "{cluster.lower()}"\n' if cluster else ""
        cue_entry = f"""
ext_service_resolvers: "{name}": {{
\tname: "{name}"
\tnamespace: "{namespace}"
\tapg: "{apg.lower()}"
\tcell: "{cell.lower()}"
{reg_str}{env_str}{cls_str}{sub_str}}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
        if not ok:
            raise RuntimeError(f"Failed to add ServiceResolver {name}: {err}")
        return {"name": name, "namespace": namespace, "apg": apg, "cell": cell}

    def add_mesh_service(
        self,
        name: str,
        namespace: str,
        apg: str,
        cell: str,
        region: Optional[str] = None,
        port: int = 8080,
        env: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds a MeshService definition."""
        content = self._read_extensions()
        reg_str = f'\tregion: "{region.lower()}"\n' if region else ""
        env_str = f'\tenv: "{env.upper()}"\n' if env else ""
        cls_str = f'\tcluster: "{cluster.lower()}"\n' if cluster else ""
        cue_entry = f"""
ext_mesh_services: "{name}": {{
\tname: "{name}"
\tnamespace: "{namespace}"
\tapg: "{apg.lower()}"
\tcell: "{cell.lower()}"
{reg_str}{env_str}{cls_str}\tport: {port}
}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
        if not ok:
            raise RuntimeError(f"Failed to add MeshService {name}: {err}")
        return {"name": name, "namespace": namespace, "apg": apg, "cell": cell}

    def add_network_policy(
        self,
        name: str,
        namespace: str,
        apg: str,
        cell: str,
        region: Optional[str] = None,
        env: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds a NetworkPolicy definition."""
        content = self._read_extensions()
        reg_str = f'\tregion: "{region.lower()}"\n' if region else ""
        env_str = f'\tenv: "{env.upper()}"\n' if env else ""
        cls_str = f'\tcluster: "{cluster.lower()}"\n' if cluster else ""
        cue_entry = f"""
ext_network_policies: "{name}": {{
\tname: "{name}"
\tnamespace: "{namespace}"
\tapg: "{apg.lower()}"
\tcell: "{cell.lower()}"
{reg_str}{env_str}{cls_str}}}
"""
        content += cue_entry
        self._write_extensions(content)
        ok, err = self.cue_client.vet()
        if not ok:
            raise RuntimeError(f"Failed to add NetworkPolicy {name}: {err}")
        return {"name": name, "namespace": namespace, "apg": apg, "cell": cell}

    def delete_item(self, category: str, key: str) -> bool:
        """Deletes an item from the custom extensions file handling nested braces."""
        content = self._read_extensions()
        prefix = f'ext_{category}: "{key}":'
        idx = content.find(prefix)
        if idx == -1:
            prefix = f'ext_{category}: \'{key}\':'
            idx = content.find(prefix)
        if idx == -1:
            return False

        # Find line start
        line_start = content.rfind("\n", 0, idx)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1

        # Find first opening brace after prefix
        open_brace = content.find("{", idx)
        if open_brace == -1:
            return False

        depth = 0
        end_idx = -1
        for i in range(open_brace, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    end_idx = i + 1
                    break

        if end_idx == -1:
            return False

        # If there is a trailing newline, consume it
        if end_idx < len(content) and content[end_idx] == "\n":
            end_idx += 1

        new_content = content[:line_start] + content[end_idx:]
        self._write_extensions(new_content)
        ok, err = self.cue_client.vet()
        if not ok:
            self._write_extensions(content)
            raise RuntimeError(f"Failed to delete {category} item {key}: {err}")
        return True

