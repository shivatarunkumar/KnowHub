# KnowHub on BigQuery: the dataset and every table the BigQuery API (backend-bq/) uses.
#
# Each table is described by one file in tables/<name>.json: its schema, primary key,
# clustering and (optionally) partitioning. Adding a table means adding a file; nothing
# here changes. The tables mirror database/postgres/migrations; see project-bq.md for the
# few deliberate differences (counters computed on read, no generated search column).
#
# Run it through `make setup-bq` rather than by hand: that script also imports tables
# that already exist (a second machine, or a lost state file) and loads the seed rows.
#
#   terraform init
#   terraform apply -var project=bigquerytarun -var dataset=knowhub -var location=europe-west2

terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  # State stays in this folder (git-ignored). A fresh machine rebuilds it: make setup-bq
  # imports whatever already exists in BigQuery before applying.
}

variable "project" {
  description = "GCP project that owns the dataset (BQ_DB_PROJECT, else GCP_PROJECT_ID)"
  type        = string
}

variable "dataset" {
  description = "Dataset holding the KnowHub tables (BQ_DB_DATASET)"
  type        = string
  default     = "knowhub"
}

variable "location" {
  description = "Dataset location (BQ_DB_LOCATION). Cannot change once the dataset exists."
  type        = string
  default     = "europe-west2"
}

variable "deletion_protection" {
  description = "Refuse to delete tables on destroy or replace. Keep true for anything with real data."
  type        = bool
  default     = true
}

provider "google" {
  project = var.project
}

locals {
  table_files = fileset("${path.module}/tables", "*.json")
  tables = {
    for file in local.table_files :
    trimsuffix(file, ".json") => jsondecode(file("${path.module}/tables/${file}"))
  }
}

resource "google_bigquery_dataset" "knowhub" {
  dataset_id  = var.dataset
  location    = var.location
  description = "KnowHub application data (RUN_ON=BQ). Tables are defined in infra/gcs/bq/tables."

  labels = {
    app = "knowhub"
  }
}

resource "google_bigquery_table" "table" {
  for_each = local.tables

  dataset_id          = google_bigquery_dataset.knowhub.dataset_id
  table_id            = each.key
  description         = each.value.description
  deletion_protection = var.deletion_protection

  schema     = jsonencode(each.value.schema)
  clustering = each.value.clustering

  dynamic "time_partitioning" {
    for_each = try([each.value.time_partitioning], [])
    content {
      type  = time_partitioning.value.type
      field = time_partitioning.value.field
    }
  }

  # BigQuery does not enforce keys; declaring them documents the model and lets the
  # optimizer prune joins. Uniqueness is enforced by the API (see project-bq.md).
  table_constraints {
    primary_key {
      columns = each.value.primary_key
    }
  }

  labels = {
    app = "knowhub"
  }
}

output "dataset" {
  value = "${var.project}.${google_bigquery_dataset.knowhub.dataset_id}"
}

output "tables" {
  value = sort(keys(google_bigquery_table.table))
}
