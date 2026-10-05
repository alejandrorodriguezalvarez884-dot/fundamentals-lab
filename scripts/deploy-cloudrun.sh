#!/usr/bin/env bash
# Deploys the production image (site + API in one container) to Google Cloud Run. Cloud Build
# builds the Dockerfile remotely, so Docker is not needed locally. The API keys go to Secret
# Manager, and a Cloud Storage bucket keeps reports, readings and the spending ledger. The
# service scales to zero: it costs nothing while nobody uses it.
#
# Requirements: the gcloud CLI logged in on a project with billing enabled, and .env with
# ANTHROPIC_API_KEY, FMP_API_KEY and SEC_USER_AGENT.
#
# Optional overrides: GCP_PROJECT, GCP_REGION, SERVICE_NAME, MAX_INSTANCES, READING_DAILY_MAX_USD,
# READING_TOTAL_MAX_USD, READING_MODEL.
set -euo pipefail

cd "$(dirname "$0")/.."

fail() {
  echo "error: $*" >&2
  exit 1
}

command -v gcloud >/dev/null || fail "gcloud is not installed."

GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
GCP_REGION="${GCP_REGION:-europe-west1}"
SERVICE_NAME="${SERVICE_NAME:-fundamentals-lab}"
MAX_INSTANCES="${MAX_INSTANCES:-2}"
# Most the AI reading may spend in one day (UTC) and over the service's whole life, in USD.
READING_DAILY_MAX_USD="${READING_DAILY_MAX_USD:-0.50}"
READING_TOTAL_MAX_USD="${READING_TOTAL_MAX_USD:-5.00}"
READING_MODEL="${READING_MODEL:-claude-opus-5-5}"
ENV_FILE=".env"

[[ -n "$GCP_PROJECT" ]] || fail "No GCP project selected. Run 'gcloud init' or set GCP_PROJECT."
[[ -f "$ENV_FILE" ]] || fail "$ENV_FILE not found."
BUCKET="${FUNDAMENTALS_BUCKET:-${GCP_PROJECT}-fundamentals-lab}"

# Read single values instead of sourcing the file, and drop the quotes around them.
env_value() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' || true; }
ANTHROPIC_KEY="$(env_value ANTHROPIC_API_KEY)"
FMP_KEY="$(env_value FMP_API_KEY)"
SEC_USER_AGENT="$(env_value SEC_USER_AGENT)"
[[ -n "$ANTHROPIC_KEY" ]] || fail "ANTHROPIC_API_KEY is empty in $ENV_FILE."
[[ -n "$FMP_KEY" ]] || fail "FMP_API_KEY is empty in $ENV_FILE."
[[ "$SEC_USER_AGENT" == *@* ]] || fail "SEC_USER_AGENT in $ENV_FILE needs a contact email."

gcp() { gcloud --project "$GCP_PROJECT" --quiet "$@"; }

echo "→ Enabling APIs in $GCP_PROJECT"
gcp services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com storage.googleapis.com

# Source deploys build with, and run as, the Compute Engine default service account.
PROJECT_NUMBER="$(gcp projects describe "$GCP_PROJECT" --format='value(projectNumber)')"
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcp projects add-iam-policy-binding "$GCP_PROJECT" \
  --member "serviceAccount:$SERVICE_ACCOUNT" --role roles/run.builder --condition=None >/dev/null

# One secret per key. A version is added only when the key changed.
put_secret() {
  local name="$1" value="$2"
  if ! gcp secrets describe "$name" >/dev/null 2>&1; then
    gcp secrets create "$name" --replication-policy automatic >/dev/null
  fi
  if [[ "$(gcp secrets versions access latest --secret "$name" 2>/dev/null || true)" != "$value" ]]; then
    printf '%s' "$value" | gcp secrets versions add "$name" --data-file=- >/dev/null
  fi
  gcp secrets add-iam-policy-binding "$name" \
    --member "serviceAccount:$SERVICE_ACCOUNT" --role roles/secretmanager.secretAccessor >/dev/null
}
echo "→ Secrets"
put_secret fundamentals-lab-anthropic-api-key "$ANTHROPIC_KEY"
put_secret fundamentals-lab-fmp-api-key "$FMP_KEY"

echo "→ Bucket gs://$BUCKET"
if ! gcp storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  gcp storage buckets create "gs://$BUCKET" --location "$GCP_REGION" --uniform-bucket-level-access \
    --public-access-prevention >/dev/null
fi
gcp storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member "serviceAccount:$SERVICE_ACCOUNT" --role roles/storage.objectAdmin >/dev/null

echo "→ Building with Cloud Build and deploying '$SERVICE_NAME' to $GCP_REGION (a few minutes)"
# "^|^" makes "|" the separator: the SEC user agent has spaces and an "@", and could have commas.
gcp run deploy "$SERVICE_NAME" \
  --source . \
  --region "$GCP_REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --cpu 1 \
  --memory 1Gi \
  --min-instances 0 \
  --max-instances "$MAX_INSTANCES" \
  --timeout 120 \
  --set-secrets "ANTHROPIC_API_KEY=fundamentals-lab-anthropic-api-key:latest,FMP_API_KEY=fundamentals-lab-fmp-api-key:latest" \
  --set-env-vars "^|^SEC_USER_AGENT=$SEC_USER_AGENT|FUNDAMENTALS_BUCKET=$BUCKET|READING_DAILY_MAX_USD=$READING_DAILY_MAX_USD|READING_TOTAL_MAX_USD=$READING_TOTAL_MAX_USD|READING_MODEL=$READING_MODEL"

URL="$(gcp run services describe "$SERVICE_NAME" --region "$GCP_REGION" --format 'value(status.url)')"
if curl -fsS "$URL/api/health" >/dev/null; then
  echo "✓ Deployed: $URL"
else
  fail "Deployed, but $URL/api/health failed. Logs: gcloud run services logs read $SERVICE_NAME --region $GCP_REGION"
fi
