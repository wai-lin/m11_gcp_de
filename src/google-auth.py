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


def impersonate():
    service_account_email = "hs2026de@hs2026de.iam.gserviceaccount.com"
    print(
        f"Impersonation configured for {service_account_email} in project {project}"
    )
    creds, project, target_creds = impersonated_service_account(
        service_account_email
    )
    return service_account_email, creds, project, target_creds
