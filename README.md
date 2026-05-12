# Coursera to BigQuery Pipeline

This project fetches course data from the Coursera GraphQL API, transforms the results into a tabular format, uploads a CSV to Google Cloud Storage, and loads the data into BigQuery.

It supports two entry modes:

- A local CLI run through `uv run src/main.py`
- An HTTP Cloud Function entrypoint named `coursera_pipeline`

## What the pipeline does

1. Calls the Coursera GraphQL search endpoint.
2. Normalizes nested course data into a pandas DataFrame.
3. Writes the CSV to `/tmp/courses.csv`.
4. Uploads the CSV to a GCS bucket.
5. Loads the CSV into a BigQuery table.

## Repository layout

```text
.
├── requirements.txt
├── pyproject.toml
├── main.py
└── src/
		├── main.py
		├── pipeline_fn.py
		└── gcp/
				├── google_auth.py
				└── google_storage.py
```

## Prerequisites

- Python 3.11 or newer locally
- A Google Cloud project with these APIs enabled:
	- Cloud Build
	- Cloud Functions
	- BigQuery
	- Cloud Storage
- Access to a GCS bucket and BigQuery dataset

## Environment variables

Set these values locally or in your Cloud Function / Cloud Build configuration:

- `GCP_PROJECT_ID`: Google Cloud project ID
- `GCS_BUCKET_NAME`: destination bucket name
- `GCS_DESTINATION_BLOB`: optional object path in the bucket, defaults to `coursera_exports/courses.csv`
- `SERVICE_ACCOUNT_EMAIL`: service account to impersonate locally
- `SEARCH_QUERY`: Coursera search term, defaults to `python`
- `SEARCH_LIMIT`: number of results to request, defaults to `100`

## Local setup

Create and activate a virtual environment, then install dependencies:

```bash
source .venv/bin/activate
uv install
```

If you are running locally against Google Cloud resources, make sure Application Default Credentials are available:

```bash
gcloud auth application-default login
```

## Run locally

### CLI mode

Run the full pipeline from the command line:

```bash
export GCP_PROJECT_ID="your-project-id"
export GCS_BUCKET_NAME="your-bucket-name"
export SEARCH_QUERY="python"
uv run src/main.py
```

### HTTP Cloud Function locally

If you want to test the Cloud Function handler with Functions Framework:

```bash
uv pip install functions-framework
functions-framework --target=coursera_pipeline --debug
```

Send a request:

```bash
curl -X POST http://127.0.0.1:8080 \
	-H "Content-Type: application/json" \
	-d '{"search_query":"data science","search_limit":25}'
```

## Cloud Function deployment

The exported function name is `coursera_pipeline`.

For Cloud Build / Buildpacks, the source must expose a root-level `main.py` or set `GOOGLE_FUNCTION_SOURCE` to the directory that contains the entrypoint module. If your code stays in `src/`, you can either:

- add a thin wrapper `main.py` at repo root, or
- configure `GOOGLE_FUNCTION_SOURCE=src`

Suggested Cloud Function settings:

- Runtime: Python 3.11
- Entry point / function target: `coursera_pipeline`
- Trigger: HTTP
- Memory: 512 MB or higher
- Timeout: 300 seconds or higher

Recommended environment variables in the function:

- `GCP_PROJECT_ID`
- `GCS_BUCKET_NAME`
- `GCS_DESTINATION_BLOB`
- `SEARCH_QUERY`
- `SEARCH_LIMIT`

## Cloud Build branch deployment

If you want automatic deployment from a non-`main` branch in GitHub:

1. Create a Cloud Build trigger for the branch you want.
2. Point the trigger at `cloudbuild.yaml` in the repo root.
3. Make sure the branch filter matches only the branch you want to deploy.

If you use Cloud Build to deploy the function, the Cloud Build service account needs permissions to deploy the function and write to the resources it uses.

## Troubleshooting

- If the buildpack says it cannot find `main.py`, either add a root-level wrapper or set `GOOGLE_FUNCTION_SOURCE` correctly.
- If authentication fails locally, use `gcloud auth application-default login` or set `GOOGLE_APPLICATION_CREDENTIALS`.
- If BigQuery load jobs fail, confirm the dataset exists and the service account has the right BigQuery roles.
- If GCS uploads fail, confirm the bucket exists and the service account can write objects.

## Notes

- The pipeline uses `/tmp/courses.csv` because Cloud Functions only provides writable local storage in `/tmp`.
- The Coursera API response can change over time, so the transformation code is defensive about missing fields.
