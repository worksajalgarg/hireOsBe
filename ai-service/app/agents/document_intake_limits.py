"""Shared limits for the two file-upload intake routes (resume_intelligence,
role_intelligence) — was independently duplicated in both modules (same
four values, byte-for-byte identical) until this file existed. Both routes
parse untrusted uploaded bytes through the same app/agents/parsing pipeline
and apply the same acceptance rules, so there's one real source of truth
here rather than two copies that could silently drift apart."""

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB

MIN_EXTRACTABLE_CHARS = 50  # below this, likely a scanned/image-only file

# docling/pypdfium2 are synchronous native-backed libraries parsing
# untrusted bytes (zip bombs, XML entity expansion, pathological PDFs) —
# bound the wall-clock cost regardless of cause. 45s (not the original
# 15s): docling's PDF engine (default as of this session — see
# document_parser.py's pdf_engine()) profiled at ~22s cold-process model
# load even with the DocumentConverter singleton, plus actual conversion
# time on top; 15s was cutting it close on a warm process and guaranteed to
# fail a cold one. Startup warm-up (app/main.py's _lifespan) means a cold
# hit here should be rare in practice.
PARSE_TIMEOUT_S = 45.0

# Below this, a genuinely short document (a one-line JD posting, a very
# short resume) legitimately having little to extract is plausible — above
# it, a fully empty result is far more likely a weak/failed extraction than
# a document with truly nothing in it.
MIN_CHARS_FOR_EMPTY_CHECK = 300
