#!/usr/bin/env bash
# Deploy Campus Bites to Google Cloud Run.
#   ./deploy.sh                 # uses your current gcloud project, region us-central1
#   REGION=us-west1 ./deploy.sh
set -euo pipefail

SERVICE="${SERVICE:-campus-bites}"
REGION="${REGION:-us-central1}"

# A stable secret keeps people logged in across redeploys. It is generated once
# and stored in .secret_key (ignored by git).
if [[ ! -f .secret_key ]]; then
  python3 -c "import secrets; print(secrets.token_hex(32))" > .secret_key
fi
SECRET_KEY="$(cat .secret_key)"

# --max-instances 1: every visitor talks to the same SQLite file.
# --min-instances 1: the instance (and the data in it) is not shut down when idle.
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --min-instances 1 \
  --max-instances 1 \
  --memory 512Mi \
  --set-env-vars "SECRET_KEY=${SECRET_KEY}"

gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)'
