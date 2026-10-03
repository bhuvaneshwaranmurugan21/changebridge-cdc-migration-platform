#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly ACCOUNT="857229544428"
readonly REGION="ap-southeast-2"
readonly ROLE_NAME="ChangeBridgeGitHubOidcRole"
readonly ROLE_ARN="arn:aws:iam::857229544428:role/ChangeBridgeGitHubOidcRole"
readonly POLICY_NAME="ChangeBridgeStage33RoleObserver"
mode="CHECK_ONLY"
expected_digest=""
expected_role_id=""
expected_trust_digest=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --apply) mode="APPLY"; shift ;;
    --expected-policy-sha256)
      [[ "$#" -ge 2 ]] || { echo "FAIL: missing reviewed digest" >&2; exit 10; }
      expected_digest="$2"; shift 2 ;;
    --expected-role-id)
      [[ "$#" -ge 2 ]] || { echo "FAIL: missing reviewed role identity" >&2; exit 10; }
      expected_role_id="$2"; shift 2 ;;
    --expected-trust-sha256)
      [[ "$#" -ge 2 ]] || { echo "FAIL: missing reviewed trust digest" >&2; exit 10; }
      expected_trust_digest="$2"; shift 2 ;;
    *) echo "FAIL: unsupported argument" >&2; exit 10 ;;
  esac
done
[[ "$expected_digest" =~ ^[a-f0-9]{64}$ ]] || {
  echo "FAIL: reviewed exact policy SHA256 is required" >&2; exit 10;
}
if [[ "$mode" == "APPLY" ]]; then
  [[ "$expected_role_id" =~ ^AROA[A-Z0-9]+$ &&
     "$expected_trust_digest" =~ ^[a-f0-9]{64}$ ]] || {
    echo "FAIL: apply requires independently reviewed RoleId and trust SHA256" >&2; exit 10;
  }
fi
for executable in aws jq sha256sum mktemp; do
  command -v "$executable" > /dev/null || {
    echo "FAIL: required existing executable unavailable: $executable" >&2; exit 11;
  }
done
script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
policy_file="$script_directory/../deployment/stage3/ChangeBridgeStage33RoleObserver.proposed.json"
receipt_directory="$(mktemp -d /tmp/changebridge-stage33-role-observer.XXXXXX)"
# Hash, validate and submit the same private bytes, never the mutable source file.
frozen_policy_file="$receipt_directory/approved-policy.original.json"
cp -- "$policy_file" "$frozen_policy_file"
actual_digest="$(sha256sum "$frozen_policy_file" | cut -d ' ' -f 1)"
[[ "$actual_digest" == "$expected_digest" ]] || {
  echo "FAIL: policy differs from reviewed exact digest" >&2; exit 12;
}
jq -e --arg arn "$ROLE_ARN" '
  keys == ["Statement", "Version"] and .Version == "2012-10-17" and
  (.Statement | length) == 1 and
  (.Statement[0] | keys) == ["Action", "Effect", "Resource", "Sid"] and
  .Statement[0].Sid == "ObserveExactExistingChangeBridgeRoleOnly" and
  .Statement[0].Effect == "Allow" and .Statement[0].Resource == $arn and
  (.Statement[0].Action | sort) ==
    ["iam:GetRole", "iam:GetRolePolicy", "iam:ListAttachedRolePolicies", "iam:ListRolePolicies"]
' "$frozen_policy_file" > /dev/null
effective_region="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
[[ "$effective_region" == "$REGION" ]] || {
  echo "FAIL: administrator execution environment must explicitly bind ap-southeast-2" >&2; exit 13;
}
read_api() {
  local receipt_name="$1"
  shift
  local api_exit=0
  aws "$@" --region "$REGION" --output json \
    > "$receipt_directory/$receipt_name.json" 2> "$receipt_directory/$receipt_name.stderr" || api_exit=$?
  if [[ "$api_exit" -ne 0 ]]; then
    echo "FAIL: $receipt_name AWS_EXIT=$api_exit RECEIPTS=$receipt_directory" >&2
    head -c 4096 "$receipt_directory/$receipt_name.stderr" >&2
    exit "$api_exit"
  fi
}
read_api administrator sts get-caller-identity
jq -e --arg account "$ACCOUNT" '
  .Account == $account and
  (.Arn | startswith("arn:aws:sts::" + $account + ":assumed-role/AccountFullAccessRole/"))
' "$receipt_directory/administrator.json" > /dev/null || {
  echo "FAIL: actual qualified AccountFullAccessRole administrator required; self-grant prohibited" >&2
  exit 14
}
read_api role-before iam get-role --role-name "$ROLE_NAME"
jq -e --arg arn "$ROLE_ARN" '.Role.Arn == $arn and (.Role.RoleId | length > 0)' \
  "$receipt_directory/role-before.json" > /dev/null
jq -Sc '.Role.AssumeRolePolicyDocument' "$receipt_directory/role-before.json" \
  > "$receipt_directory/trust-before.canonical.json"
role_id="$(jq -r '.Role.RoleId' "$receipt_directory/role-before.json")"
trust_digest="$(sha256sum "$receipt_directory/trust-before.canonical.json" | cut -d ' ' -f 1)"
if [[ "$mode" == "APPLY" ]]; then
  [[ "$role_id" == "$expected_role_id" && "$trust_digest" == "$expected_trust_digest" ]] || {
    echo "FAIL: role identity or trust differs from reviewed preflight" >&2; exit 19;
  }
fi
jq -Sc '.Role.PermissionsBoundary // null' "$receipt_directory/role-before.json" \
  > "$receipt_directory/boundary-before.canonical.json"
jq -Sc '.' "$frozen_policy_file" > "$receipt_directory/approved-policy.canonical.json"
prior_exit=0
aws iam get-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" \
  --region "$REGION" --output json > "$receipt_directory/policy-before.json" \
  2> "$receipt_directory/policy-before.stderr" || prior_exit=$?
prior_state="UNKNOWN"
if [[ "$prior_exit" -eq 0 ]]; then
  jq -Sc '.PolicyDocument' "$receipt_directory/policy-before.json" \
    > "$receipt_directory/prior-policy.canonical.json"
  cmp -s "$receipt_directory/approved-policy.canonical.json" "$receipt_directory/prior-policy.canonical.json" || {
    echo "FAIL: existing same-name policy differs; overwrite prohibited" >&2; exit 15;
  }
  prior_state="EXACT_EQUIVALENT"
elif grep -q 'An error occurred (NoSuchEntity)' "$receipt_directory/policy-before.stderr"; then
  prior_state="ABSENT"
else
  echo "FAIL: policy collision cannot be qualified AWS_EXIT=$prior_exit" >&2
  head -c 4096 "$receipt_directory/policy-before.stderr" >&2
  exit "$prior_exit"
fi
if [[ "$mode" == "CHECK_ONLY" ]]; then
  jq -n --arg policy_sha256 "$actual_digest" --arg prior_state "$prior_state" \
    --arg role_id "$role_id" --arg trust_sha256 "$trust_digest" \
    --arg receipts "$receipt_directory" \
    '{result:"ADMINISTRATOR_PREFLIGHT_ONLY",aws_mutations:0,policy_sha256:$policy_sha256,
      role_id:$role_id,trust_sha256:$trust_sha256,prior_policy_state:$prior_state,receipts:$receipts}'
  exit 0
fi
# PutRolePolicy has no create-only/CAS operation. Use one qualified exclusive executor;
# never claim the read-then-write sequence is an atomic collision guard.
write_attempted=false
write_exit=0
if [[ "$prior_state" == "ABSENT" ]]; then
  write_attempted=true
  aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" \
    --policy-document "file://$frozen_policy_file" --region "$REGION" \
    > "$receipt_directory/put-policy.stdout" 2> "$receipt_directory/put-policy.stderr" || write_exit=$?
fi
# Read back even after a failed acknowledgement; do not retry an ambiguous write.
read_api policy-after iam get-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME"
jq -Sc '.PolicyDocument' "$receipt_directory/policy-after.json" \
  > "$receipt_directory/actual-policy.canonical.json"
cmp -s "$receipt_directory/approved-policy.canonical.json" "$receipt_directory/actual-policy.canonical.json" || {
  echo "FAIL: actual policy differs; do not retry or overwrite" >&2; exit 16;
}
read_api role-after iam get-role --role-name "$ROLE_NAME"
jq -e --arg arn "$ROLE_ARN" '.Role.Arn == $arn' "$receipt_directory/role-after.json" > /dev/null
jq -Sc '.Role.AssumeRolePolicyDocument' "$receipt_directory/role-after.json" \
  > "$receipt_directory/trust-after.canonical.json"
cmp -s "$receipt_directory/trust-before.canonical.json" "$receipt_directory/trust-after.canonical.json" || {
  echo "FAIL: role trust changed during execution" >&2; exit 17;
}
[[ "$(jq -r '.Role.RoleId' "$receipt_directory/role-before.json")" == \
   "$(jq -r '.Role.RoleId' "$receipt_directory/role-after.json")" ]] || {
  echo "FAIL: role identity changed during execution" >&2; exit 18;
}
jq -Sc '.Role.PermissionsBoundary // null' "$receipt_directory/role-after.json" \
  > "$receipt_directory/boundary-after.canonical.json"
cmp -s "$receipt_directory/boundary-before.canonical.json" \
  "$receipt_directory/boundary-after.canonical.json" || {
  echo "FAIL: permissions boundary changed during execution" >&2; exit 20;
}
policy_readback_digest="$(sha256sum "$receipt_directory/actual-policy.canonical.json" | cut -d ' ' -f 1)"
jq -n --arg role_arn "$ROLE_ARN" --arg policy_name "$POLICY_NAME" \
  --arg policy_sha256 "$actual_digest" --arg readback_sha256 "$policy_readback_digest" \
  --arg role_id "$role_id" --arg trust_sha256 "$trust_digest" \
  --arg receipts "$receipt_directory" --argjson write_attempted "$write_attempted" \
  --argjson write_exit "$write_exit" \
  '{result:"EXACT_PHASE1_POLICY_READBACK_VERIFIED",role_arn:$role_arn,policy_name:$policy_name,
    approved_file_sha256:$policy_sha256,canonical_readback_sha256:$readback_sha256,
    role_id:$role_id,trust_sha256:$trust_sha256,permissions_boundary_unchanged:true,
    write_attempted:$write_attempted,write_process_exit:$write_exit,receipts:$receipts,
    stage3_complete:false,phase2_managed_policy_reads:"NOT_AUTHORIZED_BY_THIS_POLICY"}' \
  | tee "$receipt_directory/receipt.json"
if [[ "$write_exit" -ne 0 ]]; then
  echo "NOTICE: failed write acknowledgement reconciled to exact policy; original stderr retained." >&2
fi
