# DCM CI/CD Gotchas & Common Pitfalls

## 1. Account Identifier Format

The manifest `account_identifier` uses **org-account** format: `MYORG-MYACCOUNT`.

Find yours with:
```sql
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME();
```

Do NOT use legacy locator format (e.g., `abc12345.us-west-2`).

## 2. DCM Cannot Manage Its Own Parent Database

A DCM project object lives inside a database (e.g., `DCM_DEMO.PROJECTS.MY_PROJECT`). That project **cannot** DEFINE the database it resides in. Create parent databases manually or in a separate setup step.

## 3. Definition Files: DEFINE/GRANT/ATTACH Only

Definition files under `sources/definitions/` can ONLY contain:
- `DEFINE` statements
- `GRANT` statements
- `ATTACH` statements

No other SQL commands (SELECT, INSERT, ALTER, etc.) are allowed. Use post-deploy scripts for DML operations.

## 4. The `_snow` Identifier is Reserved

You cannot use `_snow` as a variable name or macro name in Jinja templates. It is reserved for future Snowflake use.

## 5. Add `out/` to .gitignore

DCM commands write output artifacts (plan results, etc.) to the `out/` directory. Add this to `.gitignore` to avoid pushing local outputs to Git:
```
out/
```

## 6. Dictionaries Cannot Be Overwritten at Runtime

You can define dictionaries in `manifest.yml` configurations, but you CANNOT override them with `--variable` flags or `USING CONFIGURATION (...)` at runtime. Only scalar values and lists can be overwritten at runtime.

## 7. Environment Names Must Match Target Names

GitHub environment names **must exactly match** manifest target names:
- Manifest target: `DCM_STAGE` → GitHub environment: `DCM_STAGE`
- Manifest target: `DCM_PROD_US` → GitHub environment: `DCM_PROD_US`

A mismatch means the workflow jobs will use wrong secrets or fail to find the environment.

## 8. Private Key Must Be PKCS#8 Format

Key must start with `BEGIN PRIVATE KEY`, NOT `BEGIN RSA PRIVATE KEY`.

Generate correctly:
```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out key.p8 -nocrypt
```

For CI/CD, use `SNOWFLAKE_PRIVATE_KEY_RAW` (full PEM content as string), not `SNOWFLAKE_PRIVATE_KEY_FILE` (GitHub runners lack persistent file storage).

## 9. Workflow YAML Must Exist on main First

GitHub Actions only recognizes workflow triggers (PR, push) if the YAML file exists on the default branch. Push workflow files to `main` before testing PR triggers.

## 10. Snowflake CLI Version >= 3.16 Required

DCM commands (`snow dcm plan`, `snow dcm deploy`, etc.) require Snowflake CLI v3.16+. In workflows, the official pattern installs from Git:
```bash
pip install git+https://github.com/snowflakedb/snowflake-cli.git
```

Verify with:
```bash
snow --version
snow dcm --help
```

## 11. The `-x` Flag Creates Temporary Connections

The `-x` flag tells the CLI to build a connection from `SNOWFLAKE_*` environment variables instead of reading `connections.toml`. This is essential for CI/CD where no config file exists. Required env vars: `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_ROLE`, and either `SNOWFLAKE_PASSWORD` or `SNOWFLAKE_PRIVATE_KEY_RAW` + `SNOWFLAKE_AUTHENTICATOR`.

## 12. Data Drop Detection Blocks Intentional Drops

Workflow 3 includes a safety gate that blocks deployment if the plan contains DROP operations on DATABASE, SCHEMA, TABLE, or STAGE. If a DROP is intentional, temporarily disable the detection step or manually approve the run.

## 13. DCM_PROJECT_PATH Must End with `/`

The `DCM_PROJECT_PATH` repository variable must include a trailing slash. The workflows concatenate it directly: `"$DCM_PROJECT_PATH"manifest.yml`. Missing slash = file not found.

## 14. Fully Qualified Names Required in Definitions

All objects in DEFINE statements must use fully qualified names: `database.schema.object_name`. Shorthand names are not supported.

## 15. Global Macros Are Auto-Imported

Macros in `sources/macros/` are automatically visible in all definition files. No `import` statements needed (and `import`/`extends`/`include` Jinja tags are not supported).
