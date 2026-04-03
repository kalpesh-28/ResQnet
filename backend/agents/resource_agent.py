"""
Resource Agent — ResQnet Disaster Response Coordination System
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


def _build_prompt(incidents: list, resources: list, triage_result: dict) -> str:
    return f"""Return a JSON object mapping resources to disaster incidents.
Resources: {json.dumps(resources)}
Triage: {json.dumps(triage_result)}

Return ONLY this exact JSON structure, nothing else:
{{
  "available_teams": ["RES-001", "RES-002", "RES-003"],
  "recommended_assignments": [
    {{"resource_id": "RES-002", "incident_id": "INC-002", "reason": "<one sentence>"}},
    {{"resource_id": "RES-001", "incident_id": "INC-001", "reason": "<one sentence>"}},
    {{"resource_id": "RES-003", "incident_id": "INC-003", "reason": "<one sentence>"}}
  ],
  "capacity_assessment": "<one sentence>",
  "gaps": ["<gap 1>", "<gap 2>"],
  "readiness_score": 8
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
        logger.error("[ResourceAgent] All 3 parse strategies failed.")
        logger.error("[ResourceAgent] raw_text repr: %s", repr(raw_text[:800]))

    return result


async def run_resource_agent(incidents: list, resources: list, triage_result: dict) -> dict:
    logger.info("[ResourceAgent] Starting resource allocation analysis...")

    try:
        prompt = _build_prompt(incidents, resources, triage_result)
        result = await asyncio.to_thread(_call_gemini, prompt)

        if result is None:
            raise ValueError("JSON parsing returned None after cleaning")

        result["agent"] = "ResourceAgent"
        result["status"] = "success"
        logger.info("[ResourceAgent] Allocation complete. %d assignments made.",
                    len(result.get("recommended_assignments", [])))
        return result

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("[ResourceAgent] Failed: %s", exc)
        return {
            "agent": "ResourceAgent",
            "status": "error",
            "error": str(exc),
            "available_teams": ["RES-001", "RES-002", "RES-003"],
            "recommended_assignments": [
                {"resource_id": "RES-002", "incident_id": "INC-002", "reason": "Fallback: NDRF Bravo matches building collapse USAR."},
                {"resource_id": "RES-001", "incident_id": "INC-001", "reason": "Fallback: NDRF Alpha matches flood rescue."},
                {"resource_id": "RES-003", "incident_id": "INC-003", "reason": "Fallback: NDRF Charlie matches road clearance."},
                {"resource_id": "RES-004", "incident_id": "INC-001", "reason": "Fallback: Nashik hospital supports flood casualties."},
                {"resource_id": "RES-005", "incident_id": "INC-002", "reason": "Fallback: Sassoon Hospital supports collapse casualties."},
                {"resource_id": "RES-006", "incident_id": "INC-001", "reason": "Fallback: Helicopter for aerial flood rescue."}
            ],
            "capacity_assessment": "All resources deployed via fallback assignment.",
            "gaps": ["No hospital coverage for Sambhajinagar", "Manual verification required"],
            "readiness_score": 5
        }
