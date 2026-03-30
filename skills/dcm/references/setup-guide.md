# DCM CI/CD Setup Guide

Complete setup for DCM CI/CD pipeline. Two auth options: PAT (simpler) or key-pair (more secure).

## Step 1: Create Deployer Role(s)

One role per environment, or a shared role for simpler setups.

```sql
USE ROLE ACCOUNTADMIN;

-- Shared deployer role (simple setup)
CREATE ROLE IF NOT EXISTS DCM_DEVELOPER
    COMMENT = 'Dedicated role for DCM project management and deployment';

GRANT CREATE DATABASE  ON ACCOUNT TO ROLE DCM_DEVELOPER;
GRANT CREATE WAREHOUSE ON ACCOUNT TO ROLE DCM_DEVELOPER;
GRANT CREATE ROLE      ON ACCOUNT TO ROLE DCM_DEVELOPER;
GRANT USAGE ON WAREHOUSE {{ warehouse }} TO ROLE DCM_DEVELOPER;

GRANT ROLE DCM_DEVELOPER TO USER {{ current_user }};
GRANT ROLE DCM_DEVELOPER TO ROLE SYSADMIN;
```

For multi-role setups (different deployer per env):
```sql
CREATE ROLE IF NOT EXISTS DCM_STAGE_DEPLOYER;
CREATE ROLE IF NOT EXISTS DCM_PROD_DEPLOYER;
-- Grant same privileges to each
```

## Step 2: Create Parent Databases

A DCM project CANNOT manage its own parent database. Create upfront.

```sql
USE ROLE DCM_DEVELOPER;

CREATE DATABASE IF NOT EXISTS DCM_DEMO;
CREATE SCHEMA IF NOT EXISTS DCM_DEMO.PROJECTS;
```

## Step 3: Create DCM Project Objects

One project object per environment. Can also be auto-created by workflows with `snow dcm create --if-not-exists -x`.

```sql
USE ROLE DCM_DEVELOPER;

CREATE DCM PROJECT IF NOT EXISTS DCM_DEMO.PROJECTS.DCM_PROJECT_DEV
    COMMENT = 'DCM Project - Development';

CREATE DCM PROJECT IF NOT EXISTS DCM_DEMO.PROJECTS.DCM_PROJECT_STG
    COMMENT = 'DCM Project - Staging';

CREATE DCM PROJECT IF NOT EXISTS DCM_DEMO.PROJECTS.DCM_PROJECT_PROD
    COMMENT = 'DCM Project - Production';
```

Or use the CLI:
```bash
snow dcm create --target DCM_DEV --if-not-exists -x
```

## Step 4: Create Service User

### Option A: Programmatic Access Token (PAT) — Simpler

```sql
USE ROLE ACCOUNTADMIN;

CREATE USER IF NOT EXISTS {{ service_user }}
    TYPE = SERVICE
    COMMENT = 'Service user for DCM CI/CD pipelines'
    DEFAULT_ROLE = DCM_DEVELOPER
    DEFAULT_WAREHOUSE = {{ warehouse }};

GRANT ROLE DCM_DEVELOPER TO USER {{ service_user }};
```

Generate a PAT for the service user via Snowsight (User menu → Programmatic Access Tokens) or SQL. Store as `DEPLOYER_PAT` in GitHub Secrets.

### Option B: Key-Pair Auth — More Secure

Same user creation as above, plus:

```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out dcm_cicd_rsa_key.p8 -nocrypt
openssl rsa -in dcm_cicd_rsa_key.p8 -pubout -out dcm_cicd_rsa_key.pub
```

```sql
ALTER USER {{ service_user }} SET RSA_PUBLIC_KEY = '<paste_public_key_here>';
```

Store private key contents as `SNOWFLAKE_PRIVATE_KEY_RAW` in GitHub Secrets.

**CRITICAL**: Key must be PKCS#8 format (`BEGIN PRIVATE KEY`, not `BEGIN RSA PRIVATE KEY`).

## Step 5: GitHub Configuration

### Repository Variables (Settings → Secrets → Actions → Variables)

| Variable | Value | Example |
|----------|-------|---------|
| `DCM_PROJECT_PATH` | Path from repo root to manifest.yml (trailing `/`) | `Quickstarts/DCM_Project_Quickstart_1/` |
| `SNOWFLAKE_USER` | Service user name | `GITHUB_ACTIONS_SERVICE_USER` |

### Repository Secrets (Settings → Secrets → Actions)

**For PAT auth (default):**

| Secret | Value |
|--------|-------|
| `DEPLOYER_PAT` | Programmatic access token for SNOWFLAKE_USER |

**For key-pair auth:**

| Secret | Value |
|--------|-------|
| `SNOWFLAKE_PRIVATE_KEY_RAW` | Full PEM private key content (include BEGIN/END lines) |

Then update workflow env blocks: replace `SNOWFLAKE_PASSWORD` with `SNOWFLAKE_PRIVATE_KEY_RAW` and add `SNOWFLAKE_AUTHENTICATOR: SNOWFLAKE_JWT`.

### GitHub Environments (Settings → Environments)

Create one environment per manifest target. Names MUST match exactly.

| Environment | Manifest Target | Protection |
|-------------|-----------------|------------|
| `DCM_STAGE` | `targets.DCM_STAGE` | Optional |
| `DCM_PROD_US` | `targets.DCM_PROD_US` | Required reviewers |

### Workflow Permissions (Settings → Actions → General)

- Select **Read and write permissions** (required for PR comments)

## Verification

```bash
snow dcm describe --target DCM_DEV -x
snow dcm list --target DCM_DEV -x
```

```sql
SHOW DCM PROJECTS IN SCHEMA DCM_DEMO.PROJECTS;
SHOW DEPLOYMENTS IN DCM PROJECT DCM_DEMO.PROJECTS.DCM_PROJECT_DEV;
```
