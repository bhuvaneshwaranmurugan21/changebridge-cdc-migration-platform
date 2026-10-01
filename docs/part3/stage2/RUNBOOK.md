# Stage 2 validation runbook

Stage 2 validation must run without AWS credentials and without a remote backend.

```bash
python scripts/package_stage32_runtime.py --output /tmp/changebridge-stage32-a.zip
python scripts/package_stage32_runtime.py --output /tmp/changebridge-stage32-b.zip
sha256sum /tmp/changebridge-stage32-a.zip /tmp/changebridge-stage32-b.zip
terraform fmt -check -diff -recursive deployment/terraform
AWS_ACCESS_KEY_ID= AWS_SECRET_ACCESS_KEY= AWS_SESSION_TOKEN= \
AWS_EC2_METADATA_DISABLED=true terraform -chdir=deployment/terraform init -backend=false
AWS_ACCESS_KEY_ID= AWS_SECRET_ACCESS_KEY= AWS_SESSION_TOKEN= \
AWS_EC2_METADATA_DISABLED=true terraform -chdir=deployment/terraform validate
python scripts/validate_part3_stage2.py
pytest -q tests/test_part3_stage2_validator.py
```

`init` may retrieve only the repository-declared providers. Do not run refresh, plan against live
resources, apply, import, or destroy. A future Stage 3 authorization must bind account, region,
budget, identity, OIDC, backend, quotas and artifact upload before any AWS mutation.
