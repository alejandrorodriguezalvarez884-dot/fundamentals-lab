#!/usr/bin/env bash
# Deploys the production image (site + API in one container) to Google Cloud Run. Cloud Build
# builds the Dockerfile remotely, so Docker is not needed locally. The API keys go to Secret
# Manager, and a Cloud Storage bucket keeps reports, readings and the spending ledger. The
# service scales to zero: it costs nothing while nobody uses it.
#
# Requirements: the gcloud CLI logged in on a project with billing enabled, and .env with
# SEC_USER_AGENT. The numbers come from Yahoo Finance, which takes no key; MARKET_DATA=fmp in .env
# reads them from FMP instead, with FMP_API_KEY. The AI reading takes its Anthropic key from Secret Manager:
# ANTHROPIC_SECRET names the secret (default fundamentals-lab-anthropic-api-key). A key in
# ANTHROPIC_API_KEY is stored there first; with no key and no secret the reading stays off.
# HUB_URL (the Market Hub address) admits only people signed in there: the service reads the
# hub's session cookie with the hub's secret (Secret Manager: market-hub-session-secret).
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
MARKET_DATA="$(env_value MARKET_DATA)"
SEC_USER_AGENT="$(env_value SEC_USER_AGENT)"
HUB_URL="$(env_value HUB_URL)"
ANTHROPIC_SECRET="${ANTHROPIC_SECRET:-$(env_value ANTHROPIC_SECRET)}"
ANTHROPIC_SECRET="${ANTHROPIC_SECRET:-fundamentals-lab-anthropic-api-key}"
[[ -n "$FMP_KEY" || "$MARKET_DATA" != "fmp" ]] || fail "MARKET_DATA=fmp needs FMP_API_KEY in $ENV_FILE."
[[ "$SEC_USER_AGENT" == *@* ]] || fail "SEC_USER_AGENT in $ENV_FILE needs a contact email."

gcp() { gcloud --project "$GCP_PROJECT" --quiet "$@"; }

# Give the service's account a role on something, only if it does not have it yet. A policy is
# one document: two deploys writing it at the same moment collide ("concurrent policy changes"),
# and the second fails. Reading it first means that in the ordinary deploy nothing is written,
# so the services' deploys can run side by side.
#   grant projects "$GCP_PROJECT" roles/run.builder --condition=None
#   grant secrets my-secret roles/secretmanager.secretAccessor
#   grant "storage buckets" "gs://my-bucket" roles/storage.objectAdmin
grant() {
  local kind="$1" resource="$2" role="$3" member="serviceAccount:$SERVICE_ACCOUNT"
  shift 3
  # $kind is left unquoted on purpose: "storage buckets" is two words of the command. grep reads
  # the whole answer (no -q): leaving early would break the pipe, and that would read as "missing".
  if gcp $kind get-iam-policy "$resource" --flatten='bindings[].members' --format='value(bindings.role,bindings.members)' 2>/dev/null \
      | tr -d '\r' | grep -xF "$role"$'\t'"$member" >/dev/null; then
    return 0
  fi
  gcp $kind add-iam-policy-binding "$resource" --member "$member" --role "$role" "$@" >/dev/null
}

echo "→ Enabling APIs in $GCP_PROJECT"
gcp services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com storage.googleapis.com

# Source deploys build with, and run as, the Compute Engine default service account.
PROJECT_NUMBER="$(gcp projects describe "$GCP_PROJECT" --format='value(projectNumber)')"
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
grant projects "$GCP_PROJECT" roles/run.builder --condition=None

# One secret per key. A version is added only when the key changed.
put_secret() {
  local name="$1" value="$2"
  if ! gcp secrets describe "$name" >/dev/null 2>&1; then
    gcp secrets create "$name" --replication-policy automatic >/dev/null
  fi
  if [[ "$(gcp secrets versions access latest --secret "$name" 2>/dev/null || true)" != "$value" ]]; then
    printf '%s' "$value" | gcp secrets versions add "$name" --data-file=- >/dev/null
  fi
  grant secrets "$name" roles/secretmanager.secretAccessor
}
echo "→ Secrets"
SECRETS=""
if [[ -n "$FMP_KEY" ]]; then
  put_secret fundamentals-lab-fmp-api-key "$FMP_KEY"
  SECRETS="FMP_API_KEY=fundamentals-lab-fmp-api-key:latest"
fi
if [[ -n "$ANTHROPIC_KEY" ]]; then
  put_secret "$ANTHROPIC_SECRET" "$ANTHROPIC_KEY"
fi
if gcp secrets describe "$ANTHROPIC_SECRET" >/dev/null 2>&1; then
  grant secrets "$ANTHROPIC_SECRET" roles/secretmanager.secretAccessor
  SECRETS="$SECRETS,ANTHROPIC_API_KEY=$ANTHROPIC_SECRET:latest"
  echo "→ AI reading on, key from the secret $ANTHROPIC_SECRET"
else
  echo "note: no Anthropic key anywhere: the AI reading stays off."
fi
HUB_ENV=""
if [[ -n "$HUB_URL" ]]; then
  gcp secrets describe market-hub-session-secret >/dev/null 2>&1 || fail "HUB_URL is set but Market Hub's secret market-hub-session-secret does not exist. Deploy the hub first."
  grant secrets market-hub-session-secret roles/secretmanager.secretAccessor
  SECRETS="$SECRETS,HUB_SESSION_SECRET=market-hub-session-secret:latest"
  HUB_ENV="|HUB_URL=$HUB_URL"
  echo "→ Behind Market Hub's sign-in ($HUB_URL)"
fi

echo "→ Bucket gs://$BUCKET"
if ! gcp storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  gcp storage buckets create "gs://$BUCKET" --location "$GCP_REGION" --uniform-bucket-level-access \
    --public-access-prevention >/dev/null
fi
grant "storage buckets" "gs://$BUCKET" roles/storage.objectAdmin

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
  --set-secrets "${SECRETS#,}" \
  --set-env-vars "^|^SEC_USER_AGENT=$SEC_USER_AGENT|FUNDAMENTALS_BUCKET=$BUCKET|READING_DAILY_MAX_USD=$READING_DAILY_MAX_USD|READING_TOTAL_MAX_USD=$READING_TOTAL_MAX_USD|READING_MODEL=$READING_MODEL|MARKET_DATA=${MARKET_DATA:-yahoo}$HUB_ENV"

URL="$(gcp run services describe "$SERVICE_NAME" --region "$GCP_REGION" --format 'value(status.url)')"
if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
  echo "✓ Deployed: $URL"
else
  fail "Deployed, but $URL/api/health failed. Logs: gcloud run services logs read $SERVICE_NAME --region $GCP_REGION"
fi
