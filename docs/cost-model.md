# Cost controls

- The lab reuses a small, short-lived source and supplies DMS endpoints as variables.
- No NAT gateway, MSK cluster, or always-on Spark cluster is created by this module.
- S3 and DynamoDB use bounded synthetic data and on-demand capacity.
- CloudWatch retention is finite and resources are tagged by run and expiry.
- DMS/compute is created only for the managed experiment and destroyed immediately afterward.

The evidence contract requires a measured cost value and teardown verification. A calculator
estimate is useful before deployment but is not recorded as actual cost.

