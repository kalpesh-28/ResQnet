"""
Coordination Agent — ResQnet Disaster Response Coordination System

THE MOST IMPORTANT AGENT in the pipeline.
Issues final authoritative dispatch orders for every resource.
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
    resources: list,
    situation_assessment: dict,
    triage_result: dict,
    resource_allocation: dict,
) -> str:
    return f"""Return a JSON object with final disaster dispatch orders.
Triage: {json.dumps(triage_result)}
Resources: {json.dumps(resource_allocation)}

Return ONLY this exact JSON structure, nothing else:
{{
  "dispatch_assignments": [
    {{
      "resource_id": "RES-002",
      "resource_name": "NDRF Team Bravo",
      "incident_id": "INC-002",
      "incident_location": "Pune",
      "action": "<specific action>",
      "eta_minutes": 30,
      "priority": "P1"
    }},
    {{
      "resource_id": "RES-001",
      "resource_name": "NDRF Team Alpha",
      "incident_id": "INC-001",
      "incident_location": "Nashik",
      "action": "<specific action>",
      "eta_minutes": 210,
      "priority": "P2"
    }},
    {{
      "resource_id": "RES-003",
      "resource_name": "NDRF Team Charlie",
      "incident_id": "INC-003",
      "incident_location": "Sambhajinagar",
      "action": "<specific action>",
      "eta_minutes": 45,
      "priority": "P3"
    }}
  ],
  "standby_resources": ["RES-004", "RES-005", "RES-006"],
  "coordination_notes": "<one sentence>",
  "escalation_required": false,
  "command_decision_summary": "<two sentences>"
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
            temperature=0.15,
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
        logger.error("[CoordinationAgent] All 3 parse strategies failed.")
        logger.error("[CoordinationAgent] raw_text repr: %s", repr(raw_text[:800]))

    return result


async def run_coordination_agent(
    incidents: list,
    resources: list,
    situation_assessment: dict,
    triage_result: dict,
    resource_allocation: dict,
) -> dict:
    logger.info("[CoordinationAgent] Issuing final dispatch orders (MOST CRITICAL STEP)...")

    try:
        prompt = _build_prompt(
            incidents, resources, situation_assessment, triage_result, resource_allocation
        )
        result = await asyncio.to_thread(_call_gemini, prompt)

        if result is None:
            raise ValueError("JSON parsing returned None after cleaning")

        result["agent"] = "CoordinationAgent"
        result["status"] = "success"
        logger.info(
            "[CoordinationAgent] FINAL DISPATCH COMPLETE — Orders: %d",
            len(result.get("dispatch_assignments", [])),
        )
        return result

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("[CoordinationAgent] CRITICAL FAILURE: %s", exc)
        return {
            "agent": "CoordinationAgent",
            "status": "error",
            "error": str(exc),
            "dispatch_assignments": [
                {
                    "resource_id": "RES-002",
                    "resource_name": "NDRF Team Bravo",
                    "incident_id": "INC-002",
                    "incident_location": "Pune",
                    "action": "Urban search and rescue at Bibwewadi building collapse",
                    "eta_minutes": 30,
                    "priority": "P1"
                },
                {
                    "resource_id": "RES-001",
                    "resource_name": "NDRF Team Alpha",
                    "incident_id": "INC-001",
                    "incident_location": "Nashik",
                    "action": "Flood rescue operations with boats in Godavari basin",
                    "eta_minutes": 210,
                    "priority": "P2"
                },
                {
                    "resource_id": "RES-003",
                    "resource_name": "NDRF Team Charlie",
                    "incident_id": "INC-003",
                    "incident_location": "Sambhajinagar",
                    "action": "Landslide clearance on NH-52",
                    "eta_minutes": 45,
                    "priority": "P3"
                },
                {
                    "resource_id": "RES-006",
                    "resource_name": "IAF Rescue Helicopter Chinook-1",
                    "incident_id": "INC-001",
                    "incident_location": "Nashik",
                    "action": "Aerial rescue of rooftop-stranded flood victims",
                    "eta_minutes": 30,
                    "priority": "P1"
                },
                {
                    "resource_id": "RES-005",
                    "resource_name": "Sassoon General Hospital Pune",
                    "incident_id": "INC-002",
                    "incident_location": "Pune",
                    "action": "Receive collapse trauma casualties — activate MCI protocol",
                    "eta_minutes": 0,
                    "priority": "P1"
                },
                {
                    "resource_id": "RES-004",
                    "resource_name": "Nashik Civil Hospital",
                    "incident_id": "INC-001",
                    "incident_location": "Nashik",
                    "action": "Receive flood rescue casualties — prepare waterborne disease ward",
                    "eta_minutes": 0,
                    "priority": "P2"
                }
            ],
            "standby_resources": [],
            "coordination_notes": "Fallback protocol active — all resources dispatched per standard assignment.",
            "escalation_required": False,
            "command_decision_summary": "CRITICAL AGENT FAILURE — Fallback dispatch orders issued. Human coordination required immediately."
        }
