import { signRoomMetadata } from "../src/interviews/room-metadata-signing";

describe("signRoomMetadata", () => {
  const base = {
    tenantId: "tenant-a",
    sessionId: "session-1",
    sessionType: "candidate_interview",
    resumeContext: "some resume text",
  };

  it("is deterministic for the same inputs", () => {
    expect(signRoomMetadata("secret", base)).toBe(signRoomMetadata("secret", base));
  });

  it("changes when any signed field changes", () => {
    const original = signRoomMetadata("secret", base);
    expect(signRoomMetadata("secret", { ...base, tenantId: "tenant-b" })).not.toBe(original);
    expect(signRoomMetadata("secret", { ...base, sessionId: "session-2" })).not.toBe(original);
    expect(signRoomMetadata("secret", { ...base, sessionType: "hiring_manager_discovery" })).not.toBe(
      original,
    );
    expect(signRoomMetadata("secret", { ...base, resumeContext: "tampered" })).not.toBe(original);
  });

  it("changes when the secret changes", () => {
    expect(signRoomMetadata("secret-a", base)).not.toBe(signRoomMetadata("secret-b", base));
  });

  it("treats an absent resumeContext the same as an empty one", () => {
    const { resumeContext: _drop, ...withoutResumeContext } = base;
    expect(signRoomMetadata("secret", withoutResumeContext)).toBe(
      signRoomMetadata("secret", { ...base, resumeContext: "" }),
    );
  });

  it("matches the known-good cross-language value computed by ai-service's Python implementation", () => {
    // Cross-checked once by hand against app/voice_agent/metadata_signing.py
    // with the same inputs — see docs/adr/0006-interview-transcript-storage.md.
    // Guards against the two implementations silently drifting apart.
    expect(
      signRoomMetadata("test-secret", {
        tenantId: "t1",
        sessionId: "s1",
        sessionType: "candidate_interview",
        resumeContext: "some resume text",
      }),
    ).toBe("3ac3022644bc02025729ffae41cca1bbbb7c722df81249a81efba38445a3d827");
  });
});
