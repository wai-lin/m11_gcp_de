import os
import re
import pandas as pd

from google.cloud import bigquery
from google.api_core.exceptions import NotFound
from src.google import get_storage_bucket


def to_dict_safe(model):
    """Convert Pydantic model to dict."""
    try:
        return model.model_dump()
    except Exception:
        return dict(model)


def upload_file_to_gcs(bucket_name: str, source_file: str, dest_path: str) -> str:
    """Upload file to GCS and return gs:// URI."""
    _, bucket = get_storage_bucket(bucket_name=bucket_name)
    blob = bucket.blob(dest_path)
    blob.upload_from_filename(source_file)
    return f"gs://{bucket_name}/{dest_path}"


def ensure_bq_dataset(bq_client: bigquery.Client, dataset_id: str) -> None:
    """Ensure BigQuery dataset exists."""
    try:
        bq_client.get_dataset(dataset_id)
    except Exception:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = os.getenv("BQ_LOCATION", "asia-southeast1")
        bq_client.create_dataset(dataset)
        print(f"Created BigQuery dataset {dataset_id}")


def _build_load_schema(bq_client: bigquery.Client, table_id: str, df: pd.DataFrame) -> list[bigquery.SchemaField]:
    try:
        table = bq_client.get_table(table_id)
        schema = list(table.schema)
        existing_fields = {field.name for field in schema}
    except NotFound:
        schema = []
        existing_fields = set()

    for column in df.columns:
        if column not in existing_fields:
            schema.append(bigquery.SchemaField(column, "STRING", mode="NULLABLE"))

    return schema


def load_csv_to_bq(bq_client: bigquery.Client, gcs_uri: str, table_id: str, df: pd.DataFrame) -> None:
    """Load CSV from GCS into BigQuery table."""
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=False,
        allow_quoted_newlines=True,
        allow_jagged_rows=False,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job_config.schema = _build_load_schema(bq_client, table_id, df)
    job_config.schema_update_options = [
        bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION
    ]
    load_job = bq_client.load_table_from_uri(
        gcs_uri, table_id, job_config=job_config)
    load_job.result()
    table = bq_client.get_table(table_id)
    print(f"Loaded {table.num_rows} rows into {table_id}")


def sanitize_bq_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Sanitize DataFrame column names for BigQuery compatibility."""
    renamed = []
    seen = {}
    for col in df.columns:
        clean = re.sub(r"[^A-Za-z0-9_]", "_", str(col))
        clean = re.sub(r"_+", "_", clean).strip("_")
        if not clean:
            clean = "col"
        if clean[0].isdigit():
            clean = f"col_{clean}"
        count = seen.get(clean, 0)
        seen[clean] = count + 1
        if count:
            clean = f"{clean}_{count}"
        renamed.append(clean)

    df = df.copy()
    df.columns = renamed
    return df
