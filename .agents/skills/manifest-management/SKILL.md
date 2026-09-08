---
name: manifest-management
description: Manage multi-dimensional Kubernetes and Consul Service Mesh configurations using pure Markdown relational tables and agentic reasoning. Supports reverse URL-path lookup to AGW/HTTPRoutes, AGW route/service inventory, ProxyDefaults inspection for specific clusters/cells, dynamic dimensional CRUD, and ingesting raw ServiceDefaults/HTTPRoutes.
---

# Multi-Dimensional Manifest & Configuration Management Skill

This skill provides an intelligent, schema-validated agentic workflow for managing multi-dimensional Kubernetes (Gateway API) and Consul Service Mesh configurations across Environments, Clusters/DCs, Application Groups, Cells, Blue/Green regions, and Namespaces without any external Python runner or scripts.

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

---

## Agent Operational Workflows

Antigravity operates directly on the Markdown relational database in `relations/*.md` and the deployment manifests under `ApplicationGroups/`.

### 1. READ / QUERY WORKFLOWS

#### A. Reverse Path Lookup
*User Prompt Example*: *"What are the httproutes for `/v1/retail/orders/` in prod?"*
1. Read `relations/http_routes.md` using `view_file`.
2. Find rows where `Path` matches or is a prefix of the target path.
3. Cross-reference `Parent Gateway` in `relations/gateways.md` and target service in `relations/services.md`.
4. Locate the concrete YAML manifest file under `ApplicationGroups/<Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/httproutes/`.
5. Return the manifest content along with complete dimensional attributes (Env, DC, Cluster, APG, Cell, Region, Namespace, File Path).

#### B. AGW Inventory Query
*User Prompt Example*: *"What routes and services are bonded to `agw-ncbs-retail-blue`?"*
1. Read `relations/gateways.md` to verify the AGW parameters.
2. Read `relations/http_routes.md` filtering rows where `Parent Gateway` equals the specified AGW.
3. Tally total bonded routes, path prefixes, unique accommodated backend services, and target ports.
4. Return an organized inventory breakdown.

#### C. Cluster ProxyDefaults Query
*User Prompt Example*: *"Show ProxyDefaults for green cell in UAT ocp53"*
1. Remind the user: `ProxyDefaults` in Consul Service Mesh is a mesh-wide global singleton (`name: global`) for the cluster, applying across all cells and regions.
2. Read `relations/proxy_defaults.md` for cluster `ocp53` in `UAT`.
3. Read and return the manifest file: `ApplicationGroups/<APG>/UAT/<Cell>/DCE/ocp53/proxydefaults/global.yaml`.

#### D. ReferenceGrant Query
*User Prompt Example*: *"What ReferenceGrants exist for APG ncbs?"*
1. Read `relations/reference_grants.md` filtering by APG.
2. Return matching YAML manifests and concrete file paths.

---

### 2. CREATE & INGEST WORKFLOWS

#### A. Ingesting Raw Manifests
*User Prompt Example*: *"Ingest `raw/ncbs-retail-orders-route-1.yaml` for UAT"*
1. Read the manifest using `view_file` and parse kind, name, namespace, and rules.
2. Determine region from namespace suffix (`-1` -> Blue, `-2` -> Green).
3. **Strict Dimensional Scope Check**: If target cluster or environment has multiple possibilities (e.g. UAT has `ocp53` in DCE and `ocp54` in DCW), prompt the user for confirmation before writing.
4. Append/update the appropriate row in `relations/http_routes.md` (or relevant relation table), preserving column formatting.
5. Generate the target YAML manifest and write it to:
   `ApplicationGroups/<Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/<Config-Items>/<name>.yaml`
6. Enforce Cross-DC symmetry if the environment is multi-cluster.

#### B. Adding New Dimensions
*User Prompt Example*: *"Add a new cell `portfolio` to APG `wealth-mgmt`"*
1. Read `relations/application_groups.md`.
2. Add a new row formatted with proper pipe separators and padding.
3. Save the file using `replace_file_content` or `write_to_file`.

---

### 3. AUDIT & CONSISTENCY WORKFLOWS

*User Prompt Example*: *"Audit configuration relations and directory consistency"*
1. Verify relational table integrity across `relations/*.md`:
   - Namespaces follow `-1` (blue) and `-2` (green) suffix rules.
   - Ports are between 1 and 65535.
   - Data Centers are `DCE` or `DCW`.
   - ProxyDefaults has strictly 1 entry per cluster.
2. Verify directory synchronization:
   - Walk `ApplicationGroups/` and ensure all files match entries in `relations/*.md`.
   - Report any drift, orphaned manifests, or Cross-DC asymmetry.
