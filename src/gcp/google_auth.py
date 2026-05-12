import os

import google.auth
from google.auth import impersonated_credentials
from google.auth.exceptions import DefaultCredentialsError


def impersonated_service_account(sa_email: str):
    try:
        creds, project = google.auth.default()
    except DefaultCredentialsError as exc:
        raise RuntimeError(
            "Application Default Credentials (ADC) not found. "
            "Run: gcloud auth application-default login"
        ) from exc

    target_creds = impersonated_credentials.Credentials(
        source_credentials=creds,
        target_principal=sa_email,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        lifetime=3600,
    )
    return creds, project, target_creds


def _running_on_cloud_functions() -> bool:
    # Cloud Functions environments expose one or more of these variables.
    return any(
        os.getenv(var)
        for var in ("K_SERVICE", "FUNCTION_TARGET", "FUNCTION_NAME")
    )


def get_auth():
    service_account_email = "hs2026de@hs2026de.iam.gserviceaccount.com"
    service_account_email = os.getenv(
        "SERVICE_ACCOUNT_EMAIL", service_account_email
    )

    if _running_on_cloud_functions():
        creds, project = google.auth.default()
        target_creds = creds
        print(f"Using default Cloud Functions credentials in project {project}")
    else:
        creds, project, target_creds = impersonated_service_account(
            service_account_email
        )
        print(
            f"Impersonation configured for {service_account_email} in project {project}"
        )

    # Return the effective credentials and project for use by callers
    return target_creds, project
