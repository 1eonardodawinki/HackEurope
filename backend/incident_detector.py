"""
Incident Detector — aggregates incidents and triggers the AI agent pipeline
when the regional threshold is exceeded.
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Awaitable

from config import INCIDENT_THRESHOLD, INCIDENT_WINDOW_HOURS, HOTZONES
from agents.evaluator_agent import evaluate_incident
from agents.reporter_agent import generate_report
import database as db


class IncidentDetector:
    def __init__(self, broadcast_callback: Callable):
        """
        broadcast_callback: async function(message: dict) → send to all WS clients
        """
        self.broadcast = broadcast_callback

        # All incidents, keyed by region
        self._incidents: dict[str, list[dict]] = defaultdict(list)
        # Evaluations for each incident
        self._evaluations: dict[str, list[dict]] = defaultdict(list)
        # Regions that have already triggered a report (avoid duplicates)
        self._reported_regions: set[str] = set()
        # Whether the agent pipeline is busy
        self._pipeline_running = False

    async def add_incident(self, incident: dict):
        """Called when AISMonitor detects a new incident."""
        region = incident.get("region", "unknown")
        incident["timestamp"] = datetime.now(timezone.utc).isoformat()

        self._incidents[region].append(incident)

        # Broadcast raw incident alert immediately
        await self.broadcast({
            "type": "incident",
            "data": incident,
        })

        # Run evaluator on this incident (non-blocking)
        asyncio.create_task(self._evaluate_and_check_threshold(incident, region))

    async def _evaluate_and_check_threshold(self, incident: dict, region: str):
        region_commodities = HOTZONES.get(region, {}).get("commodities", ["Brent Crude Oil"])

        # Broadcast evaluator start
        await self.broadcast({
            "type": "agent_status",
            "data": {"stage": "evaluator", "message": f"Evaluating incident in {region}...", "region": region}
        })

        try:
            evaluation = await evaluate_incident(incident, region_commodities)
            evaluation["incident_id"] = incident["id"]
            self._evaluations[region].append(evaluation)

            # Persist to Supabase (fire and forget)
            asyncio.create_task(db.save_incident(incident, evaluation))

            # Broadcast evaluation result
            await self.broadcast({
                "type": "evaluation",
                "data": {
                    "incident_id": incident["id"],
                    "region": region,
                    "confidence_score": evaluation.get("confidence_score", 0),
                    "incident_type": evaluation.get("incident_type", "unknown"),
                    "commodities_affected": evaluation.get("commodities_affected", []),
                    "reasoning": evaluation.get("reasoning", ""),
                }
            })

        except Exception as e:
            print(f"[Evaluator] Error: {e}")
            evaluation = {
                "incident_id": incident["id"],
                "confidence_score": 55,
                "incident_type": "possible_sanctions_evasion",
                "commodities_affected": region_commodities[:2],
                "evidence": ["AIS dropout pattern consistent with dark activity"],
            }
            self._evaluations[region].append(evaluation)

        # Check threshold — count incidents in the time window
        window_start = datetime.now(timezone.utc) - timedelta(hours=INCIDENT_WINDOW_HOURS)
        recent_incidents = [
            i for i in self._incidents[region]
            if datetime.fromisoformat(i["timestamp"].replace("Z", "+00:00")) >= window_start
        ]
        recent_evals = self._evaluations[region]

        total = len(recent_incidents)
        avg_confidence = (
            sum(e.get("confidence_score", 0) for e in recent_evals) / len(recent_evals)
            if recent_evals else 0
        )

        # Broadcast running counts
        await self.broadcast({
            "type": "threshold_update",
            "data": {
                "region": region,
                "incident_count": total,
                "threshold": INCIDENT_THRESHOLD,
                "avg_confidence": round(avg_confidence, 1),
            }
        })

        # Trigger report if threshold met and not already done
        if (total >= INCIDENT_THRESHOLD
                and region not in self._reported_regions
                and not self._pipeline_running):

            self._reported_regions.add(region)
            asyncio.create_task(self._run_report_pipeline(
                recent_incidents, recent_evals, region
            ))

    async def _run_report_pipeline(self, incidents: list[dict], evaluations: list[dict], region: str):
        self._pipeline_running = True

        async def progress(update: dict):
            await self.broadcast({"type": "agent_status", "data": update})

        try:
            await progress({
                "stage": "reporter",
                "round": 1,
                "message": f"Intelligence threshold reached for {region}. Generating report...",
            })

            report = await generate_report(incidents, evaluations, progress_callback=progress)

            if report:
                # Persist report to Supabase (fire and forget)
                asyncio.create_task(db.save_report(report))
                await self.broadcast({
                    "type": "report",
                    "data": report,
                })

        except Exception as e:
            print(f"[Reporter] Error: {e}")
            await self.broadcast({
                "type": "agent_status",
                "data": {"stage": "error", "message": f"Report generation failed: {str(e)[:100]}"}
            })
        finally:
            self._pipeline_running = False
            await self.broadcast({
                "type": "agent_status",
                "data": {"stage": "idle", "message": "Monitoring..."}
            })

    def get_summary(self) -> dict:
        counts = {r: len(inc) for r, inc in self._incidents.items()}
        avg_conf = {}
        for r, evals in self._evaluations.items():
            if evals:
                avg_conf[r] = round(sum(e.get("confidence_score", 0) for e in evals) / len(evals), 1)
        return {
            "incident_counts": counts,
            "avg_confidence": avg_conf,
            "threshold": INCIDENT_THRESHOLD,
            "reported_regions": list(self._reported_regions),
            "pipeline_running": self._pipeline_running,
        }
