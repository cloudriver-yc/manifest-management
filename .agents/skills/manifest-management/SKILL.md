---
name: manifest-management
description: Manage multi-dimensional Kubernetes and Consul Service Mesh configurations using Markdown relational tables and Python. Supports reverse URL-path lookup to AGW/HTTPRoutes, AGW route/service inventory, ProxyDefaults inspection for specific clusters/cells, dynamic dimensional CRUD, and importing raw ServiceDefaults/HTTPRoutes.
---

# Multi-Dimensional Manifest & Configuration Management Skill

This skill provides an intelligent, schema-validated workflow for managing multi-dimensional Kubernetes (Gateway API) and Consul Service Mesh configurations across Environments, Clusters/DCs, Application Groups, Cells, Blue/Green regions, and Namespaces.

## System Topology & Dimensions

1. **Environments (`env`)**: `DEV`, `SIT`, `UAT`, `PT`, `PAT`, `PROD` (Extensible).
   - `SIT`: 1 cluster in 1 DC (`ocp51` in `DCE`).
   - `UAT`: Dual clusters across DCs with active Consul peering (`ocp53` in `DCE`, `ocp54` in `DCW`).
   - `PROD`: Dual clusters across DCs with active Consul peering (`ocp71` in `DCE`, `ocp72` in `DCW`).
2. **Application Groups (`apg`)**: `ncbs`, `branch-connect`, etc.
3. **Logical Cells (`cell`)**: E.g., `retail`, `paylah`, `common`, `teller`, `branch-ops`.
4. **Logical Regions (`region`)**:
   - `blue`: Identified by `-1` namespace suffix (e.g. `gpi-retail-1`, `cbcoresg-com-1`).
   - `green`: Identified by `-2` namespace suffix (e.g. `gpi-retail-2`, `cb-core-ss-retail-2`).
   - *Note: Services, versions, and deployment topologies in Blue and Green can be independent.*
5. **Cross-DC Symmetry**: For any environment, the same region across DCE and DCW clusters has identical configuration automatically.

## Output & Interaction Policy

- **Manifest-First Principle with Complete Dimensional Context**: When querying or retrieving configurations (HTTPRoutes, ProxyDefaults, Gateways, ReferenceGrants, ServiceDefaults), **return the actual YAML/JSON manifests along with the exact values of all relevant dimensions** (Environment, Data Center, Cluster, Application Group, Cell, Region, Namespace) and their concrete file paths under `ApplicationGroups/`.
- **Strict Dimensional Scope & No Default Broadcasting**: When saving, updating, or ingesting a manifest, **NEVER deploy or update it into all environments or all clusters by default** if the target environment or cluster is omitted or ambiguous. Apply this exact strict principle to all dimensions (**Environment**, **Cluster**, **Application Group**, **Cell**, **Region**). When an environment contains multiple clusters (e.g., UAT with `ocp53` in DCE and `ocp54` in DCW, or PROD with `ocp71` in DCE and `ocp72` in DCW), **ALWAYS stop and prompt the user for confirmation** on whether it targets a specific cluster (`ocp53` vs `ocp54`) or both clusters before applying or syncing. If any dimension is missing or unclear, **always prompt the user** for details instead of making assumptions.

- **Query Failure Self-Healing & Test-Driven Remediation**: If any query cannot be answered properly (e.g. unhandled query type, schema gap, parsing bug, or missing resource representation):
  1. Trigger the fixing process immediately to resolve the underlying issue in `relations/*.md`, the schema validator, or `py_engine/`.
  2. Add a dedicated automated test case in `tests/test_framework_integrity.py` replicating the exact query failure to prevent regressions.
  3. If domain knowledge or unknown configuration parameters are needed, always ask the user for details.
- If a queried item is not found, output a clear comment `# Not found: <reason>` followed by the minimal template to register it.

---

## Core Operational Workflows (CRUD)

All operations are executed via the CLI runner located in the workspace: `./.agents/skills/manifest-management/scripts/manifest-mgr <command>`

### 1. READ / QUERY

#### A. Dynamic LLM Query Construction (Recommended for Ad-Hoc Inquiries)
The LLM directly translates natural language into dynamic query filters without needing any code changes to `cli.py`:
```bash
# Find any resource matching arbitrary key-value pairs or text
./.agents/skills/manifest-management/scripts/manifest-mgr query find grant region=blue
./.agents/skills/manifest-management/scripts/manifest-mgr query find route cell=retail
./.agents/skills/manifest-management/scripts/manifest-mgr query find gateway apg=ncbs

# Evaluate any relation expression directly
./.agents/skills/manifest-management/scripts/manifest-mgr query eval "reference_grants"
```

#### B. Reverse Lookup: Find AGW and Route for a URL Path
Quickly identify which AGW and HTTPRoute accommodates a path like `/v1/retail/orders/` or `/v1/xxxxx/yyyy/`:
```bash
./.agents/skills/manifest-management/scripts/manifest-mgr query path "/v1/retail/orders/"
```
**Output provides**: Matched route name, parent AGW name, namespace, APG, cell, region, match type, and backend service targets.

#### C. AGW Inventory: Count Bonded Routes and Services
Inspect an AGW to see all bonded HTTPRoutes and accommodated services:
```bash
./.agents/skills/manifest-management/scripts/manifest-mgr query agw agw-ncbs-retail-blue
```
**Output provides**: Total count of bonded HTTPRoutes, list of routes with path prefixes, total unique accommodated services, and backend port/namespace bindings.

#### D. Cluster ProxyDefaults Inspection
In Consul Service Mesh, `ProxyDefaults` is a mesh-wide global configuration (strictly 1 per Consul cluster) that applies across all cells (Retail, PayLah, Common) and regions (Blue, Green). Inspect the active cluster-global defaults via:
```bash
./.agents/skills/manifest-management/scripts/manifest-mgr query proxy-defaults --env UAT --cluster ocp53
```
*(If `--cell` or `--region` is supplied, the tool will explain that ProxyDefaults is cluster-global and return the cluster's active `global` configuration).*

#### E. ReferenceGrant Inspection
Query active Gateway API `ReferenceGrant` configurations for cross-namespace routing permissions:
```bash
./.agents/skills/manifest-management/scripts/manifest-mgr query grant --apg ncbs
```

#### F. System Summary & Metrics
Get a bird's-eye view of all registered environments, APGs, gateways, routes, and services:
```bash
./.agents/skills/manifest-management/scripts/manifest-mgr summary
```

---

## 2. CREATE

#### A. Ingest a Manifest (`ServiceDefaults.yaml` or `HTTPRoute.yaml`)
Automatically parses metadata, detects region from namespace suffix (`-1` -> Blue, `-2` -> Green), derives APG and Cell, binds to parent AGW, and registers routes:
```bash
./.agents/skills/manifest-management/scripts/manifest-mgr add-manifest examples/ServiceDefaults_example.yaml --apg ncbs --cell common --agw agw-ncbs-common-blue --path /v1/common/payment/
```

#### B. Dynamically Add New Dimensions
- **Add a new Environment**:
  ```bash
  ./.agents/skills/manifest-management/scripts/manifest-mgr add-dim env STG --peering
  ```
- **Add a new Application Group (APG)**:
  ```bash
  ./.agents/skills/manifest-management/scripts/manifest-mgr add-dim apg wealth-mgmt
  ```
- **Add a new Logical Cell**:
  ```bash
  ./.agents/skills/manifest-management/scripts/manifest-mgr add-dim cell portfolio --apg wealth-mgmt --desc "Portfolio Cell"
  ```
- **Add a new Namespace**:
  ```bash
  ./.agents/skills/manifest-management/scripts/manifest-mgr add-dim ns portfolio-core-1 --apg wealth-mgmt --cell portfolio --region blue
  ```
- **Add a new Service**:
  ```bash
  ./.agents/skills/manifest-management/scripts/manifest-mgr add-dim service portfolio-calc --ns portfolio-core-1 --apg wealth-mgmt --cell portfolio --region blue --version v1.0.0 --port 8080
  ```

---

## 3. UPDATE

To update routes or configurations:
- Re-run `add-manifest` with updated attributes or modify Markdown entries directly in `relations/*.md`.
- Verify Markdown correctness:
  ```bash
  ./.agents/skills/manifest-management/scripts/manifest-mgr vet
  ```

---

## 4. DELETE

Decommission an item by removing its row from the appropriate table in `relations/*.md` or using Python DimensionManager:
```python
from py_engine.dimension_mgr import DimensionManager
dm = DimensionManager()
dm.delete_item("services", "serviceA-blue")
```

---

## 5. GITOPS DIRECTORY SYNCHRONIZATION

Maintains continuous bidirectional synchronization between the Markdown relational database (`relations/`) and the human-friendly GitOps directory structure under `ApplicationGroups/`:
`ApplicationGroups/<Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/<Config-Items>/`

GitOps engines (e.g., ArgoCD / Flux) point directly to `ApplicationGroups/`, which acts as the single source of truth for cluster deployments:

```bash
# 1. Sync Markdown state into ApplicationGroups/ directory hierarchy
./.agents/skills/manifest-management/scripts/manifest-mgr sync --to-dir

# 2. Ingest manual directory changes/files from ApplicationGroups/ into Markdown relations
./.agents/skills/manifest-management/scripts/manifest-mgr sync --to-md

# 3. Audit consistency, drift, missing files, and cross-DC symmetry
./.agents/skills/manifest-management/scripts/manifest-mgr sync --check

# 4. Optional: compile and export to a specific target directory
./.agents/skills/manifest-management/scripts/manifest-mgr export --env UAT --out /path/to/dir
```

