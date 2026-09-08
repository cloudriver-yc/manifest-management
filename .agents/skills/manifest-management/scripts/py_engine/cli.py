import argparse
import json
import sys
from typing import Optional
import yaml
from .markdown_db import MarkdownDB
from .dimension_mgr import DimensionManager
from .generator import ManifestGenerator
from .graph import RelationalGraph
from .manifest_parser import ManifestParser


def print_json(data):
    print(json.dumps(data, indent=2))


def handle_query_path(args, graph: RelationalGraph):
    res = graph.find_routes_for_path(args.path)
    output_fmt = getattr(args, "output", "yaml")
    if not res:
        if output_fmt in ["yaml", "manifest"]:
            print(f"# No matching HTTPRoute or AGW found for path: {args.path}")
        else:
            print(f"[-] No matching HTTPRoute or AGW found for path: {args.path}")
        return

    if output_fmt in ["yaml", "manifest"]:
        gen = ManifestGenerator()
        manifests = []
        for r in res:
            route_obj = graph.http_routes.get(r["route_name"])
            if route_obj:
                manifests.append(gen._render_http_route(route_obj).strip())
        print("\n---\n".join(manifests))
    elif output_fmt == "json":
        print_json(res)
    else:
        print(f"\n[+] Found {len(res)} matching route(s) for path '{args.path}':")
        for r in res:
            print(f"\n  • Route Name      : {r['route_name']} (Namespace: {r['route_namespace']})")
            print(f"    Parent AGW      : {r['parent_agw']}")
            print(f"    APG / Cell / Reg: {r['apg']} / {r['cell']} / {r['region'].upper()}")
            print(f"    Matched Prefix  : {r['matched_path']} ({r['match_type']})")
            print(f"    Backend Services:")
            for b in r["backend_services"]:
                print(f"      - {b.get('service')} (port: {b.get('port')}, ns: {b.get('namespace')}, weight: {b.get('weight')}%)")
        print()


def handle_query_agw(args, graph: RelationalGraph):
    inv = graph.get_agw_inventory(args.name)
    output_fmt = getattr(args, "output", "yaml")
    if not inv:
        if output_fmt in ["yaml", "manifest"]:
            print(f"# AGW not found: {args.name}")
        else:
            print(f"[-] AGW not found: {args.name}")
        return

    if output_fmt in ["yaml", "manifest"]:
        gen = ManifestGenerator()
        gw_obj = None
        for k, v in graph.gateways.items():
            if k.lower() == args.name.lower() or v.get("name", "").lower() == args.name.lower():
                gw_obj = v
                break
        manifests = []
        if gw_obj:
            manifests.append(gen._render_gateway(gw_obj).strip())
        for r in inv["bonded_routes"]:
            route_obj = graph.http_routes.get(r["name"])
            if route_obj:
                manifests.append(gen._render_http_route(route_obj).strip())
        print("\n---\n".join(manifests))
    elif output_fmt == "json":
        print_json(inv)
    else:
        print(f"\n========================================================")
        print(f" AGW Inventory: {inv['agw_name']}")
        print(f"========================================================")
        print(f" APG / Cell / Region : {inv['apg']} / {inv['cell']} / {inv['region'].upper()}")
        print(f" Host Namespace      : {inv['namespace']}")
        print(f" Listeners           : {', '.join(str(l.get('port')) + '/' + l.get('protocol') for l in inv['listeners'])}")
        print(f" Bonded HTTPRoutes   : {inv['bonded_route_count']}")
        for r in inv["bonded_routes"]:
            paths_str = ", ".join(r["paths"])
            print(f"   - {r['name']} (Paths: {paths_str})")
        print(f" Accommodated Services ({inv['accommodated_service_count']} unique):")
        for svc in inv["accommodated_services"]:
            print(f"   * {svc}")
        print()


def handle_query_proxy_defaults(args, graph: RelationalGraph):
    res = graph.get_proxy_defaults(
        env=args.env,
        cluster=args.cluster,
        cell=args.cell,
        region=args.region,
    )
    output_fmt = getattr(args, "output", "yaml")
    if not res["proxy_defaults"]:
        if output_fmt in ["yaml", "manifest"]:
            print(f"# No matching ProxyDefaults found for env={args.env}, cluster={args.cluster}")
        else:
            print(f"[-] No matching ProxyDefaults found for env={args.env}, cluster={args.cluster}")
        return

    if output_fmt in ["yaml", "manifest"]:
        gen = ManifestGenerator()
        print(gen._render_proxy_defaults(res["proxy_defaults"]).strip())
    elif output_fmt == "json":
        print_json(res["proxy_defaults"])
    else:
        print(f"\n[+] ProxyDefaults Query Result (Match level: {res['match_level']}):")
        if res.get("scope_note"):
            print(f"  ℹ️  {res['scope_note']}")
        print(f"  Name    : {res['proxy_defaults'].get('name')}")
        print(f"  Env     : {res['proxy_defaults'].get('env')}")
        print(f"  Cluster : {res['proxy_defaults'].get('cluster')}")
        print(f"  APG     : {res['proxy_defaults'].get('apg', 'ncbs')}")
        print(f"  Config  :")
        print(json.dumps(res["proxy_defaults"].get("config", {}), indent=4))
        print()


def handle_query_grant(args, graph: RelationalGraph):
    output_fmt = getattr(args, "output", "yaml")
    apg_filter = getattr(args, "apg", None)
    ns_filter = getattr(args, "namespace", None)
    cell_filter = getattr(args, "cell", None)
    region_filter = getattr(args, "region", None)

    matched = []
    for k, rg in graph.reference_grants.items():
        if apg_filter and rg.get("apg", "").lower() != apg_filter.lower():
            continue
        if ns_filter and rg.get("namespace", "").lower() != ns_filter.lower():
            continue
        if region_filter and rg.get("region", "").lower() != region_filter.lower():
            continue
        if cell_filter:
            rg_cell = rg.get("cell", "").lower()
            rg_region = rg.get("region", "").lower()
            # If user specifies 'blue'/'green' as cell, gracefully match region or cell
            if cell_filter.lower() in ["blue", "green"]:
                if rg_region != cell_filter.lower() and rg_cell != cell_filter.lower():
                    continue
            else:
                if rg_cell != cell_filter.lower():
                    continue
        matched.append(rg)

    if not matched:
        filters = []
        if apg_filter: filters.append(f"apg={apg_filter}")
        if cell_filter: filters.append(f"cell={cell_filter}")
        if region_filter: filters.append(f"region={region_filter}")
        if ns_filter: filters.append(f"namespace={ns_filter}")
        f_str = ", ".join(filters) if filters else "ALL"
        if output_fmt in ["yaml", "manifest"]:
            print(f"# No ReferenceGrant found for {f_str}")
        else:
            print(f"[-] No ReferenceGrant found for {f_str}")
        return

    if output_fmt in ["yaml", "manifest"]:
        gen = ManifestGenerator()
        manifests = [gen._render_reference_grant(rg).strip() for rg in matched]
        print("\n---\n".join(manifests))
    elif output_fmt == "json":
        print_json(matched)
    else:
        print(f"\n[+] Found {len(matched)} ReferenceGrant(s):")
        for rg in matched:
            print(f"  - Name: {rg.get('name')} (Namespace: {rg.get('namespace')}, APG: {rg.get('apg')}, Cell: {rg.get('cell')})")
        print()


def handle_query_find(args, graph: RelationalGraph):
    output_fmt = getattr(args, "output", "yaml")
    filters_raw = getattr(args, "filters", [])
    kind = (getattr(args, "kind", None) or "all").lower()

    kv_filters = {}
    bare_terms = []

    known_kinds = {
        "grant": "grant", "referencegrant": "grant", "grants": "grant",
        "route": "route", "httproute": "route", "routes": "route",
        "gateway": "gateway", "agw": "gateway", "gateways": "gateway",
        "service": "service", "services": "service",
        "service-defaults": "service-defaults", "servicedefaults": "service-defaults",
        "proxy-defaults": "proxy-defaults", "proxydefaults": "proxy-defaults",
    }

    for f in filters_raw:
        if "=" in f:
            k, v = f.split("=", 1)
            kv_filters[k.strip().lower()] = v.strip().lower()
        else:
            token = f.strip().lower()
            if kind == "all" and token in known_kinds:
                kind = known_kinds[token]
            else:
                bare_terms.append(token)

    gen = ManifestGenerator()

    def item_matches(item: dict) -> bool:
        item_str = json.dumps(item).lower()
        for term in bare_terms:
            if term not in item_str:
                return False
        for k, v in kv_filters.items():
            if k == "region":
                item_reg = str(item.get("region", "")).lower()
                ns = str(item.get("namespace", "")).lower()
                if v == "blue" and (item_reg == "blue" or ns.endswith("-1")):
                    continue
                if v == "green" and (item_reg == "green" or ns.endswith("-2")):
                    continue
                if item_reg != v:
                    return False
            elif k == "cell":
                item_cell = str(item.get("cell", "")).lower()
                ns = str(item.get("namespace", "")).lower()
                if v in ["blue", "green"]:
                    if v == "blue" and (str(item.get("region", "")).lower() == "blue" or ns.endswith("-1")):
                        continue
                    if v == "green" and (str(item.get("region", "")).lower() == "green" or ns.endswith("-2")):
                        continue
                if item_cell != v and v not in ns:
                    return False
            elif k == "env":
                item_env = str(item.get("env", "")).lower()
                if item_env and item_env not in ["all", v]:
                    return False
            elif k == "cluster":
                item_cluster = str(item.get("cluster", "")).lower()
                if item_cluster and item_cluster not in ["all", v]:
                    return False
            elif k == "path":
                paths = []
                for rule in item.get("rules", []):
                    for match in rule.get("matches", []):
                        val = match.get("path", {}).get("value", "")
                        if val:
                            paths.append(val.lower())
                if not any(v in p or p in v for p in paths):
                    return False
            else:
                val = str(item.get(k, "")).lower()
                if v not in val:
                    return False
        return True

    categories = []
    if kind in ["all", "grant"]:
        categories.append(("ReferenceGrant", graph.reference_grants, gen._render_reference_grant))
    if kind in ["all", "route"]:
        categories.append(("HTTPRoute", graph.http_routes, gen._render_http_route))
    if kind in ["all", "gateway"]:
        categories.append(("Gateway", graph.gateways, gen._render_gateway))
    if kind in ["all", "service-defaults"]:
        categories.append(("ServiceDefaults", graph.service_defaults, gen._render_service_defaults))
    if kind in ["all", "proxy-defaults"]:
        categories.append(("ProxyDefaults", graph.proxy_defaults, gen._render_proxy_defaults))

    matched_manifests = []
    matched_data = []

    for cat_name, item_dict, render_fn in categories:
        for key, item in item_dict.items():
            if item_matches(item):
                matched_data.append(item)
                matched_manifests.append(render_fn(item).strip())

    if not matched_manifests:
        print(f"# No resources found matching kind='{kind}', filters={filters_raw}")
        return

    if output_fmt in ["yaml", "manifest"]:
        print("\n---\n".join(matched_manifests))
    elif output_fmt == "json":
        print_json(matched_data)
    else:
        print(f"\n[+] Found {len(matched_data)} resource(s):")
        for m in matched_data:
            print(f"  - {m.get('name') or m.get('service')} (Namespace: {m.get('namespace')})")
        print()


def handle_query_eval(args, db: MarkdownDB):
    output_fmt = getattr(args, "output", "yaml")
    expr = args.expr
    try:
        data = db.eval_expression(expr)
        if output_fmt in ["yaml", "manifest"]:
            print(yaml.dump(data, sort_keys=False).strip())
        else:
            print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"# Error evaluating expression '{expr}': {e}")


def handle_add_manifest(args):
    parser = ManifestParser()
    res = parser.parse_manifest_file(
        file_path=args.file,
        env=args.env,
        cluster=args.cluster,
        apg=args.apg,
        cell=args.cell,
        agw=args.agw,
        path=args.path,
        port=args.port,
    )
    print(f"\n[+] Successfully ingested manifest: {args.file}")
    for item in res["processed"]:
        print(f"  - Kind: {item.get('kind')} (Service/Name: {item.get('service') or item.get('name')})")
        print(f"    Region: {item.get('region')}, Cell: {item.get('cell')}, APG: {item.get('apg')}")
        if item.get("linked_agw"):
            print(f"    Linked to AGW: {item.get('linked_agw')} with path: {item.get('linked_path')}")

    from .sync_engine import SyncEngine
    sync_res = SyncEngine().sync_cue_to_dir()
    if sync_res["total_updated"] > 0:
        print(f"  [i] Synchronized {sync_res['total_updated']} file(s) to directory hierarchy.")
    print()


def handle_add_dim(args, dim_mgr: DimensionManager):
    dim_type = args.type.lower()
    if dim_type in ["env", "environment"]:
        res = dim_mgr.add_environment(args.name, peering_enabled=args.peering)
        print(f"[+] Added Environment: {res['environment']} (Peering: {res['peering_enabled']})")
    elif dim_type in ["apg", "application-group"]:
        res = dim_mgr.add_application_group(args.name)
        print(f"[+] Added Application Group: {res['application_group']}")
    elif dim_type == "cell":
        if not args.apg:
            print("[-] Error: --apg is required when adding a cell.")
            sys.exit(1)
        res = dim_mgr.add_cell(apg=args.apg, cell=args.name, description=args.desc or "")
        print(f"[+] Added Cell: {res['cell']} to APG: {res['apg']}")
    elif dim_type in ["ns", "namespace"]:
        if not args.apg or not args.cell:
            print("[-] Error: --apg and --cell are required when adding a namespace.")
            sys.exit(1)
        res = dim_mgr.add_namespace(name=args.name, apg=args.apg, cell=args.cell, region=args.region)
        print(f"[+] Added Namespace: {res['namespace']} (Region: {res['region']})")
    elif dim_type == "service":
        if not args.ns or not args.apg or not args.cell:
            print("[-] Error: --ns, --apg, and --cell are required when adding a service.")
            sys.exit(1)
        res = dim_mgr.add_service(
            name=args.name,
            namespace=args.ns,
            apg=args.apg,
            cell=args.cell,
            region=args.region or ("blue" if args.ns.endswith("-1") else "green"),
            version=args.version or "v1.0.0",
            port=args.port or 8080,
            protocol=args.protocol or "http",
        )
        print(f"[+] Added Service: {res['service']} (Region: {res['region']}, Version: {res['version']})")
    else:
        print(f"[-] Unsupported dimension type: {dim_type}")
        return

    from .sync_engine import SyncEngine
    sync_res = SyncEngine().sync_cue_to_dir()
    if sync_res["total_updated"] > 0:
        print(f"  [i] Synchronized {sync_res['total_updated']} file(s) to directory hierarchy.")
    print()



def handle_export(args):
    gen = ManifestGenerator()
    res = gen.export_all(target_dir=args.out, env_filter=args.env)
    print(f"\n[+] Exported {res['total_files']} manifest(s) to: {res['output_dir']}")
    print()


def handle_summary(graph: RelationalGraph):
    s = graph.get_summary()
    print("\n========================================================")
    print(" Configuration Management Dashboard Overview")
    print("========================================================")
    print(f" Environments         : {', '.join(s['environments'])}")
    print(f" Application Groups   : {', '.join(s['application_groups'])}")
    print(f" Total Namespaces     : {s['total_namespaces']}")
    print(f" Total Gateways (AGWs): {s['total_gateways']}")
    print(f" Total HTTPRoutes     : {s['total_http_routes']}")
    print(f" Total Services       : {s['total_services']}")
    print(f" ServiceDefaults      : {s['total_service_defaults']}")
    print(f" ProxyDefaults        : {s['total_proxy_defaults']}")
    print("========================================================\n")


def handle_sync(args):
    from .sync_engine import SyncEngine
    engine = SyncEngine()

    if args.check:
        res = engine.check_consistency()
        print("\n========================================================")
        print(" Bidirectional Sync & Consistency Audit Report")
        print("========================================================")
        print(f" Total Expected Manifests (Relations) : {res['stats']['total_expected_manifests']}")
        print(f" Total Discovered Manifests (Disk)    : {res['stats']['total_disk_manifests']}")

        if res["schema_errors"]:
            print("\n[-] Schema Validation Errors:")
            for e in res["schema_errors"]:
                print(f"    {e}")

        if res["missing_in_dir"]:
            print(f"\n[-] Missing Files in Directory ({len(res['missing_in_dir'])}):")
            for m in res["missing_in_dir"]:
                print(f"    • {m}")

        if res["missing_in_cue"]:
            print(f"\n[-] Orphaned / Unregistered Files ({len(res['missing_in_cue'])}):")
            for o in res["missing_in_cue"]:
                print(f"    • {o}")

        if res["content_drift"]:
            print(f"\n[-] Content Drift Detected ({len(res['content_drift'])}):")
            for d in res["content_drift"]:
                print(f"    • {d.get('file')}: {d.get('status') or d.get('error')}")

        if res["cross_dc_asymmetry"]:
            print(f"\n[-] Cross-DC Asymmetry Violations ({len(res['cross_dc_asymmetry'])}):")
            for a in res["cross_dc_asymmetry"]:
                print(f"    • [{a['env']}] {a['reason']}")
                print(f"      DCE: {a['dce_file']}")
                print(f"      DCW: {a['dcw_file']}")

        if res["is_synced"]:
            print("\n[+] Success: Markdown relations and Directory hierarchy are 100% synchronized and consistent!\n")
            sys.exit(0)
        else:
            print("\n[!] Discrepancies detected between Markdown relations and Directory hierarchy.\n")
            sys.exit(1)

    elif getattr(args, "to_md", False) or getattr(args, "to_cue", False):
        res = engine.sync_dir_to_cue()
        print(f"\n[+] Synchronized Directory -> Markdown relations: Processed {res['total_processed']} manifest(s) successfully.")
        for p in res["processed"]:
            print(f"    • Ingested {p.get('kind')} '{p.get('name')}' for {p.get('apg')}/{p.get('cell')} ({p.get('env')})")
        print()

    elif args.to_dir:
        res = engine.sync_cue_to_dir(env_filter=args.env, prune=args.prune)
        print(f"\n[+] Synchronized Relations -> Directory: Generated/Updated {res['total_updated']} file(s).")
        if res["pruned"]:
            print(f"    Pruned {res['total_pruned']} obsolete file(s).")
        print()

    else:
        # Default: Relations -> Directory
        res = engine.sync_cue_to_dir(env_filter=args.env, prune=args.prune)
        print(f"\n[+] Synchronized Relations -> Directory: Generated/Updated {res['total_updated']} file(s).")
        if res["pruned"]:
            print(f"    Pruned {res['total_pruned']} obsolete file(s).")
        print()


def main():

    parser = argparse.ArgumentParser(
        description="Manifest Management CLI for CUE, Consul Service Mesh & Gateway API"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: query
    query_parser = subparsers.add_parser("query", help="Query relations and configurations")
    query_subs = query_parser.add_subparsers(dest="query_target", required=True)

    # query path
    q_path = query_subs.add_parser("path", help="Find AGW and HTTPRoute for a url-path")
    q_path.add_argument("path", help="URL path (e.g. /v1/retail/orders/)")
    q_path.add_argument("-o", "--output", choices=["yaml", "manifest", "json", "text"], default="yaml", help="Output format (default: yaml manifest)")

    # query agw
    q_agw = query_subs.add_parser("agw", help="Query routes and services bonded to an AGW")
    q_agw.add_argument("name", help="AGW name (e.g. agw-ncbs-retail-blue)")
    q_agw.add_argument("-o", "--output", choices=["yaml", "manifest", "json", "text"], default="yaml", help="Output format (default: yaml manifest)")

    # query proxy-defaults
    q_pd = query_subs.add_parser("proxy-defaults", help="Query proxyDefaults for a cluster/cell/region")
    q_pd.add_argument("--env", required=True, help="Environment name (e.g. UAT)")
    q_pd.add_argument("--cluster", required=True, help="Cluster name (e.g. ocp53)")
    q_pd.add_argument("--cell", help="Cell name (e.g. retail)")
    q_pd.add_argument("--region", choices=["blue", "green"], help="Region (blue or green)")
    q_pd.add_argument("-o", "--output", choices=["yaml", "manifest", "json", "text"], default="yaml", help="Output format (default: yaml manifest)")

    # query grant
    q_grant = query_subs.add_parser("grant", help="Query ReferenceGrant configurations")
    q_grant.add_argument("--apg", help="Filter by APG (e.g. ncbs)")
    q_grant.add_argument("--cell", help="Filter by Cell (e.g. common, retail)")
    q_grant.add_argument("--region", choices=["blue", "green"], help="Filter by Region (blue, green)")
    q_grant.add_argument("--namespace", help="Filter by namespace")
    q_grant.add_argument("-o", "--output", choices=["yaml", "manifest", "json", "text"], default="yaml", help="Output format (default: yaml manifest)")

    # query find (LLM-driven dynamic key-value query)
    q_find = query_subs.add_parser("find", help="Dynamic query with arbitrary key=value filters (LLM-driven)")
    q_find.add_argument("filters", nargs="*", help="Dynamic filters (e.g. grant region=blue cell=common apg=ncbs)")
    q_find.add_argument("--kind", choices=["grant", "route", "gateway", "service-defaults", "proxy-defaults", "all"], default="all", help="Resource kind")
    q_find.add_argument("-o", "--output", choices=["yaml", "manifest", "json", "text"], default="yaml", help="Output format")

    # query eval (Direct CUE expression evaluation)
    q_eval = query_subs.add_parser("eval", help="Evaluate arbitrary CUE expression")
    q_eval.add_argument("expr", help="CUE expression (e.g. system.reference_grants)")
    q_eval.add_argument("-o", "--output", choices=["yaml", "manifest", "json", "text"], default="yaml", help="Output format")

    # Subcommand: add-manifest
    add_m = subparsers.add_parser("add-manifest", help="Ingest a YAML/JSON manifest (e.g. ServiceDefaults.yaml)")
    add_m.add_argument("file", help="Path to YAML/JSON manifest file")
    add_m.add_argument("--env", help="Target environment (optional)")
    add_m.add_argument("--cluster", help="Target cluster (optional, e.g. ocp53, ocp54)")
    add_m.add_argument("--apg", help="Target APG (e.g. ncbs)")
    add_m.add_argument("--cell", help="Target cell (e.g. common, retail)")
    add_m.add_argument("--agw", help="Target AGW to link route with")
    add_m.add_argument("--path", help="URL route path prefix")
    add_m.add_argument("--port", type=int, default=8080, help="Service target port")

    # Subcommand: add-dim
    add_d = subparsers.add_parser("add-dim", help="Add a new item to a dimension")
    add_d.add_argument("type", choices=["env", "apg", "cell", "ns", "service"], help="Dimension type")
    add_d.add_argument("name", help="Name of the item")
    add_d.add_argument("--apg", help="APG name")
    add_d.add_argument("--cell", help="Cell name")
    add_d.add_argument("--ns", help="Namespace name")
    add_d.add_argument("--region", choices=["blue", "green"], help="Region")
    add_d.add_argument("--version", default="v1.0.0", help="Service version")
    add_d.add_argument("--port", type=int, default=8080, help="Port")
    add_d.add_argument("--protocol", default="http", help="Protocol")
    add_d.add_argument("--peering", action="store_true", help="Enable peering for environment")
    add_d.add_argument("--desc", help="Description")

    # Subcommand: export
    exp = subparsers.add_parser("export", help="Compile and export GitOps YAML manifests")
    exp.add_argument("--env", help="Filter by environment (e.g. UAT, SIT, PROD)")
    exp.add_argument("--out", help="Output directory path (default: output/)")

    # Subcommand: sync
    sync_p = subparsers.add_parser("sync", help="Bidirectional synchronization between Markdown relations and hierarchical directory structure")
    sync_p.add_argument("--to-dir", action="store_true", help="Sync from Markdown relations to directory hierarchy")
    sync_p.add_argument("--to-md", "--to-cue", dest="to_md", action="store_true", help="Sync from directory hierarchy to Markdown relations")
    sync_p.add_argument("--check", action="store_true", help="Audit and verify consistency without making changes")
    sync_p.add_argument("--env", help="Filter by environment (optional)")
    sync_p.add_argument("--prune", action="store_true", help="Remove orphaned files in directory not present in relations")

    # Subcommand: summary
    subparsers.add_parser("summary", help="Show system dashboard overview")

    # Subcommand: vet
    subparsers.add_parser("vet", help="Validate Markdown relations schemas and integrity")

    args = parser.parse_args()

    db = MarkdownDB()

    if args.command == "vet":
        ok, out = db.vet()
        if ok:
            print("[+] All Markdown relations and definitions are valid!")
        else:
            print(f"[-] Validation failed:\n{out}")
            sys.exit(1)
        return

    if args.command == "summary":
        graph = RelationalGraph(db)
        handle_summary(graph)
        return

    if args.command == "sync":
        handle_sync(args)
        return

    if args.command == "query":
        graph = RelationalGraph(db)
        if args.query_target == "path":
            handle_query_path(args, graph)
        elif args.query_target == "agw":
            handle_query_agw(args, graph)
        elif args.query_target == "proxy-defaults":
            handle_query_proxy_defaults(args, graph)
        elif args.query_target == "grant":
            handle_query_grant(args, graph)
        elif args.query_target == "find":
            handle_query_find(args, graph)
        elif args.query_target == "eval":
            handle_query_eval(args, db)

    elif args.command == "add-manifest":
        handle_add_manifest(args)

    elif args.command == "add-dim":
        dim_mgr = DimensionManager()
        handle_add_dim(args, dim_mgr)

    elif args.command == "export":
        handle_export(args)



if __name__ == "__main__":
    main()
