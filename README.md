# TikTok Pipeline

## Deploying to Google Cloud

Prerequisites:
- `gcloud` CLI installed and authenticated.
- Billing enabled for the target project.
- Set up a Google Cloud Project and enable APIs (see step 2).

Quick deploy steps:

1. Configure environment variables:

```bash
export PROJECT_ID=your-project-id
export REGION=asia-southeast1
gcloud config set project "$PROJECT_ID"
```

2. Enable required APIs:

```bash
gcloud services enable \
	cloudfunctions.googleapis.com \
	cloudbuild.googleapis.com \
	cloudscheduler.googleapis.com \
	eventarc.googleapis.com \
	pubsub.googleapis.com \
	storage.googleapis.com \
	bigquery.googleapis.com
```

3. Ensure `requirements.txt` is present and in sync with your `uv` lockfile. If you change dependencies, run:

```bash
./scripts/uv-add-sync.sh '<package-spec>'
# or regenerate from lockfile:
uv export --format requirements.txt -o requirements.txt --no-dev
```

4. Submit the Cloud Build pipeline (deploys the functions, creates buckets and scheduler):

```bash
gcloud builds submit --config cloudbuild.yaml .
```

5. Verify deployed resources:

```bash
gcloud functions list --region="$REGION"
gcloud scheduler jobs list --location="$REGION"
gsutil ls gs://"$PROJECT_ID"-tiktok-raw
```

6. Trigger a manual extraction test:

```bash
EXTRACT_URL=$(gcloud functions describe scrape-tiktok-extract --gen2 --region="$REGION" --format='value(serviceConfig.uri)')
curl -X POST "$EXTRACT_URL" -H 'Content-Type: application/json' -d '{}'
```

If the scheduler job was created successfully it will call the same URL on the schedule.

Troubleshooting notes:
- If Eventarc or Cloud Functions fail to create triggers, ensure the Eventarc service account and the GCS service account have `roles/storage.viewer` on the buckets and `roles/pubsub.publisher` at the project level.
- If Cloud Scheduler job creation fails with an OAuth error, the pipeline uses OIDC to call the Cloud Function URL (no action needed when using the provided `cloudbuild.yaml`).

See `cloudbuild.yaml` for the exact deployment steps and environment variables.
