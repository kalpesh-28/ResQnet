"""
Situation Agent — ResQnet Disaster Response Coordination System
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


def _build_prompt(incidents: list, resources: list) -> str:
    return f"""Return a JSON object assessing these disasters.
Incidents: {json.dumps(incidents)}

Return ONLY this exact JSON structure, nothing else:
{{
  "overall_severity": "critical",
  "total_affected": 0,
  "active_zones": ["Nashik", "Pune", "Sambhajinagar"],
  "cross_incident_risk": "<one sentence>",
  "immediate_priorities": ["<priority 1>", "<priority 2>", "<priority 3>"],
  "assessment_summary": "<two sentences>"
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
            temperature=0.3,
            max_output_tokens=2048,
            response_mime_type="application/json",
        ),
    )
    response = model.generate_content(prompt)
    raw_text = response.text or ""

    # Strategy 1: clean (strip fences, find first { to last })
    cleaned = _clean_llm_output(raw_text)
    result = safe_parse_json(cleaned)

    # Strategy 2: parse raw directly (response_mime_type may give clean JSON)
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
        logger.error("[SituationAgent] All 3 parse strategies failed.")
        logger.error("[SituationAgent] raw_text repr: %s", repr(raw_text[:800]))

    return result


async def run_situation_agent(incidents: list, resources: list) -> dict:
    logger.info("[SituationAgent] Starting situational assessment...")

    try:
        prompt = _build_prompt(incidents, resources)
        result = await asyncio.to_thread(_call_gemini, prompt)

        if result is None:
            raise ValueError("JSON parsing returned None after cleaning")

        result["agent"] = "SituationAgent"
        result["status"] = "success"
        logger.info("[SituationAgent] Assessment complete. Severity: %s", result.get("overall_severity"))
        return result

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("[SituationAgent] Failed: %s", exc)
        return {
            "agent": "SituationAgent",
            "status": "error",
            "error": str(exc),
            "overall_severity": "unknown",
            "total_affected": 0,
            "active_zones": ["Nashik", "Pune", "Sambhajinagar"],
            "cross_incident_risk": "Assessment unavailable — fallback mode active.",
            "immediate_priorities": [
                "Deploy NDRF to Pune building collapse",
                "Flood rescue in Nashik",
                "Road clearance in Sambhajinagar"
            ],
            "assessment_summary": "Situational assessment failed. Manual review required. Fallback priorities applied."
        }
