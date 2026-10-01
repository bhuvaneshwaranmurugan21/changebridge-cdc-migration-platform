variable "expected_account_id" {
  type    = string
  default = "UNASSIGNED"
  validation {
    condition     = var.expected_account_id == "UNASSIGNED" || can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be UNASSIGNED or a 12-digit account ID."
  }
}

variable "aws_region" {
  type    = string
  default = "UNASSIGNED"
}

variable "deployment_id" {
  type    = string
  default = "UNASSIGNED"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "runtime_artifact_bucket" {
  type    = string
  default = "UNASSIGNED"
}

variable "runtime_artifact_key" {
  type    = string
  default = "UNASSIGNED"
}

variable "runtime_artifact_sha256" {
  type    = string
  default = "UNASSIGNED"
}

variable "source_endpoint_arn" {
  type    = string
  default = "UNASSIGNED"
}

variable "replication_instance_arn" {
  type    = string
  default = "UNASSIGNED"
}

variable "alarm_topic_arn" {
  type    = string
  default = ""
}

variable "cost_center" {
  type    = string
  default = "UNASSIGNED"
}

variable "expires_at" {
  type    = string
  default = "UNASSIGNED"
}
