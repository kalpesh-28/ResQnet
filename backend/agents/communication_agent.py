"""
Communication Agent — ResQnet Disaster Response Coordination System
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


def _build_prompt(
    incidents: list,
    coordination_result: dict,
    triage_result: dict,
) -> str:
    situation = {
        "incidents": incidents,
        "triage": triage_result
    }
    dispatch = coordination_result
    return f"""Return a JSON object with emergency communications for a disaster response.
Situation: {json.dumps(situation)}
Dispatch: {json.dumps(dispatch)}

Return ONLY this exact JSON structure, nothing else:
{{
  "public_advisory_english": "<under 160 chars>",
  "public_advisory_hindi": "<under 160 chars in Hindi>",
  "field_team_briefings": [
    {{"team_id": "RES-001", "briefing_text": "<briefing>"}},
    {{"team_id": "RES-002", "briefing_text": "<briefing>"}},
    {{"team_id": "RES-003", "briefing_text": "<briefing>"}}
  ],
  "media_statement": "<three sentences>",
  "helpline_message": "<one sentence>"
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
            temperature=0.4,
            max_output_tokens=3072,
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
        logger.error("[CommunicationAgent] All 3 parse strategies failed.")
        logger.error("[CommunicationAgent] raw_text repr: %s", repr(raw_text[:800]))

    return result


async def run_communication_agent(
    incidents: list,
    coordination_result: dict,
    triage_result: dict,
) -> dict:
    logger.info("[CommunicationAgent] Generating public advisories and briefings...")

    try:
        prompt = _build_prompt(incidents, coordination_result, triage_result)
        result = await asyncio.to_thread(_call_gemini, prompt)

        if result is None:
            raise ValueError("JSON parsing returned None after cleaning")

        result["agent"] = "CommunicationAgent"
        result["status"] = "success"
        logger.info("[CommunicationAgent] Communications generated successfully.")
        return result

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("[CommunicationAgent] Failed: %s", exc)
        return {
            "agent": "CommunicationAgent",
            "status": "error",
            "error": str(exc),
            "public_advisory_english": "EMERGENCY: Disasters active in Nashik, Pune, Sambhajinagar. Follow official instructions. Helpline: 1070.",
            "public_advisory_hindi": "आपातकाल: नासिक, पुणे, औरंगाबाद में आपदाएं सक्रिय हैं। आधिकारिक निर्देशों का पालन करें। हेल्पलाइन: 1070।",
            "field_team_briefings": [
                {"team_id": "RES-001", "briefing_text": "NDRF Alpha: Deploy flood rescue in Nashik Godavari basin. Use boats. Coordinate with District Collector."},
                {"team_id": "RES-002", "briefing_text": "NDRF Bravo: Urban search and rescue at Bibwewadi collapse, Pune. Activate USAR protocol immediately."},
                {"team_id": "RES-003", "briefing_text": "NDRF Charlie: Clear NH-52 landslide near Sambhajinagar. Liaise with NHAI. Restore emergency lane."}
            ],
            "media_statement": "The Maharashtra government has deployed NDRF teams and aerial assets across three simultaneous disasters. All available resources are operational. Citizens are advised to follow official guidance and contact helpline 1070.",
            "helpline_message": "For all disaster-related emergencies in Maharashtra, call 1070 or 112."
        }
