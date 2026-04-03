# ResQnet
Autonomous multi-agent AI system for real-time disaster response coordination across Maharashtra —

# ResQnet — Autonomous Disaster Response Coordination System

> Six AI agents. One pipeline. Zero delay.

ResQnet is an autonomous multi-agent system that acts as a 24/7 
AI-powered command centre for disaster response coordination. 
When simultaneous disasters strike, ResQnet triages incidents 
by life risk, maps available resources, issues dispatch orders, 
generates field communications, and produces a full incident 
report — all within 90 seconds, with no human input required.

Built for SunHacks 2K26 | Theme: Agentic AI

## The Problem
During multi-incident disasters, human coordinators face 
cognitive overload — simultaneously monitoring feeds, 
correlating events, and dispatching resources under extreme 
pressure. Delayed decisions cost lives.

## The Solution
A 6-agent sequential reasoning pipeline where each agent 
builds on the previous agent's output — creating a genuine 
chain of autonomous intelligence, not just parallel API calls.

## Agent Pipeline
| # | Agent | Role |
|---|---|---|
| 1 | Situation Agent | Assesses overall disaster picture across all incidents |
| 2 | Triage Agent | Ranks incidents by life risk and response urgency |
| 3 | Resource Agent | Maps available NDRF teams, hospitals, vehicles to needs |
| 4 | Coordination Agent | Issues final autonomous dispatch orders |
| 5 | Communication Agent | Generates public advisories and field team briefings |
| 6 | Reporting Agent | Produces complete incident report with timeline |

## Tech Stack
| Layer | Technology |
|---|---|
| AI/LLM | Google Gemini 1.5 Flash |
| Backend | Python FastAPI |
| Realtime | WebSockets |
| Frontend | React + Vite + Tailwind CSS |
| Map | Leaflet.js + OpenStreetMap |
| Data | Real Maharashtra geographic coordinates |

## Demo
Three simultaneous disasters — Nashik flash flood, 
Pune building collapse, Aurangabad highway blockage — 
triaged, coordinated, and reported autonomously in under 90 seconds.
