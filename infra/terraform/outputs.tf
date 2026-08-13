output "landing_bucket" {
  value = aws_s3_bucket.landing.bucket
}

output "evidence_bucket" {
  value = aws_s3_bucket.evidence.bucket
}

output "generation_table" {
  value = aws_dynamodb_table.generations.name
}

output "active_pointer_table" {
  value = aws_dynamodb_table.active_pointer.name
}

output "dms_target_endpoint_arn" {
  value = aws_dms_s3_endpoint.landing.endpoint_arn
}
