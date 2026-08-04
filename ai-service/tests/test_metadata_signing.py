import hashlib
import hmac

from app.voice_agent.metadata_signing import (
    _FIELD_SEPARATOR,
    _canonical_string,
    verify_metadata_signature,
)


def _sign(secret: str, **fields) -> str:
    canonical = _canonical_string(
        tenant_id=fields["tenant_id"],
        session_id=fields["session_id"],
        session_type=fields["session_type"],
        resume_context=fields.get("resume_context"),
    )
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def _metadata(signature: str, **fields) -> dict:
    return {
        "tenantId": fields["tenant_id"],
        "sessionId": fields["session_id"],
        "sessionType": fields["session_type"],
        "resumeContext": fields.get("resume_context"),
        "metadataSignature": signature,
    }


def test_valid_signature_verifies() -> None:
    fields = dict(tenant_id="t1", session_id="s1", session_type="candidate_interview")
    signature = _sign("secret", **fields)
    assert verify_metadata_signature(_metadata(signature, **fields), "secret") is True


def test_tampered_field_fails_verification() -> None:
    fields = dict(tenant_id="t1", session_id="s1", session_type="candidate_interview")
    signature = _sign("secret", **fields)
    metadata = _metadata(signature, **fields)
    metadata["resumeContext"] = "attacker-controlled content"
    assert verify_metadata_signature(metadata, "secret") is False


def test_wrong_secret_fails_verification() -> None:
    fields = dict(tenant_id="t1", session_id="s1", session_type="candidate_interview")
    signature = _sign("secret", **fields)
    assert verify_metadata_signature(_metadata(signature, **fields), "wrong-secret") is False


def test_missing_signature_fails_closed() -> None:
    metadata = {"tenantId": "t1", "sessionId": "s1", "sessionType": "candidate_interview"}
    assert verify_metadata_signature(metadata, "secret") is False


def test_missing_required_field_fails_closed() -> None:
    fields = dict(tenant_id="t1", session_id="s1", session_type="candidate_interview")
    signature = _sign("secret", **fields)
    metadata = _metadata(signature, **fields)
    del metadata["tenantId"]
    assert verify_metadata_signature(metadata, "secret") is False


def test_empty_metadata_fails_closed() -> None:
    assert verify_metadata_signature({}, "secret") is False


def test_matches_known_good_cross_language_value() -> None:
    # Same fixed inputs as platform/test/room-metadata-signing.spec.ts's
    # cross-language test — both must produce this exact digest.
    signature = _sign(
        "test-secret",
        tenant_id="t1",
        session_id="s1",
        session_type="candidate_interview",
        resume_context="some resume text",
    )
    assert signature == "3ac3022644bc02025729ffae41cca1bbbb7c722df81249a81efba38445a3d827"


def test_field_separator_matches_typescript_side() -> None:
    assert _FIELD_SEPARATOR == "\x01"
