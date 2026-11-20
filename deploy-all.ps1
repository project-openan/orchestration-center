# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# =============================================================================
# Orchestration Center - One-Click GCP Deployment
# =============================================================================
# This script handles EVERYTHING:
#   1. Checks prerequisites (gcloud installed, logged in)
#   2. Creates GCP resources (Cloud SQL, Artifact Registry, etc.) if needed
#   3. Detects Registry Center in same/cross project and configures linkage
#   4. Builds and deploys to Cloud Run
#
# USAGE:  Just run this script in PowerShell:
#   .\deploy-all.ps1
#   .\deploy-all.ps1 -ServiceName "orchestration-center" -GCPProjectID "my-project"
#
# You will be prompted for your GCP Project ID, a database password,
# and optionally a Registry Center URL and LLM configuration.
#
# ENVIRONMENT VARIABLES (optional, skip prompts):
#   GCP_PROJECT_ID    - Target GCP project
#   GCP_REGION        - Deployment region (default: asia-east1)
#   DB_PASSWORD       - PostgreSQL password
#   AGENT_REGISTRY_URL - Registry Center URL (auto-detected if in same project)
#   LLM_CHAT_API_KEY  - LLM API key (DeepSeek, OpenAI, etc.)
#   LLM_CHAT_MODEL    - LLM model name
#   LLM_CHAT_URL      - LLM API URL
# =============================================================================

param(
    [string]$ServiceName = "",
    [string]$GCPProjectID = ""
)

# Fail before reading secrets, changing environment or contacting cloud APIs.
# This legacy entrypoint has not adopted account bootstrap, model mounts and Secret Manager.
throw "Legacy GCP deployment is not supported by the current authentication contract. Use the validated Helm/Compose installers in project-openan/openan-installation; do not run this script against a cluster."

$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false

# ── Clear residual env vars from previous runs ──────────────────────────────
# Prevents cross-contamination when deploying multiple services in the same
# PowerShell session.
$cleanupVars = @('GCP_PROJECT_ID', 'GCP_REGION', 'DB_PASSWORD', 'PERSISTENCE_MODE', 'DB_HOST', 'DB_PORT',
                 'DB_NAME', 'DB_USERNAME', 'DB_POOL_MIN', 'DB_POOL_MAX',
                 'ORCH_IP', 'ORCH_ENABLE_HTTPS', 'ORCH_FORWARDED_ALLOW_IPS',
                 'AGENT_REGISTRY_URL', 'LLM_CHAT_MODEL', 'LLM_CHAT_API_KEY',
                 'LLM_CHAT_URL', 'A2AT_LLM_PROVIDER', 'A2AT_LLM_MODEL',
                 'A2AT_LLM_API_KEY', 'A2AT_LLM_BASE_URL')
foreach ($v in $cleanupVars) {
    Remove-Item "env:$v" -ErrorAction SilentlyContinue
}

# Use param value if provided, otherwise keep current env value for Read-Host fallback
if ($GCPProjectID) { $env:GCP_PROJECT_ID = $GCPProjectID }

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host ""
Write-Host "===================================================================="
Write-Host "  Orchestration Center - GCP Cloud Run Deployment (All-in-One)"
Write-Host "===================================================================="
Write-Host ""

# ── Step 1: Check gcloud ────────────────────────────────────────────────────
Write-Host "[1/7] Checking gcloud CLI..."
$gcloudPath = Get-Command gcloud -ErrorAction SilentlyContinue
if (-not $gcloudPath) {
    Write-Host ""
    Write-Host "ERROR: gcloud CLI is not installed."
    Write-Host ""
    Write-Host "Install it now (run in PowerShell as Administrator):"
    Write-Host "  (New-Object Net.WebClient).DownloadFile('https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe', `"`$env:TEMP\gcloud-installer.exe`"); Start-Process `"`$env:TEMP\gcloud-installer.exe`" -Wait"
    Write-Host ""
    Write-Host "After installation, CLOSE this PowerShell, open a NEW one, and run this script again."
    exit 1
}
Write-Host "  OK: gcloud found"

# ── Step 2: Check login ─────────────────────────────────────────────────────
Write-Host "[2/7] Checking GCP login status..."
$account = gcloud auth list --format="value(account)" 2>$null
if (-not $account) {
    Write-Host ""
    Write-Host "You need to log in to your Google Cloud account."
    Write-Host "A browser window will open..."
    gcloud auth login
    Write-Host ""
    Write-Host "After login, run this script again."
    exit 0
}
Write-Host "  Logged in as: ${account}"

# ── Step 3: Detect Registry Center & confirm deployment project ──────────────
Write-Host "[3/7] Detecting Registry Center & confirming deployment project..."
Write-Host ""

if (-not $env:GCP_PROJECT_ID) {
    $env:GCP_PROJECT_ID = Read-Host "Enter your GCP Project ID"
}
if (-not $env:GCP_PROJECT_ID) {
    Write-Host "ERROR: GCP Project ID is required."
    exit 1
}

# Resolve and validate service name
if (-not $ServiceName) { $ServiceName = "orchestration-center" }
if ($ServiceName -notmatch '^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$') {
    Write-Host "ERROR: ServiceName '$ServiceName' is invalid. Use lowercase letters, digits, and hyphens only."
    exit 1
}

if (-not $env:GCP_REGION) { $env:GCP_REGION = "asia-east1" }

Write-Host "  Deployment project: $env:GCP_PROJECT_ID"

# ── Detect Registry Center ────────────────────────────────────────────────────
$REGISTRY_URL = ""

if (-not $env:AGENT_REGISTRY_URL) {
    Write-Host ""
    Write-Host "  -- Registry Center Detection --"
    Write-Host ""

    # Try current project first
    Write-Host "  Checking project '${env:GCP_PROJECT_ID}' for Registry Center..."
    $sameProjectRegistry = gcloud run services describe "registry-center" --region="$env:GCP_REGION" --project="$env:GCP_PROJECT_ID" --format="value(status.url)" 2>$null
    if ($sameProjectRegistry) {
        Write-Host "  Found Registry Center in same project: ${sameProjectRegistry}"
        $useIt = Read-Host "  Link to this Registry Center? (Y/n)"
        if ($useIt -eq "" -or $useIt -eq "Y" -or $useIt -eq "y") {
            $REGISTRY_URL = $sameProjectRegistry
        }
    }

    # Try another project if not found or declined
    if (-not $REGISTRY_URL) {
        Write-Host "  No Registry Center found in current project, or link declined."
        Write-Host "  If Registry Center is in another project, enter that project ID."
        Write-Host ""
        $registryProject = Read-Host "Enter Registry Center project ID (or press Enter to skip)"
        if ($registryProject) {
            Write-Host "  Checking project '${registryProject}' for Registry Center..."
            $crossProjectRegistry = gcloud run services describe "registry-center" --region="$env:GCP_REGION" --project="$registryProject" --format="value(status.url)" 2>$null
            if ($crossProjectRegistry) {
                Write-Host "  Found Registry Center in project '${registryProject}': ${crossProjectRegistry}"
                $useIt = Read-Host "  Link to this Registry Center? (Y/n)"
                if ($useIt -eq "" -or $useIt -eq "Y" -or $useIt -eq "y") {
                    $REGISTRY_URL = $crossProjectRegistry
                }
            } else {
                Write-Host "  No Registry Center found in project '${registryProject}'."
            }
        }
    }

    if (-not $REGISTRY_URL) {
        Write-Host "  You can enter the URL directly (from the Registry Center deployment output)."
        Write-Host ""
        $manualUrl = Read-Host "Enter Registry Center URL (or press Enter to skip)"
        if ($manualUrl) {
            $REGISTRY_URL = $manualUrl
        }
    }
} else {
    $REGISTRY_URL = $env:AGENT_REGISTRY_URL
}

Write-Host ""

# ── Step 4: Collect configuration ───────────────────────────────────────────
Write-Host "[4/7] Collecting deployment configuration..."
Write-Host ""

if (-not $env:DB_PASSWORD) {
    # Try to retrieve existing password from Secret Manager
    # Use project-specific secret name to isolate passwords across GCP projects
    $sanitizeProj = $env:GCP_PROJECT_ID -replace '[^a-zA-Z0-9]', '-'
    $lookupSecretID = "${ServiceName}-db-password-${sanitizeProj}"
    $secretTmpRead = Join-Path $env:TEMP "${ServiceName}-secret-read.tmp"
    $readOk = $false
    try {
        gcloud secrets versions access latest --secret="$lookupSecretID" --project="$env:GCP_PROJECT_ID" --out-file="$secretTmpRead" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $rawBytes = [System.IO.File]::ReadAllBytes($secretTmpRead)
            if ($rawBytes.Length -ge 3 -and $rawBytes[0] -eq 0xEF -and $rawBytes[1] -eq 0xBB -and $rawBytes[2] -eq 0xBF) {
                $rawBytes = $rawBytes[3..($rawBytes.Length - 1)]
            }
            $existingPassword = [System.Text.Encoding]::UTF8.GetString($rawBytes).TrimEnd("`r", "`n")
            if ($existingPassword -and $existingPassword -notmatch '^\d+(\s+\d+)+$') {
                $env:DB_PASSWORD = $existingPassword
                $readOk = $true
                Write-Host "  Using existing password from Secret Manager ($lookupSecretID)"
            } else {
                Write-Host "  WARNING: Stored password appears corrupted (ASCII byte values), will regenerate."
            }
        }
    } catch { }
    if (Test-Path $secretTmpRead) { Remove-Item $secretTmpRead -Force }

    if (-not $readOk) {
        $env:DB_PASSWORD = Read-Host "Set a password for the PostgreSQL database (or press Enter to auto-generate)"
        if (-not $env:DB_PASSWORD) {
            $env:DB_PASSWORD = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 16 | ForEach-Object {[char]$_})
            Write-Host "  Auto-generated password: $env:DB_PASSWORD"
        }
    }
}

# ── LLM Configuration ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "  -- LLM (Large Language Model) Configuration --"
Write-Host "  The orchestration center requires an LLM for PSOP generation and execution."
Write-Host "  You can configure it now, or skip and configure later via GCP Console."
Write-Host ""

$LLM_CHAT_MODEL = ""
$LLM_CHAT_API_KEY = ""
$LLM_CHAT_URL = ""

if (-not $env:LLM_CHAT_API_KEY) {
    Write-Host "  Supported providers: DeepSeek, OpenAI, or any OpenAI-compatible API."
    $LLM_CHAT_API_KEY = Read-Host "  Enter LLM API Key (or press Enter to skip and configure later)"
} else {
    $LLM_CHAT_API_KEY = $env:LLM_CHAT_API_KEY
}

if ($LLM_CHAT_API_KEY) {
    if (-not $env:LLM_CHAT_MODEL) {
        $LLM_CHAT_MODEL = Read-Host "  Enter LLM Model name (default: deepseek-chat)"
        if (-not $LLM_CHAT_MODEL) { $LLM_CHAT_MODEL = "deepseek-chat" }
    } else {
        $LLM_CHAT_MODEL = $env:LLM_CHAT_MODEL
    }

    if (-not $env:LLM_CHAT_URL) {
        $LLM_CHAT_URL = Read-Host "  Enter LLM API URL (default: https://api.deepseek.com/v1/chat/completions)"
        if (-not $LLM_CHAT_URL) { $LLM_CHAT_URL = "https://api.deepseek.com/v1/chat/completions" }
    } else {
        $LLM_CHAT_URL = $env:LLM_CHAT_URL
    }

    Write-Host "  LLM configured: model=${LLM_CHAT_MODEL}, url=${LLM_CHAT_URL}"
} else {
    Write-Host "  LLM not configured now. You MUST configure it later for the service to work."
    Write-Host "  See deployment guide: '部署后补配大模型 (LLM)' section."
}

Write-Host ""
Write-Host "  Final configuration:"
Write-Host "    Service          : ${ServiceName}"
Write-Host "    Project ID       : $env:GCP_PROJECT_ID"
Write-Host "    Region           : $env:GCP_REGION"
Write-Host "    Registry URL     : $(if ($REGISTRY_URL) { $REGISTRY_URL } else { '(not configured)' })"
Write-Host "    LLM Model        : $(if ($LLM_CHAT_MODEL) { $LLM_CHAT_MODEL } else { '(not configured)' })"
Write-Host ""

# ── Step 5: Setup GCP resources (idempotent - safe to re-run) ───────────────
Write-Host "[5/7] Setting up GCP resources (this may take 5-10 minutes)..."
Write-Host ""

$SERVICE_NAME    = $ServiceName
$ARTIFACT_REPO   = "openan-repo"
$CLOUDSQL_INST   = "${SERVICE_NAME}-db"
$DB_NAME         = ($SERVICE_NAME -replace '-', '_')
$DB_USER         = ($SERVICE_NAME -split '-')[0]
$SA_NAME         = "${SERVICE_NAME}-sa"
$SA_EMAIL        = "${SA_NAME}@$env:GCP_PROJECT_ID.iam.gserviceaccount.com"
$secretProjectID = ($env:GCP_PROJECT_ID -replace '[^a-zA-Z0-9]', '-')
$SECRET_ID       = "${SERVICE_NAME}-db-password-${secretProjectID}"
$DB_TIER         = "db-f1-micro"
$CLOUDSQL_CONN   = $env:GCP_PROJECT_ID + ":" + $env:GCP_REGION + ":" + $CLOUDSQL_INST

# Enable APIs
Write-Host "  Enabling GCP APIs..."
gcloud services enable artifactregistry.googleapis.com sqladmin.googleapis.com run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null

# Artifact Registry (shared repo - works for both services)
Write-Host "  Setting up Artifact Registry..."
$repoExists = gcloud artifacts repositories describe "${ARTIFACT_REPO}" --location="$env:GCP_REGION" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null; $repoExists = ($LASTEXITCODE -eq 0)
if (-not $repoExists) {
    gcloud artifacts repositories create "${ARTIFACT_REPO}" --repository-format=docker --location="$env:GCP_REGION" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null
} else {
    Write-Host "    Already exists, skipping."
}

# Cloud SQL
Write-Host "  Setting up Cloud SQL PostgreSQL..."
$sqlExists = gcloud sql instances describe "${CLOUDSQL_INST}" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null; $sqlExists = ($LASTEXITCODE -eq 0)
if (-not $sqlExists) {
    gcloud sql instances create "${CLOUDSQL_INST}" --database-version=POSTGRES_15 --tier="${DB_TIER}" --region="$env:GCP_REGION" --storage-size=10 --storage-type=SSD --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null
} else {
    Write-Host "    Already exists, skipping."
}

# Database
$dbExists = gcloud sql databases describe "${DB_NAME}" --instance="${CLOUDSQL_INST}" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null; $dbExists = ($LASTEXITCODE -eq 0)
if (-not $dbExists) {
    gcloud sql databases create "${DB_NAME}" --instance="${CLOUDSQL_INST}" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null
} else {
    Write-Host "    Database already exists, skipping."
}

# DB User
$userExists = gcloud sql users list --instance="${CLOUDSQL_INST}" --project="$env:GCP_PROJECT_ID" --format="value(name)" 2>&1 | Out-Null; $userExists = ($LASTEXITCODE -eq 0) -and ((gcloud sql users list --instance="${CLOUDSQL_INST}" --project="$env:GCP_PROJECT_ID" --format="value(name)" 2>&1) -match "^${DB_USER}$")
if (-not $userExists) {
    gcloud sql users create "${DB_USER}" --instance="${CLOUDSQL_INST}" --password="$env:DB_PASSWORD" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null
} else {
    Write-Host "    DB user already exists, updating password..."
    gcloud sql users set-password "${DB_USER}" --instance="${CLOUDSQL_INST}" --password="$env:DB_PASSWORD" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null
}

# Secret Manager
Write-Host "  Storing DB password in Secret Manager (${'$'}SECRET_ID = ${SECRET_ID})..."
$secretExists = gcloud secrets describe "${SECRET_ID}" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null; $secretExists = ($LASTEXITCODE -eq 0)
$secretTmpFile = Join-Path $env:TEMP "${SERVICE_NAME}-secret.tmp"
[System.IO.File]::WriteAllText($secretTmpFile, $env:DB_PASSWORD, (New-Object System.Text.UTF8Encoding $false))
if (-not $secretExists) {
    gcloud secrets create "${SECRET_ID}" --data-file="$secretTmpFile" --replication-policy="automatic" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null
} else {
    gcloud secrets versions add "${SECRET_ID}" --data-file="$secretTmpFile" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null
    Write-Host "    Secret already exists, updated with new value."
}
Remove-Item $secretTmpFile -Force

# Service Account
Write-Host "  Setting up service account..."
$saExists = gcloud iam service-accounts describe "${SA_EMAIL}" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null; $saExists = ($LASTEXITCODE -eq 0)
if (-not $saExists) {
    gcloud iam service-accounts create "${SA_NAME}" --display-name="Orchestration Center Service Account" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null
} else {
    Write-Host "    Service account already exists, skipping."
}

# IAM bindings (idempotent, gcloud handles duplicates silently)
gcloud projects add-iam-policy-binding "$env:GCP_PROJECT_ID" --member="serviceAccount:${SA_EMAIL}" --role="roles/cloudsql.client" --condition=None 2>&1 | Out-Null
gcloud secrets add-iam-policy-binding "${SECRET_ID}" --member="serviceAccount:${SA_EMAIL}" --role="roles/secretmanager.secretAccessor" --project="$env:GCP_PROJECT_ID" 2>&1 | Out-Null

Write-Host "  Setup done!"
Write-Host ""

# ── Step 6: Deploy to Cloud Run ─────────────────────────────────────────────
Write-Host "[6/7] Deploying to Cloud Run (building & deploying, ~5 minutes)..."
Write-Host ""

# Build the env vars string separately to ensure correct expansion
$envVars = "PERSISTENCE_MODE=postgresql"
$envVars += ",DB_HOST=/cloudsql/$CLOUDSQL_CONN"
$envVars += ",DB_PORT=5432"
$envVars += ",DB_NAME=$DB_NAME"
$envVars += ",DB_USERNAME=$DB_USER"
$envVars += ",DB_PASSWORD=$env:DB_PASSWORD"
$envVars += ",ORCH_IP=0.0.0.0"
$envVars += ",ORCH_ENABLE_HTTPS=false"
$envVars += ",ORCH_FORWARDED_ALLOW_IPS=*"

if ($REGISTRY_URL) {
    $envVars += ",AGENT_REGISTRY_URL=$REGISTRY_URL"
}

if ($LLM_CHAT_MODEL) {
    $envVars += ",LLM_CHAT_MODEL=$LLM_CHAT_MODEL"
}
if ($LLM_CHAT_API_KEY) {
    $envVars += ",LLM_CHAT_API_KEY=$LLM_CHAT_API_KEY"
}
if ($LLM_CHAT_URL) {
    $envVars += ",LLM_CHAT_URL=$LLM_CHAT_URL"
}

# A2A-T SDK LLM config (derived from chat model config for consistency)
if ($LLM_CHAT_API_KEY) {
    # A2A-T SDK client name, not the model vendor: the SDK registers `openai`
    # in every process, so it is the only value every component accepts.
    $a2atProvider = "openai"
    # Derive base URL from chat URL (strip /chat/completions suffix)
    $a2atBaseUrl = $LLM_CHAT_URL
    if ($a2atBaseUrl -match "/chat/completions$") {
        $a2atBaseUrl = $a2atBaseUrl -replace "/chat/completions$", ""
    }
    $envVars += ",A2AT_LLM_PROVIDER=$a2atProvider"
    $envVars += ",A2AT_LLM_MODEL=$LLM_CHAT_MODEL"
    $envVars += ",A2AT_LLM_API_KEY=$LLM_CHAT_API_KEY"
    $envVars += ",A2AT_LLM_BASE_URL=$a2atBaseUrl"
}

Write-Host "  DB_HOST: /cloudsql/$CLOUDSQL_CONN"
if ($REGISTRY_URL) {
    Write-Host "  AGENT_REGISTRY_URL: $REGISTRY_URL"
}

$deployResult = gcloud run deploy "${SERVICE_NAME}" `
  --source=. `
  --region="$env:GCP_REGION" `
  --platform=managed `
  --allow-unauthenticated `
  --memory="1Gi" `
  --cpu="1" `
  --max-instances="10" `
  --concurrency=80 `
  --timeout=300 `
  --port=5001 `
  --service-account="${SA_EMAIL}" `
  --add-cloudsql-instances="${CLOUDSQL_CONN}" `
  --set-env-vars="$envVars" `
  --project="$env:GCP_PROJECT_ID"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "===================================================================="
    Write-Host "  DEPLOYMENT FAILED!"
    Write-Host "===================================================================="
    Write-Host ""
    Write-Host "  Check the build logs in the GCP Console:"
    Write-Host "    https://console.cloud.google.com/cloud-build/builds?project=$env:GCP_PROJECT_ID"
    Write-Host ""
    Write-Host "  Then re-run: .\deploy-all.ps1"
    Write-Host "===================================================================="
    exit 1
}

# ── Step 7: Result ───────────────────────────────────────────────────────────
$SERVICE_URL = gcloud run services describe "${SERVICE_NAME}" --region="$env:GCP_REGION" --format="value(status.url)" --project="$env:GCP_PROJECT_ID"

Write-Host ""
Write-Host "===================================================================="
Write-Host "  DEPLOYMENT SUCCESSFUL!"
Write-Host "===================================================================="
Write-Host ""
Write-Host "  Service URL: ${SERVICE_URL}"
Write-Host ""
Write-Host "  Verify it works:"
Write-Host "    Invoke-RestMethod -Uri `"${SERVICE_URL}/rest/v1/orchestrate/agent-cards`""
Write-Host ""
Write-Host "  API endpoints (Internal):"
Write-Host "    POST   ${SERVICE_URL}/rest/v1/orchestrate/parse-pdf"
Write-Host "    POST   ${SERVICE_URL}/rest/v1/orchestrate/generate-from-preflow"
Write-Host "    POST   ${SERVICE_URL}/rest/v1/orchestrate/generate-from-intent"
Write-Host "    POST   ${SERVICE_URL}/rest/v1/orchestrate/retrieve-by-intent"
Write-Host "    GET    ${SERVICE_URL}/rest/v1/orchestrate/execute?psop_id=<id>"
Write-Host "    GET    ${SERVICE_URL}/rest/v1/orchestrate/agent-cards"
Write-Host ""
Write-Host "  API endpoints (External):"
Write-Host "    POST   ${SERVICE_URL}/api/v1/orchestrate/sop"
Write-Host "    POST   ${SERVICE_URL}/api/v1/orchestrate/intent"
Write-Host "    POST   ${SERVICE_URL}/api/v1/orchestrate/search"
Write-Host "    POST   ${SERVICE_URL}/api/v1/orchestrate/execute"
Write-Host ""
if ($REGISTRY_URL) {
    Write-Host "  Linked Registry Center:"
    Write-Host "    ${REGISTRY_URL}"
    Write-Host ""
}
Write-Host "  To update the service later, just run:"
Write-Host "    .\deploy-all.ps1"
Write-Host "  (it will skip already-created resources and re-deploy)"
Write-Host "===================================================================="
