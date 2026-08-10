# Resume extractor

The production path is:

`upload → signature/size validation → Docling → normalization → section-aware chunks → model gateway → strict ResumeJSON v2 → deterministic merge → SSE result`

Docling extracts text, reading order, OCR and tables. It is not used as an LLM. The configured model only maps untrusted resume text into the approved JSON contract.

## Output

`ResumeJSON` includes contact details, headline, summary, the complete employment and education timeline, skills and skill groups, projects, certifications, awards, publications, volunteering, languages, interests, additional sections, verification topics, short source-evidence quotes, and extraction metadata.

Long resumes are processed in multiple chunks without silently dropping the tail. Each chunk is strictly validated, one correction attempt is allowed, and valid chunks are merged deterministically. Incomplete JSON and automatic mock fallbacks fail the extraction instead of being persisted as real candidate data.

## Runtime

Install from `ai-service/`:

```bash
pip install -r requirements.txt
```

Set `LLM_MODE=local`, `openrouter`, `gemini`, or `mock`. Mock mode is only for explicit development testing. Keep `LLM_FALLBACK_TO_MOCK=false` whenever extracted data can be persisted.

Local mode defaults to `Qwen/Qwen2.5-3B-Instruct`. Docling, OCR and local-model assets must be downloaded once with `HF_HUB_OFFLINE=0`; after the cache is populated, use `HF_HUB_OFFLINE=1`.

In production, set the same non-empty `AI_SERVICE_TOKEN` in the platform and AI service, and expose the AI service only on the private network.
