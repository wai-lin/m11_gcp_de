#!/usr/bin/env bash
set -euo pipefail

# prebuild.sh
# Idempotent helper to create required GCP resources for CI/CD
# - Artifact Registry repo
# - Grants required IAM roles to Cloud Build SA
# - Cloud Run Job (creates if missing)
# - Cloud Build trigger (attempts to create; requires GitHub connection)

PROJECT=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$PROJECT" ]; then
  echo "No GCP project configured. Run 'gcloud config set project <PROJECT_ID>' and retry." >&2
  exit 1
fi

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='get(projectNumber)')
REGION=${REGION:-asia-southeast1}
REPO_OWNER=${REPO_OWNER:-wai-lin}
REPO_NAME=${REPO_NAME:-m11_gcp_de}
BRANCH=${BRANCH:-tiktok_pipeline}
AR_REPO=${AR_REPO:-tiktok-jobs}
IMAGE=${IMAGE:-tiktok-scraper}
JOB_NAME=${JOB_NAME:-scrape-tiktok}
BUILD_CONFIG=${BUILD_CONFIG:-cloudbuild.yaml}
TRIGGER_NAME=${TRIGGER_NAME:-tiktok-scraper-trigger}

IMAGE_FULL="${REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/${IMAGE}:latest"

echo "Project: $PROJECT ($PROJECT_NUMBER)"
echo "Region: $REGION"
echo "Artifact Registry repo: $AR_REPO"
echo "Cloud Run job: $JOB_NAME"
echo "Build trigger: $TRIGGER_NAME (repo ${REPO_OWNER}/${REPO_NAME} branch ${BRANCH})"

ensure_artifact_repo() {
  if gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1; then
    echo "Artifact Registry repository '$AR_REPO' already exists in $REGION."
  else
    echo "Creating Artifact Registry repository '$AR_REPO'..."
    gcloud artifacts repositories create "$AR_REPO" \
      --repository-format=docker \
      --location="$REGION" \
      --description="TikTok scraper container images"
    echo "Created repository $AR_REPO."
  fi
}

grant_cloudbuild_roles() {
  CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
  echo "Ensuring Cloud Build SA ($CB_SA) has necessary roles..."
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$CB_SA" \
    --role="roles/artifactregistry.writer" || true
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$CB_SA" \
    --role="roles/run.admin" || true
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$CB_SA" \
    --role="roles/iam.serviceAccountUser" || true
  echo "IAM bindings applied (may require OWNER privileges)."
}

ensure_cloud_run_job() {
  if gcloud run jobs describe "$JOB_NAME" --region="$REGION" >/dev/null 2>&1; then
    echo "Cloud Run job '$JOB_NAME' already exists in $REGION."
  else
    echo "Creating Cloud Run job '$JOB_NAME' with image $IMAGE_FULL ..."
    ENV_VARS=("TIKTOK_USER_ID=${TIKTOK_USER_ID:-noraspersonalspace2510}")
    if [ -n "${RAPIDAPI_KEY:-}" ]; then
      ENV_VARS+=("RAPIDAPI_KEY=${RAPIDAPI_KEY}")
    fi
    gcloud run jobs create "$JOB_NAME" \
      --image="$IMAGE_FULL" \
      --region="$REGION" \
      --set-env-vars="$(IFS=,; echo "${ENV_VARS[*]}")" \
      --quiet || {
        echo "Warning: job creation failed. This can happen if the image does not yet exist in Artifact Registry." >&2
        echo "You can create the job manually after first successful build, or re-run this script after a push." >&2
      }
  fi
}

ensure_build_trigger() {
  if gcloud builds triggers list --region="$REGION" --format='value(name)' | grep -x "$TRIGGER_NAME" >/dev/null 2>&1; then
    echo "Build trigger '$TRIGGER_NAME' already exists."
  else
    echo "Creating Cloud Build trigger '$TRIGGER_NAME'..."
    if gcloud builds triggers create github \
      --name="$TRIGGER_NAME" \
      --repo-name="$REPO_NAME" \
      --repo-owner="$REPO_OWNER" \
      --branch-pattern="^${BRANCH}$" \
      --build-config="$BUILD_CONFIG" \
      --region="$REGION"; then
      echo "Trigger created."
    else
      echo "Failed to create trigger. If this fails because the repository isn't connected, run:" >&2
      echo "  gcloud builds connect --repository-format=GITHUB --source-dir=. --name=${REPO_NAME} --region=${REGION}" >&2
      echo "Or connect the repo via the Cloud Build console: https://console.cloud.google.com/cloud-build/triggers" >&2
    fi
  fi
}

main() {
  ensure_artifact_repo
  grant_cloudbuild_roles
  ensure_cloud_run_job
  ensure_build_trigger

  cat <<EOF
Prebuild finished.
- Artifact Registry: ${AR_REPO} (region ${REGION})
- Cloud Run job: ${JOB_NAME}
- Cloud Build trigger: ${TRIGGER_NAME} (repo: ${REPO_OWNER}/${REPO_NAME}, branch: ${BRANCH})

Notes:
- If trigger creation failed, ensure the GitHub repository is connected to Cloud Build (via UI or 'gcloud builds connect').
- You may need OWNER permissions to update IAM bindings.
EOF
}

main
