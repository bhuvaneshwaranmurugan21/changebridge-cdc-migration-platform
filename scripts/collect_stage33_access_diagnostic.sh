#!/usr/bin/env bash
# Read-only CloudShell diagnostic. No apply mode and no AWS mutation.
set -euo pipefail
umask 077
export AWS_PAGER=''

CB_ACCOUNT="857229544428"
CB_REGION="ap-southeast-2"
CB_REPOSITORY="bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform"
CB_OLD_ROLE="ChangeBridgeGitHubOidcRole"
CB_CANDIDATE_ROLE="ChangeBridgePart3GitHubActionsRole"
CB_OLD_ARN="arn:aws:iam::857229544428:role/ChangeBridgeGitHubOidcRole"
CB_CANDIDATE_ARN="arn:aws:iam::857229544428:role/ChangeBridgePart3GitHubActionsRole"
CB_OIDC_ARN="arn:aws:iam::857229544428:oidc-provider/token.actions.githubusercontent.com"

cb_identity_guard() {
  jq -e '.Account == "857229544428" and
    (.Arn | startswith("arn:aws:sts::857229544428:assumed-role/AccountFullAccessRole/"))' "$1" >/dev/null
}
cb_role_guard() {
  jq -e --arg arn "$2" '.Role.Arn == $arn and
    (.Role.RoleId | type == "string" and length > 0)' "$1" >/dev/null
}
cb_region_guard() {
  [[ "$1" == "ap-southeast-2" ]]
}
cb_sanitize() {
  jq 'walk(
    if type == "object" then del(.UserId, .userId, .Email, .email)
    elif type == "string" then
      gsub("arn:aws:sts::[0-9]{12}:assumed-role/(?<role>[^/]+)/[^\\s\\\"]+";
        "arn:aws:sts::REDACTED_ACCOUNT:assumed-role/" + .role + "/REDACTED_SESSION")
      | gsub("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}"; "REDACTED_EMAIL")
    else . end)'
}
cb_hash() {
  local value unused
  read -r value unused < <(sha256sum -- "$1")
  printf '%s' "$value"
}
cb_canonical_hash() {
  jq -cS "$2" "$1" > "$CB_DIR/canonical.json"
  cb_hash "$CB_DIR/canonical.json"
}
cb_fail() {
  local operation="$1" code="$2" error_file="$3"
  jq -n --arg operation "$operation" --argjson exit_code "$code" \
    --arg started "$CB_STARTED" --arg finished "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
    --arg private_receipts "$CB_DIR" --rawfile error "$error_file" \
    '{label:"DIAGNOSTIC_NOT_ADMISSION_COMPLETE", result:"FAIL", operation:$operation,
      exit_code:$exit_code, started_at_utc:$started, finished_at_utc:$finished,
      aws_writes:0, private_receipts:$private_receipts, actual_error:$error}' | cb_sanitize
  exit "$code"
}
cb_read() {
  local name="$1" api_exit=0
  shift
  aws "$@" --region "$CB_REGION" --output json --no-cli-pager \
    > "$CB_DIR/$name.json" 2> "$CB_DIR/$name.stderr" || api_exit=$?
  if [[ "$api_exit" -ne 0 ]]; then cb_fail "$name" "$api_exit" "$CB_DIR/$name.stderr"; fi
  jq -e . "$CB_DIR/$name.json" >/dev/null
}

[[ "$#" -eq 0 ]] || { echo "Read-only diagnostic accepts no arguments or apply mode." >&2; exit 2; }
for CB_COMMAND in aws jq sha256sum mktemp date cp; do
  command -v "$CB_COMMAND" >/dev/null || { echo "Missing required command: $CB_COMMAND" >&2; exit 2; }
done
CB_DIR="$(mktemp -d /tmp/changebridge-stage33-access.XXXXXX)"
CB_STARTED="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
cp -- "$0" "$CB_DIR/input-snapshot.sh"
CB_SCRIPT_SHA="$(cb_hash "$CB_DIR/input-snapshot.sh")"
[[ "$(cb_hash "$0")" == "$CB_SCRIPT_SHA" ]] || { echo "Input script changed during snapshot." >&2; exit 2; }
CB_OBSERVED_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
if [[ -z "$CB_OBSERVED_REGION" ]]; then CB_OBSERVED_REGION="$(aws configure get region 2>/dev/null || true)"; fi
cb_region_guard "$CB_OBSERVED_REGION" || { echo "Expected CloudShell region ap-southeast-2." >&2; exit 2; }

cb_read caller sts get-caller-identity
cb_identity_guard "$CB_DIR/caller.json" || { echo "Expected exact account and AccountFullAccessRole." >&2; exit 2; }
cb_read old-role iam get-role --role-name "$CB_OLD_ROLE"
cb_role_guard "$CB_DIR/old-role.json" "$CB_OLD_ARN"
CB_ROLE_DIGEST="$(cb_canonical_hash "$CB_DIR/old-role.json" '.Role | {Arn,RoleId,AssumeRolePolicyDocument,PermissionsBoundary}')"
cb_read inline-list iam list-role-policies --role-name "$CB_OLD_ROLE"
cb_read attached-list iam list-attached-role-policies --role-name "$CB_OLD_ROLE"
: > "$CB_DIR/inline-documents.jsonl"
: > "$CB_DIR/managed-documents.jsonl"

while IFS= read -r CB_POLICY_NAME; do
  CB_POLICY_ID="$(printf '%s' "$CB_POLICY_NAME" | sha256sum)"
  CB_POLICY_ID="${CB_POLICY_ID%% *}"
  cb_read "inline-$CB_POLICY_ID" iam get-role-policy --role-name "$CB_OLD_ROLE" --policy-name "$CB_POLICY_NAME"
  jq -e --arg role "$CB_OLD_ROLE" --arg policy "$CB_POLICY_NAME" \
    '.RoleName == $role and .PolicyName == $policy' "$CB_DIR/inline-$CB_POLICY_ID.json" >/dev/null
  CB_BEFORE="$(cb_canonical_hash "$CB_DIR/inline-$CB_POLICY_ID.json" '.PolicyDocument')"
  cb_read "inline-after-$CB_POLICY_ID" iam get-role-policy --role-name "$CB_OLD_ROLE" --policy-name "$CB_POLICY_NAME"
  [[ "$(cb_canonical_hash "$CB_DIR/inline-after-$CB_POLICY_ID.json" '.PolicyDocument')" == "$CB_BEFORE" ]] \
    || { echo "Inline policy changed during collection." >&2; exit 3; }
  jq -c --arg digest "$CB_BEFORE" '{RoleName,PolicyName,PolicyDocument,canonical_document_sha256:$digest}' \
    "$CB_DIR/inline-$CB_POLICY_ID.json" >> "$CB_DIR/inline-documents.jsonl"
done < <(jq -r '.PolicyNames[]' "$CB_DIR/inline-list.json")

jq -rs --slurpfile role "$CB_DIR/old-role.json" \
  '([.[0].AttachedPolicies[].PolicyArn] +
    [$role[0].Role.PermissionsBoundary.PermissionsBoundaryArn // empty]) | unique | .[]' \
  "$CB_DIR/attached-list.json" > "$CB_DIR/observed-policy-arns.txt"
while IFS= read -r CB_POLICY_ARN; do
  [[ "$CB_POLICY_ARN" == arn:aws:iam::857229544428:policy/* || "$CB_POLICY_ARN" == arn:aws:iam::aws:policy/* ]] \
    || { echo "Unexpected observed managed-policy ARN." >&2; exit 3; }
  CB_POLICY_ID="$(printf '%s' "$CB_POLICY_ARN" | sha256sum)"
  CB_POLICY_ID="${CB_POLICY_ID%% *}"
  cb_read "managed-$CB_POLICY_ID" iam get-policy --policy-arn "$CB_POLICY_ARN"
  jq -e --arg arn "$CB_POLICY_ARN" '.Policy.Arn == $arn' "$CB_DIR/managed-$CB_POLICY_ID.json" >/dev/null
  CB_VERSION="$(jq -er '.Policy.DefaultVersionId' "$CB_DIR/managed-$CB_POLICY_ID.json")"
  cb_read "version-$CB_POLICY_ID" iam get-policy-version --policy-arn "$CB_POLICY_ARN" --version-id "$CB_VERSION"
  jq -e --arg version "$CB_VERSION" '.PolicyVersion.VersionId == $version and
    .PolicyVersion.IsDefaultVersion == true' "$CB_DIR/version-$CB_POLICY_ID.json" >/dev/null
  cb_read "managed-after-$CB_POLICY_ID" iam get-policy --policy-arn "$CB_POLICY_ARN"
  jq -e --arg arn "$CB_POLICY_ARN" --arg version "$CB_VERSION" \
    '.Policy.Arn == $arn and .Policy.DefaultVersionId == $version' "$CB_DIR/managed-after-$CB_POLICY_ID.json" >/dev/null
  CB_DOCUMENT_SHA="$(cb_canonical_hash "$CB_DIR/version-$CB_POLICY_ID.json" '.PolicyVersion.Document')"
  jq -c --arg arn "$CB_POLICY_ARN" --arg digest "$CB_DOCUMENT_SHA" \
    '{PolicyArn:$arn,VersionId:.PolicyVersion.VersionId,IsDefaultVersion:.PolicyVersion.IsDefaultVersion,
      Document:.PolicyVersion.Document,canonical_document_sha256:$digest}' \
    "$CB_DIR/version-$CB_POLICY_ID.json" >> "$CB_DIR/managed-documents.jsonl"
done < "$CB_DIR/observed-policy-arns.txt"

cb_read oidc-provider iam get-open-id-connect-provider --open-id-connect-provider-arn "$CB_OIDC_ARN"
jq -e '.Url == "token.actions.githubusercontent.com" and (.ClientIDList | index("sts.amazonaws.com") != null)' \
  "$CB_DIR/oidc-provider.json" >/dev/null
CB_CANDIDATE_EXIT=0
aws iam get-role --role-name "$CB_CANDIDATE_ROLE" --region "$CB_REGION" --output json --no-cli-pager \
  > "$CB_DIR/candidate-role.json" 2> "$CB_DIR/candidate-role.stderr" || CB_CANDIDATE_EXIT=$?
if [[ "$CB_CANDIDATE_EXIT" -eq 0 ]]; then
  cb_role_guard "$CB_DIR/candidate-role.json" "$CB_CANDIDATE_ARN"
  CB_CANDIDATE_STATUS="PRESENT"
else
  CB_CANDIDATE_ERROR="$(< "$CB_DIR/candidate-role.stderr")"
  if [[ "$CB_CANDIDATE_ERROR" == *"(NoSuchEntity)"*"when calling the GetRole operation"* ]]; then
    CB_CANDIDATE_STATUS="ABSENT_NO_SUCH_ENTITY"
    printf 'null\n' > "$CB_DIR/candidate-role.json"
  else cb_fail "candidate-role" "$CB_CANDIDATE_EXIT" "$CB_DIR/candidate-role.stderr"; fi
fi

cb_read old-role-after iam get-role --role-name "$CB_OLD_ROLE"
cb_role_guard "$CB_DIR/old-role-after.json" "$CB_OLD_ARN"
[[ "$(cb_canonical_hash "$CB_DIR/old-role-after.json" '.Role | {Arn,RoleId,AssumeRolePolicyDocument,PermissionsBoundary}')" == "$CB_ROLE_DIGEST" ]] \
  || { echo "Role identity, trust or permissions boundary changed during collection." >&2; exit 3; }
cb_read inline-list-after iam list-role-policies --role-name "$CB_OLD_ROLE"
cb_read attached-list-after iam list-attached-role-policies --role-name "$CB_OLD_ROLE"
[[ "$(cb_canonical_hash "$CB_DIR/inline-list.json" '.PolicyNames | sort')" == "$(cb_canonical_hash "$CB_DIR/inline-list-after.json" '.PolicyNames | sort')" ]] \
  || { echo "Inline policy inventory changed during collection." >&2; exit 3; }
[[ "$(cb_canonical_hash "$CB_DIR/attached-list.json" '.AttachedPolicies | sort_by(.PolicyArn)')" == "$(cb_canonical_hash "$CB_DIR/attached-list-after.json" '.AttachedPolicies | sort_by(.PolicyArn)')" ]] \
  || { echo "Attached policy inventory changed during collection." >&2; exit 3; }
[[ "$(cb_hash "$0")" == "$CB_SCRIPT_SHA" ]] || { echo "Source script changed during collection." >&2; exit 3; }

jq -n --arg repository "$CB_REPOSITORY" --arg account "$CB_ACCOUNT" --arg region "$CB_REGION" \
  --arg started "$CB_STARTED" --arg finished "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --arg script_sha "$CB_SCRIPT_SHA" --arg role_digest "$CB_ROLE_DIGEST" \
  --arg candidate_status "$CB_CANDIDATE_STATUS" --arg provider "$CB_OIDC_ARN" \
  --slurpfile role "$CB_DIR/old-role.json" --slurpfile candidate "$CB_DIR/candidate-role.json" \
  --slurpfile inline "$CB_DIR/inline-documents.jsonl" --slurpfile managed "$CB_DIR/managed-documents.jsonl" \
  --slurpfile oidc "$CB_DIR/oidc-provider.json" \
  '{schema_version:"1.0.0",label:"DIAGNOSTIC_NOT_ADMISSION_COMPLETE",result:"PASS",
    repository:$repository,account_id:$account,region:$region,
    started_at_utc:$started,finished_at_utc:$finished,source_script_sha256:$script_sha,
    operator_role:"AccountFullAccessRole",aws_writes:0,identity_controls_digest:$role_digest,
    role:($role[0].Role | {Arn,RoleId,MaxSessionDuration,PermissionsBoundary,AssumeRolePolicyDocument}),
    inline_policies:$inline,observed_managed_and_boundary_policies:$managed,
    oidc_provider_arn:$provider,oidc_provider:$oidc[0],
    candidate_status:$candidate_status,
    candidate_role:($candidate[0] | if . == null then null else
      (.Role | {Arn,RoleId,MaxSessionDuration,PermissionsBoundary,AssumeRolePolicyDocument}) end),
    limitations:["Read-only diagnostic, not bootstrap authorization or completed AWS admission.",
      "Terminal JSON redacts sessions and email addresses; document hashes refer to private original receipts, not redacted bytes.",
      "Separate AWS reads do not form an atomic IAM snapshot; observed before/after drift is rejected.",
      "No policy simulation, AWS mutation or other-project role read occurred."]}' | cb_sanitize
