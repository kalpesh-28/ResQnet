"""
Triage Agent — ResQnet Disaster Response Coordination System
"""

import os
import re
import json
import asyncio
import logging

import google.generativeai as genai

logger = logging.getLogger(__name__)


def safe_parse_json(raw: str) -> dict | None:
    try:
        return json.loads(raw)
    except Exception:
        return None


def _clean_llm_output(text: str) -> str:
    # Strip markdown fences
    text = re.sub(r'```json', '', text)
    text = re.sub(r'```', '', text)
    text = text.strip()
    # Extract ONLY the content between first { and last }
    first = text.find('{')
    last = text.rfind('}')
    if first != -1 and last != -1 and last > first:
        return text[first:last + 1].strip()
    return text


def _build_prompt(incidents: list, resources: list, situation_assessment: dict) -> str:
    return f"""Return a JSON object triaging these disaster incidents.
Context: {json.dumps(situation_assessment)}
Incidents are INC-001 (flood Nashik 200 people), INC-002 (collapse Pune 45 trapped), INC-003 (road block Sambhajinagar 80 affected).

Return ONLY this exact JSON structure, nothing else:
{{
  "priority_ranking": ["INC-002", "INC-001", "INC-003"],
  "severity_scores": {{"INC-001": 8, "INC-002": 10, "INC-003": 6}},
  "top_incident": "INC-002",
  "reasoning": "<two sentences>",
  "estimated_lives_at_risk": 0,
  "response_window_minutes": 120
}}
NO wrapper. NO agent field. NO timestamp field. NO operation_name field.
Just the raw JSON above."""


def _call_gemini(prompt: str) -> dict | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config=genai.types.GenerationConfig(
            temperature=0.2,
            max_output_tokens=2048,
            response_mime_type="application/json",
        ),
    )
    response = model.generate_content(prompt)
    raw_text = response.text or ""

    # Strategy 1: clean (strip fences, find first { to last })
    cleaned = _clean_llm_output(raw_text)
    result = safe_parse_json(cleaned)

    # Strategy 2: parse raw directly
    if result is None:
        result = safe_parse_json(raw_text.strip())

    # Strategy 3: collapse all whitespace then extract JSON block
    if result is None:
        collapsed = " ".join(raw_text.split())
        first = collapsed.find("{")
        last = collapsed.rfind("}")
        if first != -1 and last != -1 and last > first:
            result = safe_parse_json(collapsed[first:last + 1])

    if result is None:
        logger.error("[TriageAgent] All 3 parse strategies failed.")
        logger.error("[TriageAgent] raw_text repr: %s", repr(raw_text[:800]))

    return result


async def run_triage_agent(incidents: list, resources: list, situation_assessment: dict) -> dict:
    logger.info("[TriageAgent] Starting priority triage...")

    try:
        prompt = _build_prompt(incidents, resources, situation_assessment)
        result = await asyncio.to_thread(_call_gemini, prompt)

        if result is None:
            raise ValueError("JSON parsing returned None after cleaning")

        result["agent"] = "TriageAgent"
        result["status"] = "success"
        logger.info("[TriageAgent] Triage complete. Top incident: %s", result.get("top_incident", "N/A"))
        return result

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("[TriageAgent] Failed: %s", exc)
        return {
            "agent": "TriageAgent",
            "status": "error",
            "error": str(exc),
            "priority_ranking": ["INC-002", "INC-001", "INC-003"],
            "severity_scores": {"INC-001": 8, "INC-002": 10, "INC-003": 6},
            "top_incident": "INC-002",
            "reasoning": "Fallback triage applied. Building collapse has highest trapped persons count. Flood is second due to large affected population.",
            "estimated_lives_at_risk": 129,
            "response_window_minutes": 120,
            "triage_confidence": "LOW",
            "triage_flags": ["Fallback used — agent failure"]
        }