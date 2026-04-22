resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = var.artifact_repository_id
  format        = "DOCKER"
  description   = "Docker images for Alex services"

  depends_on = [google_project_service.apis]
}
