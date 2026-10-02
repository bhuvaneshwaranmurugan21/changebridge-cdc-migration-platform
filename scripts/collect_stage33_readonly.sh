#!/usr/bin/env bash
set -euo pipefail

ACCOUNT="857229544428"
REGION="ap-southeast-2"
REPOSITORY="bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform"
STATE_BUCKET="changebridge-p3s3-tfstate-857229544428-ap-southeast-2"
ARTIFACT_BUCKET="changebridge-p3s3-artifacts-857229544428-ap-southeast-2"
LOCK_TABLE="changebridge-p3s3-tf-locks"
ALERT_TOPIC="changebridge-p3s3-alerts"
EXECUTION_ROLE="ChangeBridgePart3GitHubActionsRole"
OUT="$(mktemp -d /tmp/changebridge-stage33-readonly.XXXXXX)"

aws sts get-caller-identity --output json > "$OUT/caller-identity.json"
ACTUAL_ACCOUNT="$(jq -r .Account "$OUT/caller-identity.json")"
if [[ "$ACTUAL_ACCOUNT" != "$ACCOUNT" ]]; then
  echo "FAIL: expected account $ACCOUNT, observed $ACTUAL_ACCOUNT" >&2
  exit 10
fi

jq -n \
  --arg account "$ACCOUNT" \
  --arg region "$REGION" \
  --arg repository "$REPOSITORY" \
  --arg collected_at_utc "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  '{schema_version:"1.0.0",account_id:$account,region:$region,repository:$repository,read_only:true,collected_at_utc:$collected_at_utc}' \
  > "$OUT/context.json"

aws iam list-open-id-connect-providers --output json > "$OUT/oidc-providers.json"
while IFS= read -r provider_arn; do
  provider_id="$(printf '%s' "$provider_arn" | sha256sum | cut -c1-16)"
  aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$provider_arn" \
    --output json > "$OUT/oidc-provider-${provider_id}.json"
done < <(jq -r '.OpenIDConnectProviderList[].Arn' "$OUT/oidc-providers.json")
aws iam get-role --role-name "$EXECUTION_ROLE" --output json > "$OUT/execution-role.json" 2> "$OUT/execution-role.stderr" || true
aws iam list-role-policies --role-name "$EXECUTION_ROLE" --output json > "$OUT/execution-role-inline-policies.json" 2> "$OUT/execution-role-inline-policies.stderr" || true
aws iam list-attached-role-policies --role-name "$EXECUTION_ROLE" --output json > "$OUT/execution-role-attached-policies.json" 2> "$OUT/execution-role-attached-policies.stderr" || true

if [[ -s "$OUT/execution-role-inline-policies.json" ]]; then
  while IFS= read -r policy_name; do
    policy_id="$(printf '%s' "$policy_name" | sha256sum | cut -c1-16)"
    aws iam get-role-policy --role-name "$EXECUTION_ROLE" --policy-name "$policy_name" \
      --output json > "$OUT/execution-role-inline-${policy_id}.json"
  done < <(jq -r '.PolicyNames[]' "$OUT/execution-role-inline-policies.json")
fi

if aws s3api head-bucket --bucket "$STATE_BUCKET" --region "$REGION" \
  2> "$OUT/state-bucket.stderr"; then
  echo '{"status":"EXISTS_ACCESSIBLE","mutation_gate":"BLOCK"}' \
    > "$OUT/state-bucket-collision.json"
elif grep -Eq '\(404\)|Not Found|NoSuchBucket' "$OUT/state-bucket.stderr"; then
  echo '{"status":"ABSENT","mutation_gate":"PASS"}' > "$OUT/state-bucket-collision.json"
else
  echo '{"status":"EXISTS_OR_INACCESSIBLE","mutation_gate":"BLOCK"}' \
    > "$OUT/state-bucket-collision.json"
fi
if aws s3api head-bucket --bucket "$ARTIFACT_BUCKET" --region "$REGION" \
  2> "$OUT/artifact-bucket.stderr"; then
  echo '{"status":"EXISTS_ACCESSIBLE","mutation_gate":"BLOCK"}' \
    > "$OUT/artifact-bucket-collision.json"
elif grep -Eq '\(404\)|Not Found|NoSuchBucket' "$OUT/artifact-bucket.stderr"; then
  echo '{"status":"ABSENT","mutation_gate":"PASS"}' > "$OUT/artifact-bucket-collision.json"
else
  echo '{"status":"EXISTS_OR_INACCESSIBLE","mutation_gate":"BLOCK"}' \
    > "$OUT/artifact-bucket-collision.json"
fi
aws dynamodb describe-table --table-name "$LOCK_TABLE" --region "$REGION" --output json \
  > "$OUT/lock-table-collision.json" 2> "$OUT/lock-table.stderr" || true
aws sns list-topics --region "$REGION" --output json > "$OUT/sns-topics.json"
aws kms list-aliases --region "$REGION" --output json > "$OUT/kms-aliases.json"

aws budgets describe-budgets --account-id "$ACCOUNT" --output json > "$OUT/budgets.json"
aws budgets describe-notifications-for-budget \
  --account-id "$ACCOUNT" \
  --budget-name portfolio-labs-monthly-cost \
  --output json > "$OUT/budget-notifications.json"

aws service-quotas list-service-quotas --service-code glue --region "$REGION" --output json \
  > "$OUT/quotas-glue.json" 2> "$OUT/quotas-glue.stderr" || true
aws service-quotas list-service-quotas --service-code dms --region "$REGION" --output json \
  > "$OUT/quotas-dms.json" 2> "$OUT/quotas-dms.stderr" || true
aws service-quotas list-service-quotas --service-code states --region "$REGION" --output json \
  > "$OUT/quotas-stepfunctions.json" 2> "$OUT/quotas-stepfunctions.stderr" || true

aws dms describe-account-attributes --region "$REGION" --output json > "$OUT/dms-availability.json"
aws glue get-databases --region "$REGION" --max-results 1 --output json > "$OUT/glue-availability.json"
aws stepfunctions list-state-machines --region "$REGION" --max-results 1 --output json > "$OUT/stepfunctions-availability.json"
aws ec2 describe-vpcs --region "$REGION" --output json > "$OUT/vpcs.json"
aws ec2 describe-subnets --region "$REGION" --output json > "$OUT/subnets.json"

find "$OUT" -type f -empty -delete
(
  cd "$OUT"
  sha256sum * > SHA256SUMS
)

ARCHIVE="${OUT}-$(date -u '+%Y%m%dT%H%M%SZ').zip"
python3 - "$OUT" "$ARCHIVE" <<'PY'
import pathlib
import sys
import zipfile

source = pathlib.Path(sys.argv[1])
archive = pathlib.Path(sys.argv[2])
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
    for path in sorted(source.iterdir()):
        info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        bundle.writestr(info, path.read_bytes())
print(archive)
PY

sha256sum "$ARCHIVE"
echo "READ_ONLY=true"
echo "AWS_MUTATIONS=0"
