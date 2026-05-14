#!/usr/bin/env bash
set -euo pipefail

# prepare_etl_resources.sh
# Creates GCS bucket and BigQuery dataset used by ETL pipeline

PROJECT=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$PROJECT" ]; then
  echo "No GCP project configured. Run 'gcloud config set project <PROJECT_ID>' and retry." >&2
  exit 1
fi

REGION=${REGION:-asia-southeast1}
BUCKET=${BUCKET:-hsde_tiktok_scraper}
BQ_DATASET=${BQ_DATASET:-tiktok_scraper}
BQ_LOCATION=${BQ_LOCATION:-US}

echo "Project: $PROJECT"
echo "Creating bucket: $BUCKET (region: $REGION) if missing"
if gsutil ls -b "gs://$BUCKET" >/dev/null 2>&1; then
  echo "Bucket gs://$BUCKET already exists"
else
  gsutil mb -l "$REGION" "gs://$BUCKET"
  echo "Created bucket gs://$BUCKET"
fi

echo "Enabling required APIs: storage, bigquery, run"
gcloud services enable storage.googleapis.com bigquery.googleapis.com run.googleapis.com --project="$PROJECT"

echo "Creating BigQuery dataset: $BQ_DATASET (location: $BQ_LOCATION) if missing"
if bq --project_id="$PROJECT" ls --datasets | awk '{print $1}' | grep -x "$BQ_DATASET" >/dev/null 2>&1; then
  echo "Dataset $BQ_DATASET already exists"
else
  bq --location=$BQ_LOCATION mk --dataset "$PROJECT:$BQ_DATASET"
  echo "Created dataset $PROJECT:$BQ_DATASET"
fi

echo "Helpful next steps:
- Ensure Cloud Build service account has roles/artifactregistry.writer and roles/run.admin
- If using Cloud Run jobs, create the job once the container image is pushed."

echo "Done."
