# Gemini Project Context & Management Guide: ManifestManagementProject

This project is a multi-dimensional configuration management system for Kubernetes (Gateway API) and Consul Service Mesh across multiple Environments, Data Centers, Clusters, Application Groups, Cells, and Blue/Green regions.

The system is designed with a **Pure Agentic Zero-Python Architecture**: all relational topology, architectural invariants, validations, queries, manifest generation, and GitOps synchronizations are governed 100% natively by Antigravity / Gemini via this guide and the Markdown relational tables under `relations/`.

When Gemini or Antigravity loads this workspace on any machine or laptop, it **MUST** adopt this context and strictly adhere to the rules below.

---

## 1. Directory Structure & Layout Boundaries

* **Root Directory (Organized & Modular)**:
  * `relations/`: GitHub Flavored Markdown (GFM) tables maintaining multi-dimensional configuration relationships:
    * `environments.md`: Environments, clusters, DCs, and Consul peering topologies.
    * `application_groups.md`: Application groups and logical cells.
    * `namespaces.md`: Namespaces, blue/green regions, and APG/cell bindings.
    * `services.md`: Services, ports, and version definitions.
    * `gateways.md`: Application Gateways (AGW), listeners, and hostnames.
    * `http_routes.md`: HTTPRoutes, path bindings, match types, and targets.
    * `service_defaults.md`: Consul ServiceDefaults configurations.
    * `proxy_defaults.md`: Consul cluster-global ProxyDefaults configurations.
    * `reference_grants.md`: Gateway API cross-namespace ReferenceGrants.
  * `ApplicationGroups/`: Parent directory for all human-friendly configuration hierarchies:
    * `<Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/<Config-Items>/` (e.g., `ApplicationGroups/NCBS/uat/retail/DCE/ocp53/httproutes/`).
    * Acts as the unified GitOps single source of truth for deployment.
  * `raw/`: Raw input manifests provided by users (e.g., `ncbs-retail-orders-route-xxxx.yaml`).
  * `examples/`: Reference manifest examples (`ServiceDefaults_example.yaml`, `HTTPRoute_example.yaml`).
* **Customization & Skill Directory (`.agents/skills/manifest-management/`)**:
  * `SKILL.md`: Pure agentic skill definition and operational workflows.

---

## 2. Core Architectural Invariants

1. **Cluster-Global ProxyDefaults**:
   * In Consul Service Mesh, `ProxyDefaults` is a **mesh-wide global singleton** (`name: global`).
   * Each Consul cluster (1-to-1 with an OCP cluster for an APG) has **strictly 1 `ProxyDefaults`**.
   * It applies across all cells (Retail, PayLah, Common) and all regions (Blue, Green). Cell-specific customizations belong in `ServiceDefaults`.
2. **Cross-DC Symmetry**:
   * For dual-cluster peered environments (e.g. UAT with DCE `ocp53` and DCW `ocp54`, or PROD with DCE `ocp71` and DCW `ocp72`), the service and route manifests in the same region are **strictly identical**.
3. **Blue/Green Region Independence**:
   * Namespaces use suffix `-1` for Blue and `-2` for Green (e.g. `gpi-retail-1`, `cb-core-ss-retail-2`).
   * Deployment topologies, service versions, and routes in Blue and Green can be independent.
4. **Manifest-First Principle with Complete Dimensional Context**:
   * When queried for routes, gateways, proxy defaults, or reference grants, **directly return the actual YAML manifests along with the exact values of all relevant dimensions and file paths**:
     - **File Path**: The concrete file path under `ApplicationGroups/<Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/<Config-Items>/`
     - **Dimensions**:
       - **Environment (`env`)**: e.g. `PROD`, `UAT`, `DEV`
       - **Data Center (`dc`)**: e.g. `DCE`, `DCW`
       - **Cluster (`cluster`)**: e.g. `ocp71`, `ocp72`
       - **Application Group (`apg`)**: e.g. `NCBS`, `branch-connect`
       - **Cell (`cell`)**: e.g. `retail`, `common`
       - **Region (`region`)**: e.g. `blue`, `green`
       - **Namespace (`namespace`)**: e.g. `gpi-retail-1`
   * Clearly present each file with its associated dimensional values so the user can immediately see where each configuration applies.
   * Do NOT include unsolicited background explanations or verbose test logs unless explicitly requested by the user.
5. **Strict Dimensional Scope & No Default Broadcasting**:
   * When ingesting, saving, or updating a configuration or manifest, **NEVER deploy or update it into all environments or all clusters by default** if the target environment or cluster is omitted or ambiguous.
   * Apply this exact strict principle to all configuration dimensions: **Environment (`env`)**, **Cluster (`cluster`)**, **Application Group (`apg`)**, **Cell (`cell`)**, and **Region (`region`)**.
   * When an environment contains multiple clusters (e.g., UAT with `ocp53` in DCE and `ocp54` in DCW, or PROD with `ocp71` in DCE and `ocp72` in DCW), **ALWAYS stop and prompt the user for confirmation** on whether it targets a specific cluster (`ocp53` vs `ocp54`) or both clusters before committing or syncing.
   * As the strict configuration manager, if ANY dimension is missing or not explicitly declared in labels, annotations, or user instructions, **ALWAYS stop and prompt the user for clarification** (e.g., asking which environment, which cluster, which application group, which cell, or which region) before committing or syncing.
6. **Bidirectional Markdown & Directory Consistency**:
   * The human-friendly directory structure (`ApplicationGroups/<Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/<Config-Items>/`) and Markdown relations database (`relations/*.md`) must remain strictly unified at all times.
   * Any change in Markdown tables must immediately be reflected in `ApplicationGroups/`.
   * Any change in `ApplicationGroups/` manifests must be ingested back into `relations/*.md`.

---

## 3. Autonomous Agent Operational Protocols

Antigravity executes all operations directly by inspecting, modifying, or creating files across `relations/` and `ApplicationGroups/`:

### A. Query Execution Protocol
1. **Reverse Path Lookup (e.g., "What are the routes for `/v1/retail/orders/` in PROD?")**:
   - Read [relations/http_routes.md](file:///Users/lorenzolou/Downloads/ManifestManagementProject/relations/http_routes.md) to find rows matching the path prefix.
   - Match parent gateway in [relations/gateways.md](file:///Users/lorenzolou/Downloads/ManifestManagementProject/relations/gateways.md) and targets in [relations/services.md](file:///Users/lorenzolou/Downloads/ManifestManagementProject/relations/services.md).
   - Filter by requested dimensions (e.g. `env=PROD`, namespace).
   - Return the concrete YAML files located in `ApplicationGroups/` along with complete dimensional metadata (Env, DC, Cluster, APG, Cell, Region, Namespace, File Path).
2. **AGW Inventory Query (e.g., "What is bonded to `agw-ncbs-retail-blue`?")**:
   - Read [relations/gateways.md](file:///Users/lorenzolou/Downloads/ManifestManagementProject/relations/gateways.md) for the AGW definition.
   - Scan [relations/http_routes.md](file:///Users/lorenzolou/Downloads/ManifestManagementProject/relations/http_routes.md) for all routes having `Parent Gateway == <agw_name>`.
   - Tally total bonded routes, path prefixes, accommodated backend services, and target ports.
3. **ProxyDefaults Query (e.g., "Show ProxyDefaults for green cell in UAT ocp53")**:
   - Read [relations/proxy_defaults.md](file:///Users/lorenzolou/Downloads/ManifestManagementProject/relations/proxy_defaults.md) matching `Environment == UAT` and `Cluster == ocp53`.
   - Remind the user of Invariant 1: `ProxyDefaults` is cluster-global (applies to all cells and regions in that cluster).
   - Return the YAML manifest located at `ApplicationGroups/<APG>/UAT/<Cell>/DCE/ocp53/proxydefaults/global.yaml`.
4. **ReferenceGrant Query**:
   - Read [relations/reference_grants.md](file:///Users/lorenzolou/Downloads/ManifestManagementProject/relations/reference_grants.md), filter by APG, cell, or namespace, and return the manifests.

### B. Ingesting & Creating Manifests Protocol
When a raw manifest is provided:
1. Parse the document `kind` (`HTTPRoute`, `ServiceDefaults`, `ProxyDefaults`, `ReferenceGrant`, `Gateway`).
2. Extract name, namespace, and configuration specs.
3. Enforce namespace suffix invariant (`-1` -> Blue, `-2` -> Green).
4. Verify dimensional scoping:
   - Check if `env`, `cluster`, `apg`, `cell`, or `region` is clear.
   - **If ambiguous, stop and prompt Master for confirmation** (Invariant 5).
5. Append or update the corresponding row in the appropriate table under `relations/*.md`, keeping markdown column alignment clean.
6. Write the concrete manifest file into the appropriate GitOps hierarchy:
   `ApplicationGroups/<Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/<Config-Items>/<name>.yaml`
   - For environments with dual clusters (e.g., UAT `ocp53` and `ocp54`, or PROD `ocp71` and `ocp72`), enforce Invariant 2 (Cross-DC symmetry).

### C. Dimensional CRUD Protocol
When Master requests adding or modifying dimensions:
1. **Add Environment**: Append row to [relations/environments.md](file:///Users/lorenzolou/Downloads/ManifestManagementProject/relations/environments.md).
2. **Add Application Group**: Append row to [relations/application_groups.md](file:///Users/lorenzolou/Downloads/ManifestManagementProject/relations/application_groups.md).
3. **Add Cell**: Append cell to [relations/application_groups.md](file:///Users/lorenzolou/Downloads/ManifestManagementProject/relations/application_groups.md).
4. **Add Namespace**: Append row to [relations/namespaces.md](file:///Users/lorenzolou/Downloads/ManifestManagementProject/relations/namespaces.md) ensuring `-1` for Blue and `-2` for Green.
5. **Add Service / Gateway / Route**: Append row to respective markdown tables.
6. Automatically render/generate the corresponding YAML manifests in `ApplicationGroups/`.

### D. Audit & Referential Integrity Protocol
When requested to audit, vet, or verify consistency:
1. **Table Schema & Integrity Checks**:
   - Check all Data Centers are either `DCE` or `DCW`.
   - Check all Blue namespaces end with `-1` and Green end with `-2`.
   - Check all ports are between `1` and `65535`.
   - Check all route paths start with `/`.
   - Check foreign keys: each route's `Parent Gateway` exists in `gateways.md`, each service's `Namespace` exists in `namespaces.md`.
   - Check `ProxyDefaults` singleton: strictly 1 `global` entry per cluster.
2. **Directory & Manifest Sync Audit**:
   - Verify every row in `relations/` has its corresponding YAML file in `ApplicationGroups/`.
   - Verify there are no orphaned files in `ApplicationGroups/` not registered in `relations/`.
   - Verify Cross-DC symmetry: manifests in DCE and DCW for the same environment and region must have identical content.
