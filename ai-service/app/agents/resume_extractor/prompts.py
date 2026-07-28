"""Prompts for structured resume extraction via the model gateway."""

from __future__ import annotations

SYSTEM_PROMPT = """You are a resume parsing engine.
Extract ONLY facts present in the resume text. Never invent data.
Missing fields: null or [].
Return ONE compact JSON object only — no markdown, no commentary.
Keep strings short: summary ≤ 2 sentences; ≤ 3 experience roles; ≤ 2 highlights each;
≤ 15 skills; skip empty optional fields when possible.
"""

USER_PROMPT_TEMPLATE = """Map resume text to this JSON shape:
{{"contact":{{"full_name":null,"email":null,"phone":null,"location":null,"linkedin":null,"website":null}},"summary":null,"experience":[{{"company":null,"title":null,"start_date":null,"end_date":null,"location":null,"highlights":[]}}],"education":[{{"institution":null,"degree":null,"field":null,"start_date":null,"end_date":null}}],"skills":[],"certifications":[],"languages":[]}}

Resume:
---
{resume_text}
---
"""


def build_user_prompt(resume_text: str) -> str:
    return USER_PROMPT_TEMPLATE.format(resume_text=resume_text)
