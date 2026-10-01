output "deployment_identity" {
  value = {
    account    = var.expected_account_id
    region     = var.aws_region
    deployment = var.deployment_id
  }
}

output "buckets" {
  value = { for name, bucket in aws_s3_bucket.data : name => bucket.bucket }
}

output "control_tables" {
  value = { for name, table in aws_dynamodb_table.control : name => table.name }
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.migration.arn
}
