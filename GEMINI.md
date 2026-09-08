# Gemini Project Context & Management Guide: ManifestManagementProject

This project is a multi-dimensional configuration management system for Kubernetes (Gateway API) and Consul Service Mesh across multiple Environments, Data Centers, Clusters, Application Groups, Cells, and Blue/Green regions.

When Gemini or Antigravity loads this workspace on any machine or laptop, it **MUST** adopt this context and follow the rules below.

---

## 1. Directory Structure & Layout Boundaries

* **Root Directory (Organized & Modular)**:
  * `cue/`: Parent directory containing the complete CUE configuration database:
    * `cue.mod/`: CUE module root (`manifest.management`).
    * `schema/`: CUE schemas (`topology.cue`, `gateway.cue`, `consul.cue`, `root.cue`).
    * `catalog/`: Active configuration database:
      * `apgs/`: Application Group definitions (`ncbs.cue`, `branch_connect.cue`).
      * `environments/`: Environment topologies (`envs.cue`: DEV, SIT, UAT, PT, PAT, PROD).
      * `extensions/`: Dynamically added dimensions and manifests (`custom.cue`).
      * `system.cue`: Unified configuration entrypoint.
  * `ApplicationGroups/`: Parent directory for all human-friendly configuration hierarchies:
    * `<Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/<Config-Items>/` (e.g., `ApplicationGroups/NCBS/uat/retail/DCE/ocp53/httproutes/`).
    * Acts as the unified GitOps single source of truth for deployment.
  * `raw/`: Raw input manifests provided by users (e.g., `ncbs-retail-orders-route-xxxx.yaml`).
  * `examples/`: Reference manifest examples (`ServiceDefaults_example.yaml`, `HTTPRoute_example.yaml`).
  * `tests/`: Pytest automated verification suite (`test_crud_workflows.py`, `test_sync_workflows.py`).
* **Customization & Skill Directory (`.agents/skills/manifest-management/`)**:
  * `SKILL.md`: Skill definition and workflow runbook.
  * `scripts/manifest-mgr`: The canonical CLI execution runner.
  * `scripts/py_engine/`: Python engine (Relational Graph, CUE client, parser, generator, dimension manager, sync engine).


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
   * Do NOT include unsolicited background explanations or test execution reports unless explicitly requested by the user.
5. **Strict Dimensional Scope & No Default Broadcasting**:
   * When ingesting, saving, or updating a configuration or manifest, **NEVER deploy or update it into all environments or all clusters by default** if the target environment or cluster is omitted or ambiguous.
   * Apply this exact strict principle to all configuration dimensions: **Environment (`env`)**, **Cluster (`cluster`)**, **Application Group (`apg`)**, **Cell (`cell`)**, and **Region (`region`)**.
   * When an environment contains multiple clusters (e.g., UAT with `ocp53` in DCE and `ocp54` in DCW, or PROD with `ocp71` in DCE and `ocp72` in DCW), **ALWAYS stop and prompt the user for confirmation** on whether it targets a specific cluster (`ocp53` vs `ocp54`) or both clusters before committing or syncing.
   * As the strict configuration manager, if ANY dimension is missing or not explicitly declared in labels, annotations, or user instructions, **ALWAYS stop and prompt the user for clarification** (e.g., asking which environment, which cluster, which application group, which cell, or which region) before committing or syncing.

6. **Query Failure Self-Healing & Test-Driven Remediation**:
   * If any query cannot be answered properly due to an actual system defect (e.g. missing resource definition, unhandled resource schema, or CUE bug):
     1. Automatically trigger the fixing process to resolve the root cause in the schema, catalog, or query engine.
     2. Add a respective automated test case in `tests/test_crud_workflows.py` replicating that exact scenario to prevent regression.
     3. If any domain requirements or unknown inputs are needed to complete the fix, always ask the user for details.
7. **LLM Query Construction & Immutable CLI**:
   * **Do NOT modify `cli.py`** to add one-off flags for ad-hoc queries.
   * The LLM translates user intent into dynamic queries using:
     - Generic query find: `$RUNNER query find [kind] [key=value ...]`
     - Direct CUE expression evaluation: `$RUNNER query eval '<expression>'`
     - Or direct evaluation via CUE/Python commands.
8. **Bidirectional CUE & Directory Synchronization**:
   * The human-friendly directory structure (`ApplicationGroups/<Application>/<Environment>/<Logical-Cell>/<DC>/<OCP-Cluster>/<Config-Items>/`) and CUE database must remain strictly unified at all times.
   * Manual modifications or new files in the directory hierarchy automatically sync to CUE (`$RUNNER sync --to-cue`).
   * Schema or dimension additions in CUE immediately update the directory hierarchy (`$RUNNER sync --to-dir`).
   * Drift, orphaned manifests, and Cross-DC asymmetry are continuously audited via `$RUNNER sync --check`.

---

## 3. Operational Workflows & CLI Commands

All operational tasks are performed through the skill runner script:

```bash
RUNNER="./.agents/skills/manifest-management/scripts/manifest-mgr"

# 1. Bidirectional Directory & CUE Synchronization
$RUNNER sync --to-dir       # Sync from CUE database to ApplicationGroups/ hierarchy
$RUNNER sync --to-cue       # Ingest manual directory changes into CUE
$RUNNER sync --check        # Audit consistency, drift, and cross-DC symmetry

# 2. Dynamic LLM-Driven Queries (No CLI modifications needed)
$RUNNER query find grant region=blue
$RUNNER query find route cell=retail
$RUNNER query find gateway apg=ncbs
$RUNNER query eval "system.reference_grants"

# 3. Reverse Path Lookup
$RUNNER query path "/v1/retail/orders/"

# 4. Cluster ProxyDefaults Query
$RUNNER query proxy-defaults --env UAT --cluster ocp53

# 5. AGW Inventory Query
$RUNNER query agw agw-ncbs-retail-blue

# 6. Gateway API ReferenceGrant Query
$RUNNER query grant --apg ncbs

# 7. Dashboard Summary
$RUNNER summary

# 8. Ingest New Manifest (ServiceDefaults, HTTPRoute, ReferenceGrant)
$RUNNER add-manifest raw/my-manifest.yml --apg <apg> --cell <cell> --env <env> --cluster <cluster>

# 9. Dynamically Add Dimension Items
$RUNNER add-dim env STG --peering
$RUNNER add-dim apg wealth-mgmt
$RUNNER add-dim cell portfolio --apg wealth-mgmt
$RUNNER add-dim ns portfolio-core-1 --apg wealth-mgmt --cell portfolio --region blue
$RUNNER add-dim service portfolio-calc --ns portfolio-core-1 --apg wealth-mgmt --cell portfolio --region blue

# 10. Validate CUE Schemas & Integrity
$RUNNER vet
```


---

## 4. Testing & Verification

Run tests anytime with `pytest`:
```bash
python3 -m pytest tests/ -v
```
All tests must pass 100% and leave the CUE database in a clean, idempotent state.
