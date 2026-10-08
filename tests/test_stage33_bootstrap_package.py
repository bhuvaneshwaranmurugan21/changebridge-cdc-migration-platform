"""Offline construction tests; no test is a managed AWS acceptance receipt."""

import json
import stat

import pytest

from scripts import prepare_stage33_bootstrap as bootstrap


def test_package_is_deterministic_and_bound():
    package = bootstrap.compile_package()
    assert package == bootstrap.compile_package()
    digest = package.pop("package_sha256")
    assert digest == bootstrap.digest(package)
    assert package["execution_enabled"] is False
    assert len({step["resource"] for step in package["steps"]}) == 8
    assert set(package["required_actual_readbacks"]) == {
        step["resource"] for step in package["steps"]
    }
    assert package["not_implemented"]
    subscription = next(s for s in package["steps"] if s["operation"] == "subscribe")
    assert subscription["request"]["Endpoint"] == bootstrap.EMAIL


def test_dependencies_and_unknown_acknowledgements():
    steps = bootstrap.compile_package()["steps"]
    for index, step in enumerate(steps):
        assert step["depends_on"] == ([steps[index - 1]["id"]] if index else [])
        assert step["on_unknown_outcome"] == "STOP_AND_AUTHORITATIVELY_RECONCILE_NO_BLIND_RETRY"
        assert step["acknowledgement_is_not_configuration_proof"] is True


def test_security_requests_and_inner_policy_only():
    steps = bootstrap.compile_package()["steps"]
    role = next(s for s in steps if s["operation"] == "create-role")
    trust = json.loads(role["request"]["AssumeRolePolicyDocument"])
    subject = trust["Statement"][0]["Condition"]["StringEquals"][
        "token.actions.githubusercontent.com:sub"
    ]
    assert subject.endswith("ref:refs/heads/part3-stage3-aws-admission")
    assert "@276895096/" in subject and "@1332970949:" in subject
    policy_step = next(s for s in steps if s["operation"] == "put-role-policy")
    policy = json.loads(policy_step["request"]["PolicyDocument"])
    assert set(policy) == {"Version", "Statement"}
    assert policy["Statement"][-1]["Resource"] == bootstrap.KEY
    assert "iam:*" not in json.dumps(policy)
    encryption = [s for s in steps if s["operation"] == "put-bucket-encryption"]
    assert len(encryption) == 2
    for step in encryption:
        assert step["request"]["ExpectedBucketOwner"] == bootstrap.ACCOUNT
    assert any(s["operation"] == "update-continuous-backups" for s in steps)
    assert not any(s["operation"].startswith("delete") for s in steps)


def test_private_file_rejects_overwrite_and_symlink(tmp_path):
    output = tmp_path / "package.json"
    bootstrap.write_package(output)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        bootstrap.write_package(output)
    assert output.read_bytes() == original
    link = tmp_path / "link.json"
    link.symlink_to(output)
    with pytest.raises(FileExistsError):
        bootstrap.write_package(link)
    assert output.read_bytes() == original


@pytest.mark.parametrize("mutation", ["account", "region", "lifetime", "extra", "rename"])
def test_scope_drift_stops_compilation(tmp_path, monkeypatch, mutation):
    import shutil

    for name in bootstrap.SOURCES:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bootstrap.ROOT / name, destination)
    path = tmp_path / bootstrap.SOURCES[0]
    manifest = json.loads(path.read_text())
    if mutation == "account":
        manifest["account_id"] = "000000000000"
    elif mutation == "region":
        manifest["region"] = "us-east-1"
    elif mutation == "lifetime":
        manifest["maximum_lifetime_hours"] = 49
    elif mutation == "extra":
        manifest["resources"].append(manifest["resources"][0])
    else:
        manifest["resources"][2]["physical_name"] = "another-project-bucket"
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="allowlist drift"):
        bootstrap.compile_package()


def test_tampered_request_cannot_be_verified(tmp_path):
    output = tmp_path / "package.json"
    bootstrap.write_package(output)
    bootstrap.verify_package(output)
    payload = json.loads(output.read_bytes())
    payload["steps"][0]["request"]["MultiRegion"] = True
    unsigned = {key: value for key, value in payload.items() if key != "package_sha256"}
    payload["package_sha256"] = bootstrap.digest(unsigned)
    output.write_bytes(bootstrap.canonical(payload))
    with pytest.raises(ValueError, match="tampered or stale"):
        bootstrap.verify_package(output)


def test_source_drift_during_compilation_stops(tmp_path, monkeypatch):
    import shutil

    for name in bootstrap.SOURCES:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bootstrap.ROOT / name, destination)
    original_validate = bootstrap.validate_proposed_policies

    def drift_after_validation():
        original_validate()
        path = tmp_path / bootstrap.SOURCES[3]
        path.write_bytes(path.read_bytes() + b"\n")

    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    monkeypatch.setattr(bootstrap, "validate_proposed_policies", drift_after_validation)
    with pytest.raises(ValueError, match="source drift"):
        bootstrap.compile_package()


def test_backend_decryption_is_bound_to_each_required_service_and_exact_table():
    package = bootstrap.compile_package()
    step = next(s for s in package['steps'] if s['operation'] == 'put-role-policy')
    policy = json.loads(step['request']['PolicyDocument'])
    statements = {s['Sid']: s for s in policy['Statement']}
    table = statements['ExactLockTableKeyDecryptViaRegionalDynamoDBOnly']
    assert table['Action'] == 'kms:Decrypt'
    assert table['Resource'] == bootstrap.KEY
    assert table['Condition'] == {'StringEquals': {
        'kms:CallerAccount': bootstrap.ACCOUNT,
        'kms:ViaService': f'dynamodb.{bootstrap.REGION}.amazonaws.com',
        'kms:EncryptionContext:aws:dynamodb:tableName': bootstrap.LOCKS,
        'kms:EncryptionContext:aws:dynamodb:subscriberId': bootstrap.ACCOUNT,
    }}
    s3 = statements['ExactVerifiedKeyViaRegionalS3Only']
    assert s3['Resource'] == bootstrap.KEY
    assert s3['Condition']['StringEquals']['kms:ViaService'] == (
        f's3.{bootstrap.REGION}.amazonaws.com')
    assert all(s['Resource'] != '*' for s in policy['Statement'])


def test_kms_creation_uses_kms_specific_tag_shape():
    package = bootstrap.compile_package()
    key = package['steps'][0]['request']
    assert all(set(t) == {'TagKey', 'TagValue'} for t in key['Tags'])
    assert {t['TagKey'] for t in key['Tags']} == {
        'Project', 'Owner', 'Stage', 'CostCenter', 'ExpiresAt', 'ExecutionId'}
    others = [s for s in package['steps'] if s['operation'] in {
        'create-table', 'create-topic', 'create-role'}]
    assert all(set(t) == {'Key', 'Value'} for s in others for t in s['request']['Tags'])
