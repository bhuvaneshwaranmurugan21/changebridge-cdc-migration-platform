"""Materialize exact bootstrap requests; request construction never grants execution authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from scripts.prepare_stage33_bootstrap import (
    ACCOUNT,
    EMAIL,
    EXECUTION_ID,
    EXPIRY,
    KEY,
    REGION,
    canonical,
    compile_package,
    digest,
)
from scripts.qualify_stage33_bootstrap import decode_response


class BindingError(ValueError):
    """Unresolved or changed physical/ownership bindings block request construction."""


def utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as error:
        raise BindingError("explicit UTC binding required") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise BindingError("explicit UTC binding required")
    return parsed


@dataclass(frozen=True)
class ExecutionBindings:
    execution_id: str
    prepared_at_utc: str
    expires_at_utc: str
    alert_email: str = field(repr=False)
    approved_email_sha256: str = field(repr=False)
    key_arn: str | None = None

    def validate(self) -> None:
        if not isinstance(self.execution_id, str) or not re.fullmatch(
            r"[a-z0-9-]{8,64}", self.execution_id
        ):
            raise BindingError("exact execution identity required")
        if (
            not 0
            < (utc(self.expires_at_utc) - utc(self.prepared_at_utc)).total_seconds()
            <= 48 * 3600
        ):
            raise BindingError("preparation-bound expiry must be within 48 hours")
        if (
            not isinstance(self.alert_email, str)
            or len(self.alert_email) > 254
            or not re.fullmatch(
                r"[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+"
                r"@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?"
                r"\.[A-Za-z]{2,63}",
                self.alert_email,
            )
            or not isinstance(self.approved_email_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.approved_email_sha256)
            or hashlib.sha256(self.alert_email.encode()).hexdigest() != self.approved_email_sha256
        ):
            raise BindingError("private endpoint must match independently approved email digest")
        if self.key_arn is not None and (
            not isinstance(self.key_arn, str)
            or not re.fullmatch(
                rf"arn:aws:kms:{REGION}:{ACCOUNT}:key/"
                r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}",
                self.key_arn,
            )
        ):
            raise BindingError("exact same-account regional physical key ARN required")

    def tags(self) -> dict[str, str]:
        self.validate()
        return {
            "Project": "ChangeBridge",
            "Owner": "bhuvaneshwaranmurugan21",
            "Stage": "part3-stage3",
            "CostCenter": "changebridge-p3s3",
            "ExpiresAt": self.expires_at_utc,
            "ExecutionId": self.execution_id,
        }

    def validate_time(self, now: datetime, first_created_at_utc: str | None = None) -> None:
        """Recheck actual creation-bound lifetime before use; preparation is not creation proof."""
        self.validate()
        if now.tzinfo is None or now.utcoffset() != UTC.utcoffset(now):
            raise BindingError("UTC execution clock required")
        if not utc(self.prepared_at_utc) <= now < utc(self.expires_at_utc):
            raise BindingError("execution outside immutable lifetime window")
        if first_created_at_utc is not None:
            created = utc(first_created_at_utc)
            if (
                created < utc(self.prepared_at_utc)
                or created > now
                or not 0 < (utc(self.expires_at_utc) - created).total_seconds() <= 48 * 3600
            ):
                raise BindingError("actual first-creation lifetime is invalid")


def _bind(value: Any, bindings: ExecutionBindings) -> Any:
    if isinstance(value, dict):
        return {k: _bind(v, bindings) for k, v in value.items()}
    if isinstance(value, list):
        return [_bind(v, bindings) for v in value]
    if isinstance(value, str):
        replacements = {
            EMAIL: bindings.alert_email,
            EXPIRY: bindings.expires_at_utc,
            EXECUTION_ID: bindings.execution_id,
            KEY: bindings.key_arn,
        }
        if value in replacements:
            resolved = replacements[value]
            if resolved is None:
                raise BindingError("physical key is unresolved; prerequisite readback required")
            return resolved
        if KEY in value:
            # Only compiled JSON policy strings embed a key placeholder. Parse rather than
            # interpolating private values into JSON or accepting arbitrary embedded tokens.
            parsed = decode_response(value.encode())
            return json.dumps(_bind(parsed, bindings), sort_keys=True, separators=(",", ":"))
        if any(token in value for token in (EMAIL, EXPIRY, EXECUTION_ID)) or "__" in value:
            raise BindingError("unsupported embedded or unresolved placeholder")
    return value


def materialize_request(
    package: dict[str, Any], step_id: str, bindings: ExecutionBindings
) -> dict[str, Any]:
    """Require current frozen authority and a fresh detached exact request; execute nothing."""
    bindings.validate()
    if package != compile_package():
        raise BindingError("package differs from current immutable source authority")
    step = next((s for s in package["steps"] if s["id"] == step_id), None)
    if step is None:
        raise BindingError("step outside exact bootstrap authority")
    request = _bind(json.loads(canonical(step["request"])), bindings)
    if not isinstance(request, dict) or "__" in canonical(request).decode():
        raise BindingError("unresolved request binding")
    return request


def request_plan(
    package: dict[str, Any], step_id: str, bindings: ExecutionBindings
) -> dict[str, Any]:
    request = materialize_request(package, step_id, bindings)
    step = next(s for s in package["steps"] if s["id"] == step_id)
    result = {
        "label": "CONCRETE_REQUEST_NOT_EXECUTION_AUTHORITY",
        "execution_enabled": False,
        "package_sha256": package["package_sha256"],
        "execution_id": bindings.execution_id,
        "step_id": step_id,
        "service": step["service"],
        "operation": step["operation"],
        "request": request,
        "request_sha256": digest(request),
        "prerequisites_verified": False,
    }
    frozen: dict[str, Any] = json.loads(canonical(result))
    return frozen
