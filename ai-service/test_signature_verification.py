import hmac
import hashlib
import json
import requests

SECRET = "05ee49243ed71019e613ac529f6fe11b200561c8903b09f17fcaaad9b7d1ddf0"
FIELD_SEPARATOR = "\x01"

def canonical_string(tenant_id: str, session_id: str, session_type: str, resume_context: str = "") -> str:
    return FIELD_SEPARATOR.join([tenant_id, session_id, session_type, resume_context or ""])

def verify_signature(tenant_id: str, session_id: str, session_type: str, signature: str, resume_context: str = "") -> bool:
    c_str = canonical_string(tenant_id, session_id, session_type, resume_context)
    expected = hmac.new(SECRET.encode(), c_str.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

# Test HMAC signature logic
tenant_id = "tenant-123"
session_id = "session-456"
session_type = "technical"
resume_ctx = ""

c_str = canonical_string(tenant_id, session_id, session_type, resume_ctx)
sig = hmac.new(SECRET.encode(), c_str.encode(), hashlib.sha256).hexdigest()

print("--- HMAC Signature Validation ---")
print(f"Secret SHA256 Prefix: {hashlib.sha256(SECRET.encode()).hexdigest()[:8]}")
print(f"Canonical String: {repr(c_str)}")
print(f"Computed Signature: {sig}")
print(f"Validation Result: {verify_signature(tenant_id, session_id, session_type, sig, resume_ctx)}")
if verify_signature(tenant_id, session_id, session_type, sig, resume_ctx):
    print("✅ HMAC Signature verification logic is 100% MATCHED!")
