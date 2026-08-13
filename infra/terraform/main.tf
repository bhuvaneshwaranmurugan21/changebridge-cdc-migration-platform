data "aws_caller_identity" "current" {}

resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  name          = "changebridge-${var.environment}"
  bucket_prefix = "${local.name}-${data.aws_caller_identity.current.account_id}-${random_id.suffix.hex}"
  alarm_actions = var.alarm_topic_arn == "" ? [] : [var.alarm_topic_arn]
}

resource "aws_kms_key" "platform" {
  description             = "ChangeBridge generation, manifest, and evidence encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_alias" "platform" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.platform.key_id
}

resource "aws_s3_bucket" "landing" {
  bucket        = "${local.bucket_prefix}-landing"
  force_destroy = var.environment != "prod"
}

resource "aws_s3_bucket" "evidence" {
  bucket        = "${local.bucket_prefix}-evidence"
  force_destroy = var.environment != "prod"
}

resource "aws_s3_bucket_versioning" "landing" {
  bucket = aws_s3_bucket.landing.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "landing" {
  bucket = aws_s3_bucket.landing.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.platform.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.platform.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "landing" {
  bucket                  = aws_s3_bucket.landing.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket                  = aws_s3_bucket.evidence.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "generations" {
  name         = "${local.name}-generations"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "generation_id"

  attribute {
    name = "generation_id"
    type = "S"
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.platform.arn
  }
}

resource "aws_dynamodb_table" "active_pointer" {
  name         = "${local.name}-active-pointer"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "product_id"

  attribute {
    name = "product_id"
    type = "S"
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.platform.arn
  }
}

resource "aws_glue_catalog_database" "candidate" {
  name = replace("${local.name}-candidate", "-", "_")
}

resource "aws_cloudwatch_log_group" "orchestration" {
  name              = "/aws/vendedlogs/states/${local.name}"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.platform.arn
}

resource "aws_cloudwatch_metric_alarm" "cdc_lag" {
  alarm_name          = "${local.name}-cdc-lag"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CDCLatencySource"
  namespace           = "AWS/DMS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 30
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_actions
}

data "aws_iam_policy_document" "dms_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["dms.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dms_s3" {
  name               = "${local.name}-dms-s3"
  assume_role_policy = data.aws_iam_policy_document.dms_assume.json
}

data "aws_iam_policy_document" "dms_s3" {
  statement {
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = [aws_s3_bucket.landing.arn]
  }
  statement {
    actions   = ["s3:DeleteObject", "s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.landing.arn}/*"]
  }
  statement {
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.platform.arn]
  }
}

resource "aws_iam_role_policy" "dms_s3" {
  role   = aws_iam_role.dms_s3.id
  policy = data.aws_iam_policy_document.dms_s3.json
}

resource "aws_dms_s3_endpoint" "landing" {
  endpoint_id                       = "${local.name}-landing"
  endpoint_type                     = "target"
  bucket_name                       = aws_s3_bucket.landing.bucket
  bucket_folder                     = "raw"
  service_access_role_arn           = aws_iam_role.dms_s3.arn
  data_format                       = "parquet"
  timestamp_column_name             = "changebridge_commit_time"
  preserve_transactions             = true
  cdc_path                          = "cdc"
  encryption_mode                   = "SSE_KMS"
  server_side_encryption_kms_key_id = aws_kms_key.platform.arn
}

resource "aws_dms_replication_task" "migration" {
  count = var.source_endpoint_arn != "" && var.replication_instance_arn != "" ? 1 : 0

  migration_type           = "full-load-and-cdc"
  replication_instance_arn = var.replication_instance_arn
  replication_task_id      = local.name
  source_endpoint_arn      = var.source_endpoint_arn
  target_endpoint_arn      = aws_dms_s3_endpoint.landing.endpoint_arn

  table_mappings = jsonencode({
    rules = [{
      "rule-type" = "selection"
      "rule-id"   = "1"
      "rule-name" = "business-tables"
      "object-locator" = {
        "schema-name" = "public"
        "table-name"  = "%"
      }
      "rule-action" = "include"
    }]
  })
}
