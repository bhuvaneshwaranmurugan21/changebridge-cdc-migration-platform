# Canonicalization

The authority is `contracts/canonicalization-v1.json`; `src/changebridge/contracts.py` is its bounded
reference implementation. Canonical bytes consist of the profile ID, an identity-specific domain
separator, and compact UTF-8 JSON with NFC strings and sorted normalized object keys.

Integers remain exact. Finite decimals use a tagged normalized decimal string. Binary values use
unpadded base64url in a tagged object. Timestamps are UTC RFC 3339 values with six fractional digits.
IEEE-754 floats are rejected from identity material. Null is an explicit value and is not equivalent
to an absent key. Composite primary keys preserve the source-contract component order and each
component's name, type, and value.

Source positions contain a kind and canonical string value. Only positions of the same kind are
comparable. Total event order is source position, transaction sequence, event sequence, then immutable
event ID; wall-clock time is never an ordering key.

The event, payload, transaction, contract, proof-manifest, and evidence-manifest identities have
separate digest domains. Ingestion time, temporary paths, hostnames, and generation timestamps cannot
silently enter semantic identity. Changing any identity profile is a contract evolution event.
