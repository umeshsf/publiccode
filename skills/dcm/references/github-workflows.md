# DCM GitHub Actions Workflows

Based on the official [Snowflake-Labs/snowflake_dcm_projects](https://github.com/Snowflake-Labs/snowflake_dcm_projects/tree/main/GitHub_workflows) repo.

## How the Workflows Work Together

| # | Workflow | Trigger | Purpose |
|---|---------|---------|---------|
| 1 | Test Connections | Manual | Validates connectivity and role config for all targets |
| 2 | Test PR to main | PR to `main` | Runs `snow dcm plan` on STAGE & PROD in parallel, posts PR comment |
| 3 | Deploy to STAGE & PROD | Push to `main` | Plan → Drop Detection → Deploy → Post Scripts → Refresh DTs → Test |
| 4 | Test STAGE Expectations | Manual | Ad-hoc data quality testing on STAGE |

**Typical flow:** Run Workflow 1 once to validate setup. Open PR (Workflow 2 for plan preview), merge (Workflow 3 for deploy). Workflow 4 for ad-hoc testing.

## Environment Variable Flow

1. `DCM_PROJECT_PATH` (repo variable) → locates `manifest.yml`
2. `manifest.yml` parsed with `yq` to extract `account_identifier`, `project_owner`, `project_name` per target
3. Values set as `SNOWFLAKE_ACCOUNT` and `SNOWFLAKE_ROLE` env vars
4. `SNOWFLAKE_USER` (repo variable) + auth secret (`DEPLOYER_PAT` or `SNOWFLAKE_PRIVATE_KEY_RAW`) complete connection
5. `snow` CLI picks up `SNOWFLAKE_*` env vars automatically via `-x` flag — no config.toml needed

## Workflow 1: Test Connections

Manual workflow that dynamically reads all targets from manifest using a matrix strategy.

```yaml
name: DCM 1) Test Connections

on:
  workflow_dispatch:

env:
  DCM_PROJECT_PATH: ${{ vars.DCM_PROJECT_PATH }}

jobs:
  PARSE_MANIFEST:
    runs-on: ubuntu-latest
    outputs:
      targets: ${{ steps.get_targets.outputs.targets }}
    steps:
    - uses: actions/checkout@v4

    - name: Get targets from manifest
      id: get_targets
      run: |
        MANIFEST_PATH="${{ env.DCM_PROJECT_PATH }}manifest.yml"
        TARGETS=$(yq eval '.targets | keys | @json' "$MANIFEST_PATH")
        echo "targets=$TARGETS" >> $GITHUB_OUTPUT
        echo "Manifest targets:" >> $GITHUB_STEP_SUMMARY
        echo "$TARGETS" | jq -r '.[] | "- \(.)"' >> $GITHUB_STEP_SUMMARY

    - name: Setup SnowCLI
      run: pip install git+https://github.com/snowflakedb/snowflake-cli.git

    - name: Verify SnowCLI version
      run: |
        SNOW_VERSION=$(snow --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
        MAJOR=$(echo "$SNOW_VERSION" | cut -d. -f1)
        MINOR=$(echo "$SNOW_VERSION" | cut -d. -f2)
        if [ "$MAJOR" -gt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 16 ]; }; then
          echo "Snowflake CLI ${SNOW_VERSION}" >> $GITHUB_STEP_SUMMARY
        else
          echo "Snowflake CLI ${SNOW_VERSION} — minimum required is 3.16" >> $GITHUB_STEP_SUMMARY
        fi

  TEST_CONNECTION:
    needs: PARSE_MANIFEST
    runs-on: ubuntu-latest
    strategy:
      matrix:
        target: ${{ fromJson(needs.PARSE_MANIFEST.outputs.targets) }}
      fail-fast: false
    environment: ${{ matrix.target }}
    steps:
    - uses: actions/checkout@v4
    - name: Setup SnowCLI
      run: pip install git+https://github.com/snowflakedb/snowflake-cli.git

    - name: Read manifest target ${{ matrix.target }}
      id: read_manifest
      run: |
        MANIFEST_PATH="${{ env.DCM_PROJECT_PATH }}manifest.yml"
        TARGET_NAME="${{ matrix.target }}"
        DCM_PROJECT_NAME=$(yq eval ".targets.$TARGET_NAME.project_name" "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")
        DCM_ACCOUNT=$(yq eval ".targets.$TARGET_NAME.account_identifier" "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")
        DCM_OWNER_ROLE=$(yq eval ".targets.$TARGET_NAME.project_owner" "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")
        echo "DCM_PROJECT_NAME=$DCM_PROJECT_NAME" >> $GITHUB_ENV
        echo "SNOWFLAKE_ACCOUNT=$DCM_ACCOUNT" >> $GITHUB_ENV
        echo "SNOWFLAKE_ROLE=$DCM_OWNER_ROLE" >> $GITHUB_ENV

    - name: 1. Test Connection
      env:
        SNOWFLAKE_PASSWORD: ${{ secrets.DEPLOYER_PAT }}
        SNOWFLAKE_USER: ${{ vars.SNOWFLAKE_USER }}
        TARGET_NAME: ${{ matrix.target }}
      run: |
        if ! snow connection test -x --format json > connection_output.json 2>&1; then
          echo "### Connection to $TARGET_NAME failed!" >> $GITHUB_STEP_SUMMARY
          cat connection_output.json 2>/dev/null >> $GITHUB_STEP_SUMMARY
          exit 1
        fi
        echo "### Connection to $TARGET_NAME successful!" >> $GITHUB_STEP_SUMMARY
        CONNECTION_ROLE=$(jq -r '.Role' connection_output.json)
        echo "CONNECTION_ROLE=$CONNECTION_ROLE" >> $GITHUB_ENV

    - name: 2. Validate Role Match
      run: |
        if [ "$CONNECTION_ROLE" = "$SNOWFLAKE_ROLE" ]; then
          echo "Role match: $CONNECTION_ROLE matches manifest project_owner $SNOWFLAKE_ROLE" >> $GITHUB_STEP_SUMMARY
        else
          echo "Role mismatch! Connection: $CONNECTION_ROLE, Manifest: $SNOWFLAKE_ROLE" >> $GITHUB_STEP_SUMMARY
          exit 1
        fi

    - name: 3. Validate DCM Project Status
      env:
        SNOWFLAKE_PASSWORD: ${{ secrets.DEPLOYER_PAT }}
        SNOWFLAKE_USER: ${{ vars.SNOWFLAKE_USER }}
        TARGET_NAME: ${{ matrix.target }}
      run: |
        cd ./$DCM_PROJECT_PATH
        if snow dcm describe --target $TARGET_NAME -x --format json > dcm_output.json 2>&1; then
          echo "Project $DCM_PROJECT_NAME exists" >> $GITHUB_STEP_SUMMARY
        else
          echo "Project $DCM_PROJECT_NAME does not yet exist (will be created on first deploy)" >> $GITHUB_STEP_SUMMARY
        fi
```

## Workflow 2: Test PR to main

Triggered on PRs. Parses manifest, runs PLAN against STAGE and PROD in parallel, posts results as PR comment.

```yaml
name: DCM 2) Test PR to main

on:
  pull_request:
    types: [opened, synchronize, reopened]
    branches: ["main"]
    paths:
      - 'Quickstarts/**'    # UPDATE: match your DCM project path
  workflow_dispatch:

env:
  DCM_PROJECT_PATH: ${{ vars.DCM_PROJECT_PATH }}
  SNOWFLAKE_PASSWORD: ${{ secrets.DEPLOYER_PAT }}
  SNOWFLAKE_USER: ${{ vars.SNOWFLAKE_USER }}

jobs:
  PARSE_MANIFEST:
    runs-on: ubuntu-latest
    outputs:
      stage_account: ${{ steps.get_targets.outputs.stage_account }}
      stage_role: ${{ steps.get_targets.outputs.stage_role }}
      stage_project_name: ${{ steps.get_targets.outputs.stage_project_name }}
      prod_account: ${{ steps.get_targets.outputs.prod_account }}
      prod_role: ${{ steps.get_targets.outputs.prod_role }}
      prod_project_name: ${{ steps.get_targets.outputs.prod_project_name }}
    steps:
    - uses: actions/checkout@v4
    - name: Get targets from manifest
      id: get_targets
      run: |
        MANIFEST_PATH="${{ env.DCM_PROJECT_PATH }}manifest.yml"
        echo "stage_account=$(yq eval '.targets.DCM_STAGE.account_identifier' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT
        echo "stage_role=$(yq eval '.targets.DCM_STAGE.project_owner' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT
        echo "stage_project_name=$(yq eval '.targets.DCM_STAGE.project_name' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT
        echo "prod_account=$(yq eval '.targets.DCM_PROD_US.account_identifier' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT
        echo "prod_role=$(yq eval '.targets.DCM_PROD_US.project_owner' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT
        echo "prod_project_name=$(yq eval '.targets.DCM_PROD_US.project_name' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT

  STAGE_PLAN:
    needs: PARSE_MANIFEST
    runs-on: ubuntu-latest
    environment: DCM_STAGE
    env:
      SNOWFLAKE_ACCOUNT: ${{ needs.PARSE_MANIFEST.outputs.stage_account }}
      SNOWFLAKE_ROLE: ${{ needs.PARSE_MANIFEST.outputs.stage_role }}
    steps:
    - uses: actions/checkout@v4
    - name: Setup SnowCLI
      run: pip install git+https://github.com/snowflakedb/snowflake-cli.git
    - name: Execute PLAN against STAGE
      id: stage_plan
      run: |
        cd ./$DCM_PROJECT_PATH
        snow dcm create --target DCM_STAGE --if-not-exists -x
        mkdir -p summary

        if snow dcm plan --target DCM_STAGE --save-output -x; then
          echo "### DCM Plan to STAGE successful" >> $GITHUB_STEP_SUMMARY
          PLAN_METADATA_FILE="out/plan/plan_result.json"
          for OP_TYPE in CREATE ALTER DROP; do
            OP_COUNT=$(jq --arg OP_TYPE "$OP_TYPE" '.changeset[] | select(.type == $OP_TYPE)' "$PLAN_METADATA_FILE" | jq -s 'length')
            echo "**${OP_TYPE} operations: $OP_COUNT**" >> $GITHUB_STEP_SUMMARY
          done
          cp $GITHUB_STEP_SUMMARY summary/stage-plan-summary.md
        else
          echo "### DCM Plan to STAGE failed" >> $GITHUB_STEP_SUMMARY
          cp $GITHUB_STEP_SUMMARY summary/stage-plan-summary.md
          exit 1
        fi
    - uses: actions/upload-artifact@v4
      if: always()
      with:
        name: stage-plan-summary
        path: ${{ env.DCM_PROJECT_PATH }}summary/stage-plan-summary.md

  PROD_PLAN:
    needs: PARSE_MANIFEST
    runs-on: ubuntu-latest
    environment: DCM_PROD_US
    env:
      SNOWFLAKE_ACCOUNT: ${{ needs.PARSE_MANIFEST.outputs.prod_account }}
      SNOWFLAKE_ROLE: ${{ needs.PARSE_MANIFEST.outputs.prod_role }}
    steps:
    - uses: actions/checkout@v4
    - name: Setup SnowCLI
      run: pip install git+https://github.com/snowflakedb/snowflake-cli.git
    - name: Execute PLAN against PROD
      id: prod_plan
      run: |
        cd ./$DCM_PROJECT_PATH
        snow dcm create --target DCM_PROD_US --if-not-exists -x
        mkdir -p summary

        if snow dcm plan --target DCM_PROD_US --save-output -x; then
          echo "### DCM Plan to PROD successful" >> $GITHUB_STEP_SUMMARY
          PLAN_METADATA_FILE="out/plan/plan_result.json"
          for OP_TYPE in CREATE ALTER DROP; do
            OP_COUNT=$(jq --arg OP_TYPE "$OP_TYPE" '.changeset[] | select(.type == $OP_TYPE)' "$PLAN_METADATA_FILE" | jq -s 'length')
            echo "**${OP_TYPE} operations: $OP_COUNT**" >> $GITHUB_STEP_SUMMARY
          done
          cp $GITHUB_STEP_SUMMARY summary/prod-plan-summary.md
        else
          echo "### DCM Plan to PROD failed" >> $GITHUB_STEP_SUMMARY
          cp $GITHUB_STEP_SUMMARY summary/prod-plan-summary.md
          exit 1
        fi
    - uses: actions/upload-artifact@v4
      if: always()
      with:
        name: prod-plan-summary
        path: ${{ env.DCM_PROJECT_PATH }}summary/prod-plan-summary.md

  COMMENT_ON_PR:
    needs: [STAGE_PLAN, PROD_PLAN]
    if: always()
    runs-on: ubuntu-latest
    permissions:
      issues: write
      pull-requests: write
    steps:
    - uses: actions/download-artifact@v4
      with:
        pattern: '*-summary'
        merge-multiple: true
    - name: Post Summary to PR
      uses: actions/github-script@v7
      with:
        script: |
          const fs = require('fs');
          let comment = '### DCM merge check\n\n';
          for (const file of ['stage-plan-summary.md', 'prod-plan-summary.md']) {
            try { comment += fs.readFileSync(file, 'utf8') + '---\n'; }
            catch (e) { comment += `Could not retrieve ${file} summary.\n\n`; }
          }
          comment += `[View full run](https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }})`;
          if (context.eventName === 'pull_request') {
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: comment
            });
          }
```

## Workflow 3: Deploy to STAGE & PROD

Triggered on push to main. Sequential pipeline: STAGE first (Plan → Drop Detection → Deploy → Post Scripts → Refresh DTs → Test), then PROD.

```yaml
name: DCM 3) Deploy to STAGE & PROD

on:
  push:
    branches: ["main"]
    paths:
      - 'Quickstarts/**'    # UPDATE: match your DCM project path
  workflow_dispatch:

env:
  DCM_PROJECT_PATH: ${{ vars.DCM_PROJECT_PATH }}
  SNOWFLAKE_PASSWORD: ${{ secrets.DEPLOYER_PAT }}
  SNOWFLAKE_USER: ${{ vars.SNOWFLAKE_USER }}

jobs:
  PARSE_MANIFEST:
    runs-on: ubuntu-latest
    outputs:
      stage_account: ${{ steps.get_targets.outputs.stage_account }}
      stage_role: ${{ steps.get_targets.outputs.stage_role }}
      prod_account: ${{ steps.get_targets.outputs.prod_account }}
      prod_role: ${{ steps.get_targets.outputs.prod_role }}
    steps:
    - uses: actions/checkout@v4
    - name: Get targets from manifest
      id: get_targets
      run: |
        MANIFEST_PATH="${{ env.DCM_PROJECT_PATH }}manifest.yml"
        echo "stage_account=$(yq eval '.targets.DCM_STAGE.account_identifier' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT
        echo "stage_role=$(yq eval '.targets.DCM_STAGE.project_owner' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT
        echo "prod_account=$(yq eval '.targets.DCM_PROD_US.account_identifier' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT
        echo "prod_role=$(yq eval '.targets.DCM_PROD_US.project_owner' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT

  # ===== STAGE PIPELINE =====
  PLAN_STAGE:
    needs: PARSE_MANIFEST
    runs-on: ubuntu-latest
    environment: DCM_STAGE
    env:
      SNOWFLAKE_ACCOUNT: ${{ needs.PARSE_MANIFEST.outputs.stage_account }}
      SNOWFLAKE_ROLE: ${{ needs.PARSE_MANIFEST.outputs.stage_role }}
    steps:
    - uses: actions/checkout@v4
    - run: pip install git+https://github.com/snowflakedb/snowflake-cli.git
    - name: Plan STAGE
      run: |
        cd ./$DCM_PROJECT_PATH
        snow dcm create --target DCM_STAGE --if-not-exists -x
        if snow dcm plan --target DCM_STAGE --save-output -x; then
          echo "### DCM Plan to STAGE successful" >> $GITHUB_STEP_SUMMARY
        else
          echo "### DCM Plan to STAGE failed" >> $GITHUB_STEP_SUMMARY
          exit 1
        fi
    - uses: actions/upload-artifact@v4
      if: always()
      with:
        name: stage-plan-output
        path: ${{ env.DCM_PROJECT_PATH }}out/plan/plan_result.json

  DATA_DROP_DETECTION_STAGE:
    needs: PLAN_STAGE
    runs-on: ubuntu-latest
    steps:
    - uses: actions/download-artifact@v4
      with:
        name: stage-plan-output
        path: ${{ env.DCM_PROJECT_PATH }}out/plan/
    - name: Check for Destructive Commands
      run: |
        PLAN_FILE="${{ env.DCM_PROJECT_PATH }}out/plan/plan_result.json"
        DESTRUCTIVE=$(jq -c '[.changeset[] | select(.type == "DROP" and (.object_id.domain | IN("DATABASE","SCHEMA","TABLE","STAGE")))]' "$PLAN_FILE")
        TOTAL=$(echo "$DESTRUCTIVE" | jq 'length')
        if [[ $TOTAL -gt 0 ]]; then
          echo "### PLAN contains $TOTAL DROP operation(s) on data objects — blocking deploy" >> $GITHUB_STEP_SUMMARY
          echo "$DESTRUCTIVE" | jq -r '.[] | "- DROP \(.object_id.domain): \(.object_id.name)"' >> $GITHUB_STEP_SUMMARY
          exit 1
        else
          echo "### No destructive DROP commands found" >> $GITHUB_STEP_SUMMARY
        fi

  DEPLOY_STAGE:
    needs: [PARSE_MANIFEST, PLAN_STAGE, DATA_DROP_DETECTION_STAGE]
    runs-on: ubuntu-latest
    environment: DCM_STAGE
    env:
      SNOWFLAKE_ACCOUNT: ${{ needs.PARSE_MANIFEST.outputs.stage_account }}
      SNOWFLAKE_ROLE: ${{ needs.PARSE_MANIFEST.outputs.stage_role }}
    steps:
    - uses: actions/checkout@v4
    - run: pip install git+https://github.com/snowflakedb/snowflake-cli.git
    - name: Deploy to STAGE
      run: |
        cd ./$DCM_PROJECT_PATH
        if snow dcm deploy --target DCM_STAGE -x; then
          echo "### DCM Deploy to STAGE successful" >> $GITHUB_STEP_SUMMARY
        else
          echo "### DCM Deploy to STAGE failed" >> $GITHUB_STEP_SUMMARY
          exit 1
        fi

  POST_SCRIPTS_STAGE:
    needs: [PARSE_MANIFEST, DEPLOY_STAGE]
    runs-on: ubuntu-latest
    environment: DCM_STAGE
    env:
      SNOWFLAKE_ACCOUNT: ${{ needs.PARSE_MANIFEST.outputs.stage_account }}
      SNOWFLAKE_ROLE: ${{ needs.PARSE_MANIFEST.outputs.stage_role }}
    steps:
    - uses: actions/checkout@v4
    - run: pip install git+https://github.com/snowflakedb/snowflake-cli.git
    - name: Execute post scripts
      run: |
        cd ./$DCM_PROJECT_PATH
        if [ -f SQL_post_scripts/insert_sample_data.sql ]; then
          snow sql -f SQL_post_scripts/insert_sample_data.sql --variable "env_suffix=STG" --enable-templating JINJA -x
          echo "### Post scripts executed" >> $GITHUB_STEP_SUMMARY
        else
          echo "No post-hook files found." >> $GITHUB_STEP_SUMMARY
        fi

  REFRESH_DYNAMIC_TABLES_STAGE:
    needs: [PARSE_MANIFEST, POST_SCRIPTS_STAGE]
    runs-on: ubuntu-latest
    environment: DCM_STAGE
    env:
      SNOWFLAKE_ACCOUNT: ${{ needs.PARSE_MANIFEST.outputs.stage_account }}
      SNOWFLAKE_ROLE: ${{ needs.PARSE_MANIFEST.outputs.stage_role }}
    steps:
    - uses: actions/checkout@v4
    - run: pip install git+https://github.com/snowflakedb/snowflake-cli.git
    - name: Refresh Dynamic Tables
      run: |
        cd ./$DCM_PROJECT_PATH
        set +e
        REFRESH_OUTPUT=$(snow dcm refresh --target DCM_STAGE -x 2>&1)
        EXIT_CODE=$?
        set -e
        if [ $EXIT_CODE -eq 0 ]; then
          echo "### Dynamic Tables Refresh Successful" >> $GITHUB_STEP_SUMMARY
        else
          echo "### Dynamic Tables Refresh Failed" >> $GITHUB_STEP_SUMMARY
          echo "$REFRESH_OUTPUT" >> $GITHUB_STEP_SUMMARY
          exit $EXIT_CODE
        fi

  TEST_EXPECTATIONS_STAGE:
    needs: [PARSE_MANIFEST, REFRESH_DYNAMIC_TABLES_STAGE]
    runs-on: ubuntu-latest
    environment: DCM_STAGE
    env:
      SNOWFLAKE_ACCOUNT: ${{ needs.PARSE_MANIFEST.outputs.stage_account }}
      SNOWFLAKE_ROLE: ${{ needs.PARSE_MANIFEST.outputs.stage_role }}
    steps:
    - uses: actions/checkout@v4
    - run: pip install git+https://github.com/snowflakedb/snowflake-cli.git
    - name: Test Data Quality
      run: |
        cd ./$DCM_PROJECT_PATH
        set +e
        TEST_OUTPUT=$(snow dcm test --target DCM_STAGE -x 2>&1)
        EXIT_CODE=$?
        set -e
        if [ $EXIT_CODE -eq 0 ]; then
          echo "### Data Quality Test Passed" >> $GITHUB_STEP_SUMMARY
        else
          echo "### Data Quality Test Failed" >> $GITHUB_STEP_SUMMARY
          echo "$TEST_OUTPUT" >> $GITHUB_STEP_SUMMARY
          exit $EXIT_CODE
        fi

  # ===== PROD PIPELINE (runs after STAGE succeeds) =====
  PLAN_PROD:
    needs: [PARSE_MANIFEST, TEST_EXPECTATIONS_STAGE]
    runs-on: ubuntu-latest
    environment: DCM_PROD_US
    env:
      SNOWFLAKE_ACCOUNT: ${{ needs.PARSE_MANIFEST.outputs.prod_account }}
      SNOWFLAKE_ROLE: ${{ needs.PARSE_MANIFEST.outputs.prod_role }}
    steps:
    - uses: actions/checkout@v4
    - run: pip install git+https://github.com/snowflakedb/snowflake-cli.git
    - name: Plan PROD
      run: |
        cd ./$DCM_PROJECT_PATH
        snow dcm create --target DCM_PROD_US --if-not-exists -x
        if snow dcm plan --target DCM_PROD_US --save-output -x; then
          echo "### DCM Plan to PROD successful" >> $GITHUB_STEP_SUMMARY
        else
          echo "### DCM Plan to PROD failed" >> $GITHUB_STEP_SUMMARY
          exit 1
        fi
    - uses: actions/upload-artifact@v4
      if: always()
      with:
        name: prod-plan-output
        path: ${{ env.DCM_PROJECT_PATH }}out/plan/plan_result.json

  DATA_DROP_DETECTION_PROD:
    needs: PLAN_PROD
    runs-on: ubuntu-latest
    steps:
    - uses: actions/download-artifact@v4
      with:
        name: prod-plan-output
        path: ${{ env.DCM_PROJECT_PATH }}out/plan/
    - name: Check for Destructive Commands
      run: |
        PLAN_FILE="${{ env.DCM_PROJECT_PATH }}out/plan/plan_result.json"
        DESTRUCTIVE=$(jq -c '[.changeset[] | select(.type == "DROP" and (.object_id.domain | IN("DATABASE","SCHEMA","TABLE","STAGE")))]' "$PLAN_FILE")
        TOTAL=$(echo "$DESTRUCTIVE" | jq 'length')
        if [[ $TOTAL -gt 0 ]]; then
          echo "### PLAN contains $TOTAL DROP operation(s) — blocking deploy" >> $GITHUB_STEP_SUMMARY
          exit 1
        else
          echo "### No destructive DROP commands found" >> $GITHUB_STEP_SUMMARY
        fi

  DEPLOY_PROD:
    needs: [PARSE_MANIFEST, PLAN_PROD, DATA_DROP_DETECTION_PROD]
    runs-on: ubuntu-latest
    environment: DCM_PROD_US
    env:
      SNOWFLAKE_ACCOUNT: ${{ needs.PARSE_MANIFEST.outputs.prod_account }}
      SNOWFLAKE_ROLE: ${{ needs.PARSE_MANIFEST.outputs.prod_role }}
    steps:
    - uses: actions/checkout@v4
    - run: pip install git+https://github.com/snowflakedb/snowflake-cli.git
    - name: Deploy to PROD
      run: |
        cd ./$DCM_PROJECT_PATH
        if snow dcm deploy --target DCM_PROD_US -x; then
          echo "### DCM Deploy to PROD successful" >> $GITHUB_STEP_SUMMARY
        else
          echo "### DCM Deploy to PROD failed" >> $GITHUB_STEP_SUMMARY
          exit 1
        fi

  # Repeat POST_SCRIPTS, REFRESH_DTs, TEST_EXPECTATIONS for PROD as needed
```

## Workflow 4: Test STAGE Expectations (Manual)

```yaml
name: DCM 4) Test STAGE Expectations

on:
  workflow_dispatch:

env:
  DCM_PROJECT_PATH: ${{ vars.DCM_PROJECT_PATH }}
  SNOWFLAKE_PASSWORD: ${{ secrets.DEPLOYER_PAT }}
  SNOWFLAKE_USER: ${{ vars.SNOWFLAKE_USER }}

jobs:
  PARSE_MANIFEST:
    runs-on: ubuntu-latest
    outputs:
      stage_account: ${{ steps.get_targets.outputs.stage_account }}
      stage_role: ${{ steps.get_targets.outputs.stage_role }}
    steps:
    - uses: actions/checkout@v4
    - name: Get STAGE target
      id: get_targets
      run: |
        MANIFEST_PATH="${{ env.DCM_PROJECT_PATH }}manifest.yml"
        echo "stage_account=$(yq eval '.targets.DCM_STAGE.account_identifier' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT
        echo "stage_role=$(yq eval '.targets.DCM_STAGE.project_owner' "$MANIFEST_PATH" | sed 's/"//g' | sed "s/'//g")" >> $GITHUB_OUTPUT

  REFRESH_AND_TEST:
    needs: PARSE_MANIFEST
    runs-on: ubuntu-latest
    environment: DCM_STAGE
    env:
      SNOWFLAKE_ACCOUNT: ${{ needs.PARSE_MANIFEST.outputs.stage_account }}
      SNOWFLAKE_ROLE: ${{ needs.PARSE_MANIFEST.outputs.stage_role }}
    steps:
    - uses: actions/checkout@v4
    - run: pip install git+https://github.com/snowflakedb/snowflake-cli.git
    - name: Refresh Dynamic Tables
      run: |
        cd ./$DCM_PROJECT_PATH
        snow dcm refresh --target DCM_STAGE -x
    - name: Test Expectations
      run: |
        cd ./$DCM_PROJECT_PATH
        snow dcm test --target DCM_STAGE -x
```

## Customization Notes

**Different target names**: If your manifest uses different targets (e.g., `STAGING`, `PRODUCTION`), update the hardcoded target references in Workflows 2-4. Workflow 1 is fully dynamic.

**Single-target deployment**: Remove PROD jobs from Workflows 2 and 3, adjust `needs` dependencies.

**Key-pair auth**: Replace `SNOWFLAKE_PASSWORD: ${{ secrets.DEPLOYER_PAT }}` with:
```yaml
SNOWFLAKE_PRIVATE_KEY_RAW: ${{ secrets.SNOWFLAKE_PRIVATE_KEY_RAW }}
SNOWFLAKE_AUTHENTICATOR: SNOWFLAKE_JWT
```

**Path filters**: Update `paths` in Workflows 2 and 3 to match your project location.

**Post scripts**: The official repo runs `SQL_post_scripts/insert_sample_data.sql` with Jinja templating via `--variable "env_suffix=STG"`. Customize for your scripts.
