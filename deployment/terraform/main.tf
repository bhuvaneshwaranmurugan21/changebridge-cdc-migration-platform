locals {
  admitted = alltrue([
    var.expected_account_id != "UNASSIGNED", var.aws_region != "UNASSIGNED",
    var.deployment_id != "UNASSIGNED", var.runtime_artifact_bucket != "UNASSIGNED",
    var.runtime_artifact_key != "UNASSIGNED", var.runtime_artifact_sha256 != "UNASSIGNED",
    var.cost_center != "UNASSIGNED", var.expires_at != "UNASSIGNED"
  ])
  name          = "changebridge-${var.environment}-${var.deployment_id}"
  prefix        = "${local.name}-${var.expected_account_id}"
  alarm_actions = var.alarm_topic_arn == "" ? [] : [var.alarm_topic_arn]
  jobs = {
    snapshot = "spark_iceberg_snapshot.py", cdc-apply = "spark_iceberg_apply.py",
    schema   = "spark_iceberg_schema.py", reconcile = "spark_iceberg_reconcile.py",
    publish  = "spark_iceberg_publish.py"
  }
}

resource "terraform_data" "admission_guard" {
  input = {
    account    = var.expected_account_id
    region     = var.aws_region
    deployment = var.deployment_id
  }
  lifecycle {
    precondition {
      condition     = local.admitted
      error_message = "Stage 3 must assign account, region, deployment, artifact, cost, and expiry before mutation."
    }
  }
}

resource "aws_kms_key" "platform" {
  description             = "ChangeBridge platform key"
  enable_key_rotation     = true
  deletion_window_in_days = 7
  depends_on              = [terraform_data.admission_guard]
}

resource "aws_s3_bucket" "data" {
  for_each      = toset(["landing", "evidence", "warehouse"])
  bucket        = "${local.prefix}-${each.key}"
  force_destroy = false
}
resource "aws_s3_bucket_versioning" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.platform.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}
resource "aws_s3_bucket_public_access_block" "data" {
  for_each                = aws_s3_bucket.data
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_glue_catalog_database" "candidate" {
  name = replace("${local.name}-candidate", "-", "_")
}

resource "aws_dynamodb_table" "control" {
  for_each     = toset(["generations", "checkpoints", "active-pointer"])
  name         = "${local.name}-${each.key}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = each.key == "active-pointer" ? "product_id" : "generation_id"
  attribute {
    name = each.key == "active-pointer" ? "product_id" : "generation_id"
    type = "S"
  }
  point_in_time_recovery { enabled = true }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.platform.arn
  }
}
resource "aws_dynamodb_table" "publication_revisions" {
  name         = "${local.name}-publication-revisions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "product_id"
  range_key    = "revision"
  attribute {
    name = "product_id"
    type = "S"
  }
  attribute {
    name = "revision"
    type = "N"
  }
  point_in_time_recovery { enabled = true }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.platform.arn
  }
}

data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "job" {
  for_each           = local.jobs
  name               = "${local.name}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}
data "aws_iam_policy_document" "job" {
  statement {
    actions = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.data["landing"].arn,
      "${aws_s3_bucket.data["landing"].arn}/*",
      aws_s3_bucket.data["warehouse"].arn,
      "${aws_s3_bucket.data["warehouse"].arn}/*",
    ]
  }
  statement {
    actions   = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:CreateTable", "glue:UpdateTable"]
    resources = [aws_glue_catalog_database.candidate.arn, "arn:aws:glue:${var.aws_region}:${var.expected_account_id}:catalog", "arn:aws:glue:${var.aws_region}:${var.expected_account_id}:table/${aws_glue_catalog_database.candidate.name}/*"]
  }
  statement {
    actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
    resources = [
      aws_dynamodb_table.control["generations"].arn,
      aws_dynamodb_table.control["checkpoints"].arn,
    ]
  }
  statement {
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.platform.arn]
  }
}
resource "aws_iam_role_policy" "job" {
  for_each = aws_iam_role.job
  role     = each.value.id
  policy   = data.aws_iam_policy_document.job.json
}

data "aws_iam_policy_document" "publication" {
  statement {
    actions = ["dynamodb:GetItem", "dynamodb:TransactWriteItems", "dynamodb:UpdateItem"]
    resources = [
      aws_dynamodb_table.control["active-pointer"].arn,
      aws_dynamodb_table.publication_revisions.arn,
    ]
  }
}

resource "aws_iam_role_policy" "publication" {
  role   = aws_iam_role.job["publish"].id
  policy = data.aws_iam_policy_document.publication.json
}

data "aws_iam_policy_document" "evidence_writer" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.data["evidence"].arn}/*"]
  }
}

resource "aws_iam_role_policy" "evidence_writer" {
  role   = aws_iam_role.job["reconcile"].id
  policy = data.aws_iam_policy_document.evidence_writer.json
}

resource "aws_glue_job" "runtime" {
  for_each          = local.jobs
  name              = "${local.name}-${each.key}"
  role_arn          = aws_iam_role.job[each.key].arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 30
  max_retries       = 0
  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.runtime_artifact_bucket}/${var.runtime_artifact_key}/${each.value}"
  }
  default_arguments = { "--datalake-formats" = "iceberg", "--enable-glue-datacatalog" = "true", "--runtime-sha256" = var.runtime_artifact_sha256 }
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
resource "aws_iam_role" "dms" {
  name               = "${local.name}-dms"
  assume_role_policy = data.aws_iam_policy_document.dms_assume.json
}
data "aws_iam_policy_document" "dms" {
  statement {
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = [aws_s3_bucket.data["landing"].arn]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data["landing"].arn}/*"]
  }
  statement {
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.platform.arn]
  }
}
resource "aws_iam_role_policy" "dms" {
  role   = aws_iam_role.dms.id
  policy = data.aws_iam_policy_document.dms.json
}
resource "aws_dms_s3_endpoint" "landing" {
  endpoint_id                       = "${local.name}-landing"
  endpoint_type                     = "target"
  bucket_name                       = aws_s3_bucket.data["landing"].bucket
  bucket_folder                     = "raw"
  service_access_role_arn           = aws_iam_role.dms.arn
  data_format                       = "parquet"
  preserve_transactions             = true
  cdc_path                          = "cdc"
  timestamp_column_name             = "changebridge_commit_time"
  encryption_mode                   = "SSE_KMS"
  server_side_encryption_kms_key_id = aws_kms_key.platform.arn
}
resource "aws_dms_replication_task" "migration" {
  count                    = var.source_endpoint_arn == "UNASSIGNED" || var.replication_instance_arn == "UNASSIGNED" ? 0 : 1
  migration_type           = "full-load-and-cdc"
  replication_instance_arn = var.replication_instance_arn
  replication_task_id      = local.name
  source_endpoint_arn      = var.source_endpoint_arn
  target_endpoint_arn      = aws_dms_s3_endpoint.landing.endpoint_arn
  table_mappings           = jsonencode({ rules = [{ "rule-type" = "selection", "rule-id" = "1", "rule-name" = "orders", "object-locator" = { "schema-name" = "public", "table-name" = "orders" }, "rule-action" = "include" }, { "rule-type" = "selection", "rule-id" = "2", "rule-name" = "order-items", "object-locator" = { "schema-name" = "public", "table-name" = "order_items" }, "rule-action" = "include" }] })
}

data "aws_iam_policy_document" "states_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "states" {
  name               = "${local.name}-states"
  assume_role_policy = data.aws_iam_policy_document.states_assume.json
}
data "aws_iam_policy_document" "states" {
  statement {
    actions   = ["glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:BatchStopJobRun"]
    resources = [for job in aws_glue_job.runtime : job.arn]
  }
}
resource "aws_iam_role_policy" "states" {
  role   = aws_iam_role.states.id
  policy = data.aws_iam_policy_document.states.json
}
resource "aws_sfn_state_machine" "migration" {
  name       = "${local.name}-migration"
  role_arn   = aws_iam_role.states.arn
  definition = templatefile("${path.module}/../orchestration/migration.asl.json", { snapshot_job = aws_glue_job.runtime["snapshot"].name, cdc_job = aws_glue_job.runtime["cdc-apply"].name, schema_job = aws_glue_job.runtime["schema"].name, proof_job = aws_glue_job.runtime["reconcile"].name, publish_job = aws_glue_job.runtime["publish"].name })
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
resource "aws_cloudwatch_metric_alarm" "workflow_failure" {
  alarm_name          = "${local.name}-workflow-failure"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { StateMachineArn = aws_sfn_state_machine.migration.arn }
  alarm_actions       = local.alarm_actions
}
