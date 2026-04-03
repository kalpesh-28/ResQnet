"""
Main API — ResQnet Disaster Response Coordination System

FastAPI application exposing:
  GET  /incidents         → list all active incidents
  GET  /resources         → list all available resources
  POST /trigger-scenario  → launch AI agent pipeline in background
  WS   /agent-feed        → real-time WebSocket stream of agent updates
"""

import json
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from websocket_manager import manager
from orchestrator import run_pipeline

# ── Environment Setup ────────────────────────────────────────────────────────
load_dotenv()

# ── Logging Setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("resqnet.main")

# ── Data File Paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
INCIDENTS_FILE = DATA_DIR / "incidents.json"
RESOURCES_FILE = DATA_DIR / "resources.json"

# ── Pipeline State ───────────────────────────────────────────────────────────
pipeline_running = False
pipeline_result: dict | None = None


def _load_json(filepath: Path) -> list | dict:
    """Load and return JSON data from a file."""
    if not filepath.exists():
        raise FileNotFoundError(f"Data file not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Application Lifespan ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("═" * 60)
    logger.info("  ResQnet Disaster Response Coordination System")
    logger.info("  Backend API starting up...")
    logger.info("═" * 60)
    logger.info("  Data: %s", DATA_DIR)
    logger.info("  Incidents: %s", INCIDENTS_FILE.name)
    logger.info("  Resources: %s", RESOURCES_FILE.name)
    logger.info("═" * 60)
    yield
    logger.info("[ResQnet] Shutting down gracefully.")


# ── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="ResQnet — Disaster Response Coordination API",
    description=(
        "AI-powered multi-agent backend for real-time disaster response coordination. "
        "Runs a sequential pipeline of 6 Gemini-powered agents across active incidents "
        "in Maharashtra, India, broadcasting live updates via WebSocket."
    ),
    version="1.0.0",
    contact={
        "name": "ResQnet Emergency Command",
        "email": "command@resqnet.in",
    },
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# REST ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/",
    summary="Health Check",
    tags=["System"],
)
async def root():
    """API health check and welcome message."""
    return {
        "system": "ResQnet Disaster Response Coordination System",
        "status": "operational",
        "version": "1.0.0",
        "endpoints": {
            "incidents": "GET /incidents",
            "resources": "GET /resources",
            "trigger": "POST /trigger-scenario",
            "websocket": "WS /agent-feed",
            "docs": "GET /docs",
        },
        "active_ws_connections": manager.connection_count,
        "pipeline_running": pipeline_running,
    }


@app.get(
    "/incidents",
    summary="List All Active Incidents",
    tags=["Incidents"],
    response_class=JSONResponse,
)
async def get_incidents():
    """
    Returns all active disaster incidents loaded from incidents.json.
    Includes: Nashik Flood, Pune Building Collapse, Sambhajinagar Road Blockage.
    """
    try:
        incidents = _load_json(INCIDENTS_FILE)
        logger.info("[API] GET /incidents → %d incidents returned", len(incidents))
        return JSONResponse(
            content={
                "success": True,
                "count": len(incidents),
                "incidents": incidents,
            }
        )
    except FileNotFoundError as exc:
        logger.error("[API] Incidents file not found: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        logger.error("[API] Failed to parse incidents.json: %s", exc)
        raise HTTPException(status_code=500, detail="Invalid JSON in incidents.json") from exc


@app.get(
    "/resources",
    summary="List All Available Resources",
    tags=["Resources"],
    response_class=JSONResponse,
)
async def get_resources():
    """
    Returns all disaster response resources loaded from resources.json.
    Includes: 3 NDRF Teams, 2 Hospitals, 1 IAF Helicopter.
    """
    try:
        resources = _load_json(RESOURCES_FILE)
        logger.info("[API] GET /resources → %d resources returned", len(resources))
        return JSONResponse(
            content={
                "success": True,
                "count": len(resources),
                "resources": resources,
            }
        )
    except FileNotFoundError as exc:
        logger.error("[API] Resources file not found: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        logger.error("[API] Failed to parse resources.json: %s", exc)
        raise HTTPException(status_code=500, detail="Invalid JSON in resources.json") from exc


@app.post(
    "/trigger-scenario",
    summary="Trigger Full AI Agent Pipeline",
    tags=["Pipeline"],
    response_class=JSONResponse,
)
async def trigger_scenario(background_tasks: BackgroundTasks):
    """
    Triggers the complete 6-agent disaster response pipeline as a background task.

    Pipeline sequence:
    1. SituationAgent → Overall assessment
    2. TriageAgent    → Priority ranking
    3. ResourceAgent  → Recommended assignments
    4. CoordinationAgent → FINAL dispatch orders (most critical)
    5. CommunicationAgent → Public advisories & briefings
    6. ReportingAgent → Full operational report

    All steps broadcast via WebSocket /agent-feed in real-time.
    """
    global pipeline_running, pipeline_result  # pylint: disable=global-statement

    if pipeline_running:
        logger.warning("[API] Pipeline already running — rejecting duplicate trigger")
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "message": "Pipeline is already running. Connect to /agent-feed to monitor progress.",
                "pipeline_running": True,
            },
        )

    try:
        incidents = _load_json(INCIDENTS_FILE)
        resources = _load_json(RESOURCES_FILE)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.error("[API] Failed to load data files: %s", exc)
        raise HTTPException(status_code=500, detail=f"Data load error: {exc}") from exc

    async def run_and_store():
        global pipeline_running, pipeline_result  # pylint: disable=global-statement
        pipeline_running = True
        try:
            result = await run_pipeline(incidents, resources)
            pipeline_result = result
            logger.info("[API] Pipeline completed successfully.")
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("[API] Pipeline failed with unhandled error: %s", exc)
            await manager.broadcast(
                {
                    "event": "pipeline_error",
                    "message": f"Pipeline encountered an unhandled error: {str(exc)}",
                    "error": str(exc),
                }
            )
        finally:
            pipeline_running = False

    background_tasks.add_task(run_and_store)
    logger.info("[API] POST /trigger-scenario → Pipeline launched in background")

    return JSONResponse(
        content={
            "success": True,
            "message": "AI pipeline launched. Connect to ws://<host>/agent-feed for real-time updates.",
            "incidents_loaded": len(incidents),
            "resources_loaded": len(resources),
            "pipeline_steps": 6,
            "agents": [
                "SituationAgent",
                "TriageAgent",
                "ResourceAgent",
                "CoordinationAgent",
                "CommunicationAgent",
                "ReportingAgent",
            ],
        }
    )


@app.get(
    "/pipeline-result",
    summary="Get Last Pipeline Result",
    tags=["Pipeline"],
    response_class=JSONResponse,
)
async def get_pipeline_result():
    """
    Returns the full context output of the last completed pipeline run.
    Returns 404 if no pipeline has been run yet in this session.
    """
    if pipeline_result is None:
        raise HTTPException(
            status_code=404,
            detail="No pipeline result available. Trigger a scenario first via POST /trigger-scenario.",
        )
    return JSONResponse(
        content={
            "success": True,
            "pipeline_running": pipeline_running,
            "result": pipeline_result,
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

@app.websocket("/agent-feed")
async def websocket_agent_feed(websocket: WebSocket):
    """
    WebSocket endpoint for real-time agent pipeline updates.

    Clients receive JSON messages for each agent step:
    - event: "agent_update" | "pipeline_complete" | "pipeline_error"
    - step: current step number (1-6)
    - agent: agent name
    - status: "running" | "complete" | "error"
    - data: agent output
    - message: human-readable status message
    """
    await manager.connect(websocket)
    logger.info(
        "[WS] Client connected to /agent-feed. Total connections: %d",
        manager.connection_count,
    )

    # Send immediate welcome message
    await manager.send_personal_message(
        {
            "event": "connected",
            "message": "Connected to ResQnet Agent Feed. Waiting for pipeline trigger...",
            "active_connections": manager.connection_count,
            "pipeline_running": pipeline_running,
        },
        websocket,
    )

    try:
        # Keep connection alive — wait for client disconnect
        while True:
            try:
                # Await any message from client (ping/pong or commands)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                logger.debug("[WS] Received from client: %s", data)
                # Echo acknowledgement for any client ping
                await manager.send_personal_message(
                    {"event": "ack", "received": data}, websocket
                )
            except asyncio.TimeoutError:
                # Send keepalive ping
                await manager.send_personal_message(
                    {"event": "ping", "message": "keepalive"}, websocket
                )

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected from /agent-feed.")
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("[WS] Unexpected WebSocket error: %s", exc)
    finally:
        await manager.disconnect(websocket)
        logger.info(
            "[WS] Connection cleaned up. Remaining: %d", manager.connection_count
        )
