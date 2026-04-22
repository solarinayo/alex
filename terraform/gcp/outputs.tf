output "backend_service_url" {
  description = "Alex backend Cloud Run URL"
  value       = google_cloud_run_v2_service.backend.uri
}

output "frontend_service_url" {
  description = "Alex frontend Cloud Run URL"
  value       = google_cloud_run_v2_service.frontend.uri
}

output "artifact_registry" {
  description = "Artifact Registry Docker base path"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}

output "uploads_bucket" {
  description = "Uploads bucket name"
  value       = google_storage_bucket.uploads.name
}

output "cloudsql_connection_name" {
  description = "Cloud SQL instance connection name"
  value       = google_sql_database_instance.postgres.connection_name
}

output "wif_provider" {
  description = "Workload Identity Federation provider name"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "app_deployer_service_account" {
  description = "GitHub app deployer service account"
  value       = google_service_account.app_deployer.email
}

output "infra_deployer_service_account" {
  description = "GitHub infra deployer service account"
  value       = google_service_account.infra_deployer.email
}

output "db_password_secret_name" {
  description = "Secret Manager name for DB password"
  value       = google_secret_manager_secret.db_password.name
}

output "openai_secret_name" {
  description = "Secret Manager name for OpenAI API key"
  value       = google_secret_manager_secret.openai_api_key.name
}
