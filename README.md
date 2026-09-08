# Manifest Management Project

A multi-dimensional configuration management system for Kubernetes (Gateway API) and Consul Service Mesh across multiple Environments, Data Centers, Clusters, Application Groups, Cells, and Blue/Green regions.

The project operates on a **Pure Agentic Zero-Python Architecture**: all configuration relationships, architectural invariants, queries, manifest ingestion, and GitOps deployments are governed 100% natively by Antigravity / Gemini via [GEMINI.md](GEMINI.md) and human-friendly GitHub Flavored Markdown (GFM) tables under `relations/`.

---

## 1. Directory Structure

```
manifest-management/
├── relations/                        # Markdown relational database
│   ├── environments.md               # Environment, cluster, DC topology
│   ├── application_groups.md         # Application groups and cells
│   ├── namespaces.md                 # Namespaces and blue/green regions
│   ├── services.md                   # Services, versions, and ports
│   ├── gateways.md                   # Application Gateways (AGW)
│   ├── http_routes.md                # HTTPRoutes and path bindings
│   ├── service_defaults.md           # Consul ServiceDefaults
│   ├── proxy_defaults.md             # Consul cluster-global ProxyDefaults
│   └── reference_grants.md           # Gateway API ReferenceGrants
├── ApplicationGroups/                # Direct GitOps deployment single source of truth
│   └── <Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/<Config-Items>/
├── raw/                              # Input manifests provided for ingestion
├── examples/                         # Reference manifests
├── GEMINI.md                         # Project Context, Architectural Invariants & Agent Operating Rules
└── .agents/
    └── skills/manifest-management/   # Pure agentic skill runbook (SKILL.md)
```

---

## 2. Autonomous Agent Interactions

You interact directly with Antigravity through natural language prompts. Antigravity reads and manages the Markdown tables and GitOps files directly:

### Reverse Path Lookup
> *"What are the httproutes for `/v1/retail/orders/` in prod?"*
- Antigravity scans `relations/http_routes.md`, cross-references `gateways.md` and `services.md`, and returns the exact YAML manifests with full dimensional values (Env, DC, Cluster, APG, Cell, Region, Namespace) and concrete file paths in `ApplicationGroups/`.

### AGW Inventory
> *"What routes and services are bonded to `agw-ncbs-retail-blue`?"*
- Antigravity analyzes the bonded HTTPRoutes, path prefixes, target backend services, and ports.

### Cluster ProxyDefaults
> *"Show ProxyDefaults for green cell in UAT ocp53"*
- Antigravity enforces the cluster-global singleton invariant (applies across all cells and regions) and returns `ApplicationGroups/<APG>/UAT/<Cell>/DCE/ocp53/proxydefaults/global.yaml`.

### Manifest Ingestion
> *"Ingest `raw/orders-route.yaml` for UAT retail"*
- Antigravity parses metadata, prompts for any ambiguous dimensions (preventing accidental default broadcasting), updates `relations/http_routes.md`, and generates the target manifest under `ApplicationGroups/` ensuring Cross-DC symmetry.

### Relational & GitOps Audit
> *"Audit configuration relations and directory consistency"*
- Antigravity verifies table referential integrity (port boundaries, Blue/Green `-1`/`-2` suffixes, DC values) and checks for drift or orphaned files against `ApplicationGroups/`.

---

## 3. Core Invariants

1. **ProxyDefaults Singleton**: Strictly 1 mesh-wide global `ProxyDefaults` (`name: global`) per Consul cluster.
2. **Cross-DC Symmetry**: Dual-cluster peered environments (e.g. DCE `ocp53` and DCW `ocp54` in UAT) have identical configurations in the same region.
3. **Blue/Green Suffixes**: Namespaces end with `-1` for Blue and `-2` for Green.
4. **Manifest-First Principle**: Queries always return concrete YAML manifests with full dimensional metadata and file paths.
5. **Strict Dimensional Scope**: The agent will never broadcast manifests across clusters or environments without explicit confirmation.
