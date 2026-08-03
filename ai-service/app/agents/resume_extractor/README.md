# Resume extractor agent
#
# Pipeline: upload → validate → Docling (or legacy-doc / PyMuPDF+EasyOCR) → normalize →
# model_gateway(resume_parsing) → Pydantic ResumeJSON → SSE stages to the client.
#
# Roles:
# - Docling = text/layout extraction (not an LLM)
# - LLM_MODE=local = local transformers/torch instruct model maps text → ResumeJSON
# - LLM_MODE=openrouter|gemini|mock = remote/stub mapping instead
#
# Install (from ai-service/):
#   pip install -r requirements.txt
# First Docling/EasyOCR/local-LLM run may download models to ~/.cache/huggingface.
# For first local model download: HF_HUB_OFFLINE=0, then set back to 1.
#
# Env: see ../../.env.example (LLM_MODE, LOCAL_LLM_*, OPENAI_API_KEY, CORS_ORIGINS, …)
