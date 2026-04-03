"""
Orchestrator — ResQnet Disaster Response Coordination System

Runs the complete 6-agent disaster response pipeline sequentially.
Broadcasts real-time progress updates via WebSocket after each agent completes.
Updates resource statuses based on coordination agent dispatch orders.
"""

import asyncio
import logging
from datetime import datetime, timezone
from copy import deepcopy

from agents.situation_agent import run_situation_agent
from agents.triage_agent import run_triage_agent
from agents.resource_agent import run_resource_agent
from agents.coordination_agent import run_coordination_agent
from agents.communication_agent import run_communication_agent
from agents.reporting_agent import run_reporting_agent
from websocket_manager import manager

logger = logging.getLogger(__name__)

# Delay (seconds) between agent steps to allow frontend to display progress smoothly
INTER_AGENT_DELAY = 1.5


def _build_broadcast_envelope(
    step: int,
    total_steps: int,
    agent_name: str,
    status: str,
    data: dict,
    message: str = "",
) -> dict:
    """Build a standardized WebSocket broadcast envelope."""
    return {
        "event": "agent_update",
        "step": step,
        "total_steps": total_steps,
        "agent": agent_name,
        "status": status,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def _apply_resource_updates(resources: list, dispatch_orders: list) -> list:
    """
    Update resource status and assigned_to fields based on coordination dispatch orders.
    Returns a deep copy of resources with updated statuses.
    """
    updated = deepcopy(resources)
    order_map = {order["resource_id"]: order for order in dispatch_orders}

    for resource in updated:
        rid = resource.get("id")
        if rid in order_map:
            order = order_map[rid]
            resource["status"] = "deployed"
            resource["assigned_to"] = order.get("assigned_to_incident")
            resource["deployment_order"] = order.get("order_id")
            resource["mission"] = order.get("mission")
            resource["eta_hours"] = order.get("eta_hours")
            logger.info(
                "[Orchestrator] Resource %s → deployed to %s",
                rid,
                order.get("assigned_to_incident"),
            )

    return updated


async def run_pipeline(incidents: list, resources: list) -> dict:
    """
    Execute the complete 6-agent disaster response pipeline.

    Steps:
    1. Situation Agent   → overall situational assessment
    2. Triage Agent      → priority ranking
    3. Resource Agent    → recommended assignments
    4. Coordination Agent → FINAL dispatch decisions
    5. Communication Agent → advisories + briefings
    6. Reporting Agent   → full incident report

    Broadcasts a WebSocket event after EVERY agent step.
    Returns the complete full_context dictionary.
    """
    total_steps = 6
    pipeline_start = datetime.now(timezone.utc)
    logger.info("[Orchestrator] === PIPELINE STARTED === %s", pipeline_start.isoformat())

    full_context = {
        "pipeline_started_at": pipeline_start.isoformat(),
        "incidents": incidents,
        "resources_initial": resources,
    }

    # ─────────────────────────────────────────────
    # STEP 1: Situation Agent
    # ─────────────────────────────────────────────
    logger.info("[Orchestrator] Step 1/6 — SituationAgent")
    await manager.broadcast(
        _build_broadcast_envelope(
            step=1,
            total_steps=total_steps,
            agent_name="SituationAgent",
            status="running",
            data={},
            message="Performing overall situational assessment of all active incidents...",
        )
    )

    situation_result = await run_situation_agent(incidents, resources)
    full_context["situation"] = situation_result

    await manager.broadcast(
        _build_broadcast_envelope(
            step=1,
            total_steps=total_steps,
            agent_name="SituationAgent",
            status="complete",
            data=situation_result,
            message=f"Situational assessment complete. Overall status: {situation_result.get('overall_status', 'N/A')}",
        )
    )
    await asyncio.sleep(INTER_AGENT_DELAY)

    # ─────────────────────────────────────────────
    # STEP 2: Triage Agent
    # ─────────────────────────────────────────────
    logger.info("[Orchestrator] Step 2/6 — TriageAgent")
    await manager.broadcast(
        _build_broadcast_envelope(
            step=2,
            total_steps=total_steps,
            agent_name="TriageAgent",
            status="running",
            data={},
            message="Ranking incidents by priority using multi-factor triage scoring...",
        )
    )

    triage_result = await run_triage_agent(incidents, resources, situation_result)
    full_context["triage"] = triage_result

    top_priority = (triage_result.get("recommended_dispatch_sequence") or ["N/A"])[0]
    await manager.broadcast(
        _build_broadcast_envelope(
            step=2,
            total_steps=total_steps,
            agent_name="TriageAgent",
            status="complete",
            data=triage_result,
            message=f"Triage complete. Top priority incident: {top_priority}",
        )
    )
    await asyncio.sleep(INTER_AGENT_DELAY)

    # ─────────────────────────────────────────────
    # STEP 3: Resource Agent
    # ─────────────────────────────────────────────
    logger.info("[Orchestrator] Step 3/6 — ResourceAgent")
    await manager.broadcast(
        _build_broadcast_envelope(
            step=3,
            total_steps=total_steps,
            agent_name="ResourceAgent",
            status="running",
            data={},
            message="Analyzing available resources and generating optimal allocation recommendations...",
        )
    )

    resource_result = await run_resource_agent(incidents, resources, triage_result)
    full_context["resource_allocation"] = resource_result

    assignment_count = len(resource_result.get("recommended_assignments", []))
    await manager.broadcast(
        _build_broadcast_envelope(
            step=3,
            total_steps=total_steps,
            agent_name="ResourceAgent",
            status="complete",
            data=resource_result,
            message=f"Resource allocation complete. {assignment_count} resources mapped to incidents.",
        )
    )
    await asyncio.sleep(INTER_AGENT_DELAY)

    # ─────────────────────────────────────────────
    # STEP 4: Coordination Agent (MOST CRITICAL)
    # ─────────────────────────────────────────────
    logger.info("[Orchestrator] Step 4/6 — CoordinationAgent (CRITICAL)")
    await manager.broadcast(
        _build_broadcast_envelope(
            step=4,
            total_steps=total_steps,
            agent_name="CoordinationAgent",
            status="running",
            data={},
            message="⚡ CRITICAL: Issuing final authoritative dispatch orders for all resources...",
        )
    )

    coordination_result = await run_coordination_agent(
        incidents, resources, situation_result, triage_result, resource_result
    )
    full_context["coordination"] = coordination_result

    # Apply dispatch decisions to resource statuses
    dispatch_orders = coordination_result.get("dispatch_orders", [])
    updated_resources = _apply_resource_updates(resources, dispatch_orders)
    full_context["resources_deployed"] = updated_resources

    order_count = len(dispatch_orders)
    operation_name = coordination_result.get("operation_name", "Unknown Operation")
    await manager.broadcast(
        _build_broadcast_envelope(
            step=4,
            total_steps=total_steps,
            agent_name="CoordinationAgent",
            status="complete",
            data={**coordination_result, "resources_deployed": updated_resources},
            message=f"🚨 DISPATCH COMPLETE — {operation_name} | {order_count} orders issued.",
        )
    )
    await asyncio.sleep(INTER_AGENT_DELAY)

    # ─────────────────────────────────────────────
    # STEP 5: Communication Agent
    # ─────────────────────────────────────────────
    logger.info("[Orchestrator] Step 5/6 — CommunicationAgent")
    await manager.broadcast(
        _build_broadcast_envelope(
            step=5,
            total_steps=total_steps,
            agent_name="CommunicationAgent",
            status="running",
            data={},
            message="Generating public advisories, press briefing, and inter-agency communications...",
        )
    )

    communication_result = await run_communication_agent(
        incidents, coordination_result, triage_result
    )
    full_context["communications"] = communication_result

    advisory_count = len(communication_result.get("public_advisories", []))
    await manager.broadcast(
        _build_broadcast_envelope(
            step=5,
            total_steps=total_steps,
            agent_name="CommunicationAgent",
            status="complete",
            data=communication_result,
            message=f"Communications ready. {advisory_count} public advisories issued.",
        )
    )
    await asyncio.sleep(INTER_AGENT_DELAY)

    # ─────────────────────────────────────────────
    # STEP 6: Reporting Agent
    # ─────────────────────────────────────────────
    logger.info("[Orchestrator] Step 6/6 — ReportingAgent")
    await manager.broadcast(
        _build_broadcast_envelope(
            step=6,
            total_steps=total_steps,
            agent_name="ReportingAgent",
            status="running",
            data={},
            message="Compiling final operational incident report from all pipeline outputs...",
        )
    )

    reporting_result = await run_reporting_agent(full_context)
    full_context["report"] = reporting_result

    pipeline_end = datetime.now(timezone.utc)
    duration_sec = (pipeline_end - pipeline_start).total_seconds()
    full_context["pipeline_completed_at"] = pipeline_end.isoformat()
    full_context["pipeline_duration_sec"] = round(duration_sec, 2)

    await manager.broadcast(
        _build_broadcast_envelope(
            step=6,
            total_steps=total_steps,
            agent_name="ReportingAgent",
            status="complete",
            data=reporting_result,
            message=f"Final report ready. Assessment: {reporting_result.get('overall_assessment', 'N/A')} | Duration: {round(duration_sec, 1)}s",
        )
    )

    # ─────────────────────────────────────────────
    # FINAL BROADCAST — Complete pipeline context
    # ─────────────────────────────────────────────
    await manager.broadcast(
        {
            "event": "pipeline_complete",
            "timestamp": pipeline_end.isoformat(),
            "duration_sec": round(duration_sec, 2),
            "operation_name": operation_name,
            "overall_assessment": reporting_result.get("overall_assessment", "N/A"),
            "message": f"✅ Pipeline complete in {round(duration_sec, 1)}s — {operation_name}",
            "full_context": full_context,
        }
    )

    logger.info(
        "[Orchestrator] === PIPELINE COMPLETE === Duration: %.2fs | Operation: %s",
        duration_sec,
        operation_name,
    )
    return full_context
