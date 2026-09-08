# Manifest Management Project

A multi-dimensional configuration management system for Kubernetes (Gateway API) and Consul Service Mesh across multiple Environments, Data Centers, Clusters, Application Groups, Cells, and Blue/Green regions.

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
├── examples/                         # Reference manifests
├── tests/                            # Automated test suite
├── GEMINI.md                         # Project Context, Architectural Invariants & Agent Rules
└── .agents/
    └── skills/manifest-management/   # Management runner script and Python engine
```

---

## 2. Core CLI Commands

Use the canonical runner script located under `.agents/skills/manifest-management/scripts/manifest-mgr`:

```bash
RUNNER="./.agents/skills/manifest-management/scripts/manifest-mgr"

# Schema & relational validation
$RUNNER vet

# Dashboard overview
$RUNNER summary

# Bidirectional GitOps synchronization
$RUNNER sync --to-dir       # Sync Markdown relations into ApplicationGroups/ hierarchy
$RUNNER sync --to-md        # Ingest manual directory changes from ApplicationGroups/ into relations
$RUNNER sync --check        # Audit consistency, drift, and cross-DC symmetry

# Dynamic queries
$RUNNER query find route path=/v1/retail/orders/ env=prod
$RUNNER query proxy-defaults --env UAT --cluster ocp53
$RUNNER query grant --apg ncbs

# Dynamic dimension registration
$RUNNER add-dim env <NAME> [--peering]
$RUNNER add-dim apg <NAME>
$RUNNER add-dim cell <CELL> --apg <APG>
$RUNNER add-dim ns <NS> --apg <APG> --cell <CELL> --region <blue|green>
$RUNNER add-dim service <SVC> --ns <NS> --apg <APG> --cell <CELL>
```

---

## 3. Testing & Verification

Run automated tests using pytest:

```bash
python3 -m pytest tests/ -v
```
