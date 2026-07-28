# Resume extractor agent
#
# Pipeline: upload → validate → Docling (or PyMuPDF+EasyOCR) → normalize →
# model_gateway(resume_parsing) → Pydantic ResumeJSON → SSE stages to the client.
#
# Install (from ai-service/):
#   pip install -r requirements.txt
# First Docling/EasyOCR run may download models.
#
# Env: see ../../.env.example (OPENAI_API_KEY, CORS_ORIGINS, RESUME_MAX_UPLOAD_MB)
