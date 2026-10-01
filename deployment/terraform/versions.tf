terraform {
  required_version = "~> 1.9.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 5.100.0" }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "ChangeBridge"
      Environment = var.environment
      Deployment  = var.deployment_id
      CostCenter  = var.cost_center
      ExpiresAt   = var.expires_at
    }
  }
}
