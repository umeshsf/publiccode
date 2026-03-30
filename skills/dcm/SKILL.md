---
name: dcm-cicd-pipeline
description: "Set up a production-ready CI/CD pipeline for Snowflake DCM Projects with GitHub Actions. Use when: DCM CI/CD, DCM pipeline, DCM GitHub Actions, automate DCM deployment, DCM plan on PR, DCM deploy on merge, multi-environment DCM, DCM service user, DCM key-pair auth, DCM Git integration. Triggers: dcm cicd, dcm pipeline, dcm github, automate dcm, dcm ci cd, dcm deploy automation, dcm pr plan."
---

# DCM CI/CD Pipeline

Set up automated PLAN-on-PR and DEPLOY-on-merge workflows for Snowflake DCM Projects using GitHub Actions. Uses `snow dcm` CLI commands with the `-x` flag for temporary connections from environment variables.

Based on the official [Snowflake-Labs/snowflake_dcm_projects](https://github.com/Snowflake-Labs/snowflake_dcm_projects) repo, [DCM Projects documentation](https://docs.snowflake.com/en/user-guide/dcm-projects/dcm-projects-files), and community patterns.

## When to Use

- User wants to automate DCM deployments with GitHub Actions
- User wants PLAN output posted as PR comments for review
- User wants gated PROD deployments with manual approval
- User needs service user auth (PAT or key-pair) for CI/CD
- User wants data drop detection safety gates
- User wants a complete multi-environment DCM setup from scratch

## Prerequisites

- Snowflake account with ACCOUNTADMIN access (initial setup only)
- GitHub repo with Actions enabled
- Snowflake CLI v3.16+ (`snow dcm --help` to verify)
- The built-in `dcm` skill handles DCM project creation/modification — this skill handles the CI/CD automation layer on top

## Workflow

### Step 1: Gather Requirements

**Ask** the user:

1. **GitHub repo URL** — where the DCM project lives
2. **Target names** — e.g., `DCM_DEV`, `DCM_STAGE`, `DCM_PROD_US` (these become GitHub environment names)
3. **DCM project FQNs** — e.g., `DCM_DEMO.PROJECTS.DCM_PROJECT_DEV`
4. **Owner role per target** — e.g., `DCM_DEVELOPER` for dev, `DCM_PROD_DEPLOYER` for prod
5. **Auth method** — Password/PAT (simpler) or key-pair (more secure)
6. **DCM project path** — relative path in repo to manifest.yml (e.g., `Quickstarts/DCM_Project_Quickstart_1/`)

**⚠️ STOPPING POINT**: Confirm all values before proceeding.

### Step 2: Run Snowflake Setup

**Load** `references/setup-guide.md` for the full SQL setup.

Execute in order:

1. **Create deployer role(s)** with required grants
2. **Create parent databases** (DCM cannot manage its own parent DB)
3. **Create DCM project objects** — or let workflows auto-create with `snow dcm create --if-not-exists -x`
4. **Create service user** — TYPE=SERVICE with PAT or key-pair auth

**Key commands:**
```sql
USE ROLE ACCOUNTADMIN;
CREATE ROLE IF NOT EXISTS DCM_DEVELOPER;
GRANT CREATE DATABASE ON ACCOUNT TO ROLE DCM_DEVELOPER;
GRANT CREATE WAREHOUSE ON ACCOUNT TO ROLE DCM_DEVELOPER;
GRANT CREATE ROLE ON ACCOUNT TO ROLE DCM_DEVELOPER;

USE ROLE DCM_DEVELOPER;
CREATE DATABASE IF NOT EXISTS DCM_DEMO;
CREATE SCHEMA IF NOT EXISTS DCM_DEMO.PROJECTS;
CREATE DCM PROJECT IF NOT EXISTS DCM_DEMO.PROJECTS.DCM_PROJECT_DEV;
```

**For key-pair auth:**
```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out dcm_cicd_rsa_key.p8 -nocrypt
openssl rsa -in dcm_cicd_rsa_key.p8 -pubout -out dcm_cicd_rsa_key.pub
```

**⚠️ STOPPING POINT**: Verify Snowflake objects created successfully.

### Step 3: Create manifest.yml

Use `snow init <project_name> --template DCM_PROJECT` to scaffold, then customize.

The manifest maps target names to accounts, project objects, and templating configs:

```yaml
manifest_version: 2
type: DCM_PROJECT

default_target: DCM_DEV

targets:
  DCM_DEV:
    account_identifier: MYORG-MY_DEV_ACCOUNT
    project_name: DCM_DEMO.PROJECTS.DCM_PROJECT_DEV
    project_owner: DCM_DEVELOPER
    templating_config: DEV

  DCM_STAGE:
    account_identifier: MYORG-MY_STAGE_ACCOUNT
    project_name: DCM_DEMO.PROJECTS.DCM_PROJECT_STG
    project_owner: DCM_STAGE_DEPLOYER
    templating_config: STAGE

  DCM_PROD_US:
    account_identifier: MYORG-MY_PROD_ACCOUNT
    project_name: DCM_DEMO.PROJECTS.DCM_PROJECT_PROD
    project_owner: DCM_PROD_DEPLOYER
    templating_config: PROD

templating:
  defaults:
    user: "GITHUB_ACTIONS_SERVICE_USER"
    wh_size: "X-SMALL"
  configurations:
    DEV:
      env_suffix: "_DEV"
    STAGE:
      env_suffix: "_STG"
    PROD:
      env_suffix: ""
      wh_size: "LARGE"
```

**Important**: `account_identifier` uses **org-account** format (e.g., `MYORG-MYACCOUNT`). Target names become GitHub environment names.

### Step 4: Write Definition Files

Create `sources/definitions/` with DEFINE statements and Jinja templating. DCM auto-discovers all `.sql` files in this directory. Macros go in `sources/macros/`.

**Standard folder structure:**
```
my_dcm_project/
├── manifest.yml
├── sources/
│   ├── definitions/
│   │   ├── infrastructure.sql
│   │   ├── roles.sql
│   │   └── grants.sql
│   └── macros/
│       └── global_macros.sql
├── SQL_post_scripts/     (optional post-deploy scripts)
└── out/                  (auto-generated, add to .gitignore)
```

**Pattern:**
```sql
DEFINE SCHEMA DCM_DEMO{{ env_suffix }}.RAW;
DEFINE TABLE DCM_DEMO{{ env_suffix }}.RAW.MY_TABLE (
    ID VARCHAR NOT NULL,
    NAME VARCHAR,
    _LOADED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
DEFINE ROLE AR{{ env_suffix }}_RAW_READ;
GRANT USAGE ON DATABASE DCM_DEMO{{ env_suffix }} TO ROLE AR{{ env_suffix }}_RAW_READ;
```

Definition files can ONLY contain DEFINE, GRANT, or ATTACH statements. If user already has definition files, skip this step.

### Step 5: Set Up GitHub Secrets, Variables & Environments

**Load** `references/github-workflows.md` for full details.

**Repository Variables (Settings → Secrets → Actions → Variables):**

| Variable | Value | Purpose |
|----------|-------|---------|
| `DCM_PROJECT_PATH` | `path/to/project/` (trailing slash!) | Locates manifest.yml in repo |
| `SNOWFLAKE_USER` | Service user name | Shared across environments |

**Repository Secrets (Settings → Secrets → Actions):**

| Auth Method | Secret | Value |
|-------------|--------|-------|
| **PAT (default)** | `DEPLOYER_PAT` | Programmatic access token |
| **Key-pair** | `SNOWFLAKE_PRIVATE_KEY_RAW` | Full PEM private key content |

**GitHub Environments (Settings → Environments):**
- Create one environment per manifest target (e.g., `DCM_STAGE`, `DCM_PROD_US`)
- Add **Required reviewers** on production environments
- Environment names MUST match manifest target names exactly

**⚠️ STOPPING POINT**: Confirm secrets, variables, and environments are configured.

### Step 6: Create GitHub Actions Workflows

**Load** `references/github-workflows.md` for complete YAML templates based on the official Snowflake-Labs repo.

The official pattern uses **4 workflows** in `.github/workflows/`:

| # | Workflow | Trigger | Purpose |
|---|---------|---------|---------|
| 1 | `DCM_1_Test_Connections.yml` | Manual | Validates connectivity + role match for all targets |
| 2 | `DCM_2_Test_PR_to_main.yml` | PR to `main` | PLAN against STAGE & PROD in parallel, posts PR comment |
| 3 | `DCM_3_Deploy_to_Stage_and_Prod.yml` | Push to `main` | Full pipeline: Plan → Drop Detection → Deploy → Post Scripts → Refresh DTs → Test Expectations |
| 4 | `DCM_4_Test_STAGE_Expectations.yml` | Manual | Ad-hoc data quality testing on STAGE |

**Key patterns from official workflows:**
- `yq` parses manifest.yml to extract account/role/project dynamically
- `snow dcm create --target <name> --if-not-exists -x` auto-creates project objects
- `snow dcm plan --target <name> --save-output -x` with `out/plan/plan_result.json` parsing
- `snow dcm deploy --target <name> -x` for deployment
- Data Drop Detection: blocks deploy if plan contains DROP on DATABASE/SCHEMA/TABLE/STAGE
- `-x` flag: temporary connection from `SNOWFLAKE_*` env vars (no config.toml needed)

### Step 7: Test the Pipeline

1. Run Workflow 1 (Test Connections) manually to validate setup
2. Push workflow files to `main` first (required for trigger recognition)
3. Create a feature branch with a small change
4. Open a PR — verify PLAN runs and posts comment (Workflow 2)
5. Merge — verify STAGE deploys, then PROD with approval gate (Workflow 3)

**Verification:**
```bash
snow dcm describe --target DCM_DEV -x
snow dcm list --target DCM_DEV -x
```

## Stopping Points

- ✋ After Step 1: Confirm target names, project FQNs, auth method
- ✋ After Step 2: Verify Snowflake objects created
- ✋ After Step 5: Confirm GitHub secrets, variables, and environments
- ✋ After Step 7: Verify end-to-end pipeline works

## Output

A fully automated CI/CD pipeline with:
- PLAN-on-PR with changeset summary posted as PR comment
- Data Drop Detection safety gate (blocks DROP on data objects)
- Sequential deployment: STAGE first, then PROD with approval gate
- Post-deploy scripts, Dynamic Table refresh, and Data Quality Expectations testing
- Full traceability via GitHub step summaries and artifacts

## Troubleshooting

**`Resource not accessible by integration`** on PR comment:
- Repo → Settings → Actions → General → Workflow permissions → Read and write

**Connection fails in workflow:**
- Run Workflow 1 (Test Connections) to diagnose
- Verify environment names match manifest target names exactly
- Check role match: connection role must equal manifest `project_owner`

**`Private key provided is not in PKCS#8 format`:**
- Key must start with `BEGIN PRIVATE KEY`, not `BEGIN RSA PRIVATE KEY`

**Workflows don't trigger on PR:**
- Workflow YAML files must exist on `main` branch first
- Check `paths` filter matches your project location

**Plan shows unexpected DROP operations:**
- Data Drop Detection blocks this automatically
- Review plan output in `out/plan/plan_result.json`

**DCM cannot manage parent database error:**
- Create parent databases in setup, not in DEFINE statements

## References

- `references/setup-guide.md` — Complete Snowflake setup SQL
- `references/github-workflows.md` — GitHub Actions YAML templates (based on official repo)
- `references/gotchas.md` — Common pitfalls and fixes
- Official repo: https://github.com/Snowflake-Labs/snowflake_dcm_projects
- DCM docs: https://docs.snowflake.com/en/user-guide/dcm-projects/dcm-projects-files
- Blog: https://prajwal-ns.github.io/prajwal.xyz/posts/Building-a-Production-Ready-CICD-Pipeline-for-Snowflake-Using-DCM-Projects--and--GitHub-Actions
