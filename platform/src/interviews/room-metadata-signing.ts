import { createHmac } from "crypto";

/**
 * HMAC-signs LiveKit room metadata so ai-service's voice_agent worker can
 * verify a dispatched room's metadata actually came from platform's
 * createSession(), not a room created directly against LiveKit's API with
 * forged tenantId/sessionId/sessionType/resumeContext — see
 * docs/adr/0006-interview-transcript-storage.md and the Phase E section of
 * the source plan.
 *
 * Signs a fixed, explicit delimiter-joined string rather than JSON — two
 * different languages' JSON serializers (JS JSON.stringify, Python
 * json.dumps) are not guaranteed byte-identical (key order, whitespace,
 * escaping), which would make an HMAC over "the JSON" silently fragile.
 * ai-service/app/voice_agent/metadata_signing.py must build this exact
 * same canonical string — keep the two in sync by hand.
 */

// U+0001 (SOH) — a control character that can't appear in any of these
// fields in practice, so it can't be used to construct a collision (e.g. a
// resumeContext crafted to shift field boundaries).
const FIELD_SEPARATOR = "";

export interface SignableRoomMetadata {
  tenantId: string;
  sessionId: string;
  sessionType: string;
  resumeContext?: string;
}

function canonicalString(metadata: SignableRoomMetadata): string {
  return [
    metadata.tenantId,
    metadata.sessionId,
    metadata.sessionType,
    metadata.resumeContext ?? "",
  ].join(FIELD_SEPARATOR);
}

export function signRoomMetadata(secret: string, metadata: SignableRoomMetadata): string {
  return createHmac("sha256", secret).update(canonicalString(metadata)).digest("hex");
}
