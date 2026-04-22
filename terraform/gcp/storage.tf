resource "google_storage_bucket" "uploads" {
  name                        = var.uploads_bucket_name != "" ? var.uploads_bucket_name : "${var.project_id}-alex-uploads"
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true

  depends_on = [google_project_service.apis]
}
