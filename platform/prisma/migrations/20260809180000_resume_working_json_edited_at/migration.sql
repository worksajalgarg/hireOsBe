-- Tracks whether a recruiter has genuinely edited resumes.working_json via
-- PATCH /resumes/:id — distinguishes that from working_json merely being
-- auto-seeded by the first extraction attempt (which may have been a
-- broken/garbled parse and shouldn't permanently block later re-extraction
-- from refreshing working_json).
ALTER TABLE "resumes" ADD COLUMN "working_json_edited_at" TIMESTAMP(3);
