"""
Reporter Agent — generates a structured intelligence report from aggregated incidents.
Works in a back-and-forth loop with the Critic Agent until approved.
"""

import json
import anthropic
from config import MODEL, ANTHROPIC_API_KEY, MAX_CRITIC_ROUNDS

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

REPORTER_SYSTEM = """You are a senior intelligence analyst at a maritime security and commodity research firm.

Your role is to generate comprehensive, well-evidenced intelligence reports that:
1. Clearly describe the pattern of maritime incidents detected
2. Assess the likely cause (sanctions evasion, piracy, state-sponsored activity, illegal STS transfers)
3. Project the impact on specific commodity prices with timeframes and confidence levels
4. Show your full chain of reasoning
5. Assign an overall confidence score (0-100)

Be specific. Cite evidence. Quantify predictions (e.g. "+4-7% Brent Crude over 2-3 weeks").
Your reports will be reviewed by a critic. Write as if publishing to institutional clients.

IMPORTANT: Your final report MUST be valid JSON matching this schema:
{
  "title": "string - concise report title",
  "executive_summary": "string - 2-3 sentence summary",
  "incident_pattern": "string - detailed description of what was detected",
  "threat_assessment": "string - what type of activity this likely is and why",
  "chain_of_thought": "string - your full reasoning process",
  "commodity_predictions": [
    {
      "commodity": "string",
      "current_price": number,
      "currency": "string",
      "predicted_change_pct_low": number,
      "predicted_change_pct_high": number,
      "confidence": number (0-100),
      "timeframe": "string e.g. '2-4 weeks'",
      "reasoning": "string"
    }
  ],
  "supporting_evidence": ["string", ...],
  "risk_factors": ["string", ...],
  "overall_confidence": number (0-100),
  "classification": "INTELLIGENCE REPORT - RESTRICTED"
}"""

CRITIC_SYSTEM = """You are an adversarial quality control analyst reviewing an intelligence report before it is published to institutional clients.

Your role is to:
1. Identify logical gaps, unsupported claims, or weak evidence
2. Challenge commodity price predictions — are they too confident? Too vague?
3. Point out missing context that would strengthen the report
4. Flag any factual inconsistencies

Be rigorous and adversarial, but constructive. Your goal is to ensure only high-quality, defensible intelligence reaches clients.

Respond in JSON:
{
  "approved": boolean,
  "overall_quality": number (0-100),
  "critique": "string - specific, detailed critique",
  "missing_evidence": ["string", ...],
  "weak_claims": ["string", ...],
  "suggestions": ["string", ...],
  "approval_reason": "string - if approved, explain why it meets standards"
}"""


async def build_context(incidents: list[dict], evaluations: list[dict]) -> str:
    """Build the context string for the reporter."""
    region = incidents[0].get("region", "unknown") if incidents else "unknown"

    incidents_text = "\n".join([
        f"- [{i.get('type', 'unknown').upper()}] {i.get('ship_name', 'Unknown')} (MMSI {i.get('mmsi', 'N/A')}) "
        f"at {i.get('lat', 0):.3f}°N, {i.get('lon', 0):.3f}°E | "
        f"Duration: {i.get('duration_minutes', 0):.0f} min | "
        f"Timestamp: {i.get('timestamp', 'unknown')}"
        for i in incidents
    ])

    evals_text = "\n".join([
        f"- Incident #{j+1}: Confidence {e.get('confidence_score', 0)}% — {e.get('incident_type', 'unknown')} — "
        f"Commodities: {', '.join(e.get('commodities_affected', []))} — "
        f"Evidence: {'; '.join(e.get('evidence', []))}"
        for j, e in enumerate(evaluations)
    ])

    return f"""CLASSIFIED INTELLIGENCE BRIEF — {region.upper()}
Generated: {__import__('datetime').datetime.utcnow().isoformat()}Z

=== DETECTED INCIDENTS ({len(incidents)} events, past 24h) ===
{incidents_text}

=== EVALUATOR ASSESSMENTS ===
{evals_text}

=== REGION CONTEXT ===
Region: {region}
Strategic significance: Major maritime chokepoint / commodity export route
Affected commodities: {', '.join(set(
    c for e in evaluations for c in e.get('commodities_affected', [])
))}

Generate your intelligence report now as valid JSON."""


async def generate_report(
    incidents: list[dict],
    evaluations: list[dict],
    progress_callback=None
) -> dict:
    """
    Run the Reporter → Critic loop.
    Returns the final approved intelligence report.
    """

    context = await build_context(incidents, evaluations)
    reporter_messages = [{"role": "user", "content": context}]

    report_draft = None
    critic_feedback = None

    for round_num in range(1, MAX_CRITIC_ROUNDS + 1):
        # ── Reporter turn ────────────────────────────────────────────────────
        if progress_callback:
            await progress_callback({
                "stage": "reporter",
                "round": round_num,
                "message": f"Reporter generating {'initial report' if round_num == 1 else 'revised report'} (round {round_num}/{MAX_CRITIC_ROUNDS})..."
            })

        if critic_feedback and round_num > 1:
            reporter_messages.append({
                "role": "user",
                "content": f"""CRITIC FEEDBACK (Round {round_num - 1}):
{json.dumps(critic_feedback, indent=2)}

Please revise your report addressing all critique points. Respond with improved JSON."""
            })

        async with client.messages.stream(
            model=MODEL,
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=REPORTER_SYSTEM,
            messages=reporter_messages,
        ) as stream:
            report_response = await stream.get_final_message()

        reporter_text = ""
        for block in report_response.content:
            if hasattr(block, "text"):
                reporter_text += block.text

        reporter_messages.append({"role": "assistant", "content": report_response.content})

        # Parse reporter's JSON
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', reporter_text)
            if json_match:
                report_draft = json.loads(json_match.group())
        except Exception:
            report_draft = {"raw_text": reporter_text, "parse_error": True}

        # ── Critic turn ──────────────────────────────────────────────────────
        if progress_callback:
            await progress_callback({
                "stage": "critic",
                "round": round_num,
                "message": f"Critic reviewing report (round {round_num}/{MAX_CRITIC_ROUNDS})..."
            })

        critic_response = await client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=CRITIC_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"Review this intelligence report:\n\n{json.dumps(report_draft, indent=2)}"
            }]
        )

        critic_text = ""
        for block in critic_response.content:
            if hasattr(block, "text"):
                critic_text += block.text

        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', critic_text)
            if json_match:
                critic_feedback = json.loads(json_match.group())
            else:
                critic_feedback = {"approved": False, "critique": critic_text[:500]}
        except Exception:
            critic_feedback = {"approved": False, "critique": critic_text[:500]}

        if progress_callback:
            await progress_callback({
                "stage": "critic_result",
                "round": round_num,
                "approved": critic_feedback.get("approved", False),
                "critique": critic_feedback.get("critique", ""),
                "quality_score": critic_feedback.get("overall_quality", 0),
            })

        if critic_feedback.get("approved", False):
            break

    # Attach metadata
    if report_draft:
        report_draft["_meta"] = {
            "critic_rounds": round_num,
            "final_approved": critic_feedback.get("approved", False),
            "critic_quality_score": critic_feedback.get("overall_quality", 0),
            "incident_count": len(incidents),
            "region": incidents[0].get("region", "unknown") if incidents else "unknown",
        }

    return report_draft or {}
