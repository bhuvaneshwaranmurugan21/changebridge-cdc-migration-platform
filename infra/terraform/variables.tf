variable "aws_region" {
  type        = string
  description = "AWS region for the reference deployment."
  default     = "ap-south-1"
}

variable "environment" {
  type        = string
  description = "Short environment name."
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod"
  }
}

variable "source_endpoint_arn" {
  type        = string
  description = "Existing DMS PostgreSQL source endpoint ARN; empty skips the task."
  default     = ""
}

variable "replication_instance_arn" {
  type        = string
  description = "Existing DMS replication instance ARN; empty skips the task."
  default     = ""
}

variable "alarm_topic_arn" {
  type        = string
  description = "Optional SNS topic ARN for alarm actions."
  default     = ""
}
