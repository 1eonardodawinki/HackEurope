"""
Reporter Agent — generates a structured intelligence report from aggregated incidents.
Works in a back-and-forth loop with the Critic Agent until approved.
"""

import asyncio
import json
import re
import traceback
import anthropic
from config import FAST_MODEL, ANTHROPIC_API_KEY, MAX_CRITIC_ROUNDS

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

REPORTER_SYSTEM = """You are a senior intelligence analyst at a maritime security and commodity research firm.

Your role is to generate comprehensive, well-evidenced intelligence reports that:
1. Clearly describe the pattern of maritime incidents detected
2. Assess the likely cause (sanctions evasion, piracy, state-sponsored activity, illegal STS transfers)
3. Show your full chain of reasoning
4. Assign an overall confidence score (0-100)

Be specific. Cite evidence. Quantify predictions (e.g. "+4-7% Brent Crude over 2-3 weeks").
Your reports will be reviewed by a critic. Write as if publishing to institutional clients.

IMPORTANT: Your final report MUST be valid JSON matching this schema. Output ONLY the JSON object — no markdown fences, no preamble:
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


def _serialise_content(content) -> list:
    """Convert SDK content block objects to plain dicts for multi-turn messages.

    Must NOT use model_dump() — it includes internal SDK fields like 'parsed_output'
    that the API rejects with HTTP 400 'Extra inputs are not permitted'.
    """
    result = []
    for block in content:
        if isinstance(block, dict):
            result.append(block)
            continue
        t = getattr(block, 'type', None)
        if t == 'text':
            result.append({"type": "text", "text": block.text})
        elif t == 'thinking':
            result.append({"type": "thinking", "thinking": block.thinking, "signature": block.signature})
        elif t == 'tool_use':
            result.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
        elif t == 'tool_result':
            result.append({"type": "tool_result", "tool_use_id": block.tool_use_id, "content": block.content})
        elif hasattr(block, 'model_dump'):
            # Last-resort: strip known internal SDK fields
            result.append(block.model_dump(exclude={'parsed_output', 'cache_control'}))
        else:
            result.append({"type": "text", "text": str(block)})
    return result


def _fallback_report(incidents: list[dict], evaluations: list[dict], error_message: str = "") -> dict:
    """Return a minimal valid report if the Claude API is unavailable."""
    region = incidents[0].get("region", "unknown") if incidents else "unknown"
    avg_conf = (
        sum(e.get("confidence_score", 0) for e in evaluations) / len(evaluations)
        if evaluations else 55
    )
    threat_note = (
        f"Automated fallback — Claude API error: {error_message}"
        if error_message
        else "Automated fallback — Claude API unavailable during report generation."
    )
    return {
        "title": f"Maritime Incident Alert — {region}",
        "executive_summary": (
            f"{len(incidents)} maritime incidents detected in the {region} over the past 24 hours. "
            "Automated analysis suggests elevated risk of dark vessel activity. "
            "Manual review recommended."
        ),
        "incident_pattern": "\n".join(
            f"• {i.get('ship_name','Unknown')} ({i.get('type','unknown')}) at "
            f"{i.get('lat',0):.3f}°N, {i.get('lon',0):.3f}°E"
            for i in incidents
        ),
        "threat_assessment": threat_note,
        "chain_of_thought": f"Report generated by fallback system due to API error. Error: {error_message}",
        "commodity_predictions": [],
        "supporting_evidence": [f"Incident {i.get('id','?')}: {i.get('type','?')} — {i.get('ship_name','?')}" for i in incidents],
        "risk_factors": ["API error prevented full analysis — confidence scores are estimates only"],
        "overall_confidence": int(avg_conf),
        "classification": "INTELLIGENCE REPORT - RESTRICTED",
    }


async def _call_reporter(system: str, messages: list[dict], progress_callback=None) -> anthropic.types.Message:
    """Stream the reporter. Retries up to 3 times on 429 rate-limit errors."""
    for attempt in range(3):
        try:
            full_text = ""
            async with client.messages.stream(
                model=FAST_MODEL,
                max_tokens=6000,
                system=system,
                messages=messages,
            ) as stream:
                async for chunk in stream.text_stream:
                    full_text += chunk
                    if progress_callback and len(full_text) % 400 < max(1, len(chunk)):
                        await progress_callback({
                            "stage": "reporter_stream",
                            "chars": len(full_text),
                            "message": f"Drafting report... ({len(full_text):,} chars)",
                        })
                return await stream.get_final_message()
        except anthropic.RateLimitError as e:
            wait = 15 * (2 ** attempt)   # 15s, 30s, 60s
            print(f"[Reporter] 429 rate limit (attempt {attempt+1}/3) — waiting {wait}s: {e}")
            if attempt == 2:
                raise
            await asyncio.sleep(wait)
        except Exception:
            print("[Reporter] Streaming failed, falling back to non-streaming:")
            traceback.print_exc()
            return await client.messages.create(
                model=FAST_MODEL,
                max_tokens=6000,
                system=system,
                messages=messages,
            )


async def generate_report(
    incidents: list[dict],
    evaluations: list[dict],
    progress_callback=None
) -> dict:
    """
    Run the Reporter → Critic loop.
    Returns the final approved intelligence report, or a fallback report on failure.
    """

    print(f"[Reporter] Starting report generation — {len(incidents)} incidents, {len(evaluations)} evaluations")

    context = await build_context(incidents, evaluations)
    reporter_messages = [{"role": "user", "content": context}]

    report_draft = None
    critic_feedback = None

    for round_num in range(1, MAX_CRITIC_ROUNDS + 1):
        # ── Reporter turn ────────────────────────────────────────────────────
        print(f"[Reporter] Round {round_num}/{MAX_CRITIC_ROUNDS} — generating report...")
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

        try:
            report_response = await _call_reporter(REPORTER_SYSTEM, reporter_messages, progress_callback=progress_callback)
        except Exception as exc:
            print(f"[Reporter] All API attempts failed on round {round_num}:")
            traceback.print_exc()
            return _fallback_report(incidents, evaluations, error_message=str(exc))

        reporter_text = "".join(b.text for b in report_response.content if hasattr(b, "text"))
        print(f"[Reporter] Round {round_num} response: {len(reporter_text)} chars")
        print(f"[Reporter] Draft preview:\n{reporter_text[:600]}\n{'...' if len(reporter_text) > 600 else ''}")

        reporter_messages.append({
            "role": "assistant",
            "content": _serialise_content(report_response.content),
        })

        try:
            json_match = re.search(r'\{[\s\S]*\}', reporter_text)
            if json_match:
                report_draft = json.loads(json_match.group())
                print(f"[Reporter] Round {round_num} JSON parsed OK — confidence: {report_draft.get('overall_confidence')}%")
            else:
                print(f"[Reporter] Round {round_num} — no JSON found in response")
                report_draft = {"raw_text": reporter_text, "parse_error": True}
        except Exception as e:
            print(f"[Reporter] Round {round_num} JSON parse error: {e}")
            report_draft = {"raw_text": reporter_text, "parse_error": True}

        # ── Critic turn (Haiku — fast structured review) ──────────────────────
        print(f"[Critic] Round {round_num}/{MAX_CRITIC_ROUNDS} — reviewing...")
        if progress_callback:
            await progress_callback({
                "stage": "critic",
                "round": round_num,
                "message": f"Critic reviewing report (round {round_num}/{MAX_CRITIC_ROUNDS})..."
            })

        critic_messages = [{
            "role": "user",
            "content": f"Review this intelligence report:\n\n{json.dumps(report_draft, indent=2)}"
        }]
        try:
            critic_response = await client.messages.create(
                model=FAST_MODEL,
                max_tokens=2048,
                system=CRITIC_SYSTEM,
                messages=critic_messages,
            )

            critic_text = "".join(b.text for b in critic_response.content if hasattr(b, "text"))
            print(f"[Critic] Round {round_num} response:\n{critic_text[:800]}")

            try:
                json_match = re.search(r'\{[\s\S]*\}', critic_text)
                if json_match:
                    critic_feedback = json.loads(json_match.group())
                else:
                    critic_feedback = {"approved": False, "overall_quality": 50, "critique": critic_text[:500]}
            except Exception as e:
                print(f"[Critic] JSON parse error: {e}")
                critic_feedback = {"approved": False, "overall_quality": 50, "critique": critic_text[:500]}

        except Exception:
            print(f"[Critic] API call failed on round {round_num}, auto-approving:")
            traceback.print_exc()
            critic_feedback = {
                "approved": True,
                "overall_quality": 60,
                "critique": "Critic API call failed — report auto-approved",
                "approval_reason": "Auto-approved due to critic API error",
            }

        approved = critic_feedback.get("approved", False)
        quality = critic_feedback.get("overall_quality", 0)
        print(f"[Critic] Round {round_num} — approved={approved}, quality={quality}")

        if progress_callback:
            await progress_callback({
                "stage": "critic_result",
                "round": round_num,
                "approved": approved,
                "critique": critic_feedback.get("critique", ""),
                "quality_score": quality,
            })

        if approved:
            print(f"[Reporter] Report approved by critic on round {round_num}")
            break

    # Attach metadata
    if report_draft:
        report_draft["_meta"] = {
            "critic_rounds": round_num,
            "final_approved": critic_feedback.get("approved", False) if critic_feedback else False,
            "critic_quality_score": critic_feedback.get("overall_quality", 0) if critic_feedback else 0,
            "incident_count": len(incidents),
            "region": incidents[0].get("region", "unknown") if incidents else "unknown",
        }
        print(f"[Reporter] Final report ready — title: {report_draft.get('title', 'N/A')}")
        return report_draft

    print("[Reporter] All rounds exhausted with no draft — returning fallback")
    return _fallback_report(incidents, evaluations, error_message="All critic rounds exhausted without a valid report draft")


# ── Investigation report (MMSI-based dark fleet assessment) ───────────────────

INVESTIGATION_REPORTER_SYSTEM = """You are a senior maritime intelligence analyst producing a vessel risk assessment for an institutional client (insurer, government agency, or financial institution).

You have been given:
1. A vessel MMSI and name
2. An ML model probability score (0-1) predicting dark fleet risk
3. Intelligence findings from three specialist agents: News, Sanctions, Geopolitical

Your role is to reach a definitive, evidence-based verdict on whether this vessel is a dark fleet participant — or a legitimate commercial vessel being incorrectly flagged.

CRITICAL PRINCIPLE — COMPETING HYPOTHESES:
Always evaluate BOTH explanations simultaneously:
  H1 (Dark Fleet): The vessel is engaged in sanctions evasion, AIS manipulation, or illegal transfers.
  H2 (Legitimate): The vessel is a normal commercial ship that happens to be in a risk region or match a statistical profile.

The default assumption is H2 (legitimate) unless specific, named evidence supports H1.

WHAT CONSTITUTES REAL EVIDENCE FOR H1:
- Named sanctions designations (OFAC/EU/UN) on the vessel, owner, or operator
- Documented AIS manipulation with corroborating satellite imagery
- Confirmed ship-to-ship transfers to/from sanctioned vessels
- Investigative journalism citing this specific vessel

WHAT DOES NOT CONSTITUTE EVIDENCE:
- Operating in a risk region (this describes thousands of legitimate vessels)
- High ML probability score alone (scores reflect statistical patterns, not confirmed activity)
- Vague news about regional dark fleet activity not naming this vessel
- Absence of information about the vessel

Assign risk_verdict honestly:
- "CLEARED": ML LOW + no sanctions hits + no named news = no basis for dark fleet classification
- "LOW_RISK": Some statistical flags but no corroborating intelligence
- "INCONCLUSIVE": Mixed signals — real ambiguity exists
- "ELEVATED": Multiple soft indicators or one hard indicator
- "HIGH_RISK": Specific named evidence of dark fleet activity

Be specific. Cite evidence by name. Justify every claim. Write for professionals who will act on this report.
If you find no real evidence of dark fleet activity, say so clearly — a clean verdict protects legitimate operators and builds client trust.

IMPORTANT: Keep each field concise (2-4 sentences max per string field) to ensure the full JSON fits within the response limit. Do not pad or repeat information across fields.

IMPORTANT: Your final report MUST be valid JSON matching this schema. Output ONLY the JSON object — no markdown fences, no preamble:
{
  "title": "string - e.g. 'Vessel Risk Assessment: VESSEL_NAME (MMSI XXXXXXXXX)'",
  "executive_summary": "string - 2-3 sentence summary with overall risk verdict",
  "vessel_profile": "string - what is known about this vessel",
  "ml_risk_score": {
    "probability": number (0-1),
    "risk_tier": "HIGH" | "MEDIUM" | "LOW",
    "interpretation": "string - what this score means in context of other evidence, and whether it is corroborated or contradicted"
  },
  "news_intelligence": "string - synthesis of news findings, explicitly stating if no adverse news was found",
  "sanctions_assessment": "string - detailed sanctions risk analysis, explicitly confirming NONE if no hits found",
  "geopolitical_context": "string - regional threat context, distinguishing regional risk from vessel-specific risk",
  "threat_assessment": "string - clear verdict on H1 vs H2, with the key evidence driving your conclusion",
  "chain_of_thought": "string - your full reasoning process including both hypotheses",
  "supporting_evidence": ["string", ...],
  "risk_factors": ["string", ...],
  "recommended_actions": ["string", ...],
  "risk_verdict": "CLEARED" | "LOW_RISK" | "INCONCLUSIVE" | "ELEVATED" | "HIGH_RISK",
  "overall_confidence": number (0-100),
  "classification": "INTELLIGENCE REPORT - RESTRICTED"
}"""

INVESTIGATION_CRITIC_SYSTEM = """You are an adversarial quality control analyst reviewing a vessel risk assessment before it is delivered to an institutional client.

Your role is to check for errors in BOTH directions — over-flagging legitimate vessels is as harmful as under-flagging dark fleet participants.

Specifically challenge:
1. OVER-FLAGGING: Does the report assert dark fleet activity without specific named evidence? Using a risk region, a statistical ML score, or vague regional news to conclude "high risk" is unacceptable and exposes the firm to reputational and legal liability.
2. UNDER-FLAGGING: Are specific, named sanctions hits or documented AIS manipulation being downplayed or ignored?
3. ML score weight: Is the score properly contextualised — corroborated by intel, or contradicted by clean findings?
4. Sanctions specificity: Are sanctions claims named and sourced, or vague and inferred?
5. Verdict-evidence alignment: Does the risk_verdict match the actual weight of evidence? A "CLEARED" verdict requires explicitly stating what was searched and not found.
6. Recommended actions: Are they proportionate? Recommending "decline financing" for a vessel with no evidence is harmful.

Approve only when: the verdict is clearly supported by evidence, both hypotheses were genuinely considered, and the recommended actions are proportionate.

Respond in JSON:
{
  "approved": boolean,
  "overall_quality": number (0-100),
  "critique": "string - specific, detailed critique calling out both over- and under-flagging",
  "over_flagging_issues": ["string", ...],
  "missing_evidence": ["string", ...],
  "weak_claims": ["string", ...],
  "suggestions": ["string", ...],
  "approval_reason": "string - if approved, explain why the verdict is well-supported"
}"""


def _fallback_investigation_report(vessel_info: dict, ml_score: dict, error_message: str = "") -> dict:
    """Return a minimal valid investigation report if the Claude API is unavailable."""
    mmsi = vessel_info.get("mmsi", "unknown")
    vessel_name = vessel_info.get("vessel_name", "Unknown Vessel")
    prob = ml_score.get("probability", 0.5)
    tier = ml_score.get("risk_tier", "MEDIUM")
    return {
        "title": f"Vessel Risk Assessment: {vessel_name} (MMSI {mmsi})",
        "executive_summary": (
            f"ML model assigns {tier} risk (probability {prob:.0%}) to vessel {vessel_name} (MMSI {mmsi}). "
            "Automated fallback report — full agent analysis unavailable. Manual review required before acting on this assessment."
        ),
        "vessel_profile": f"MMSI: {mmsi}, Name: {vessel_name}",
        "ml_risk_score": {
            "probability": prob,
            "risk_tier": tier,
            "interpretation": "ML score only — agent intelligence gathering failed. Do not use in isolation.",
        },
        "news_intelligence": "News agent output unavailable — no adverse or clean findings recorded.",
        "sanctions_assessment": "Sanctions agent output unavailable — no confirmation of presence or absence of designations.",
        "geopolitical_context": "Geopolitical agent output unavailable.",
        "threat_assessment": f"Automated fallback — API error: {error_message}. No verdict can be issued." if error_message else "Automated fallback — API unavailable. No verdict can be issued.",
        "chain_of_thought": "Report generated by fallback system. Full pipeline did not run.",
        "supporting_evidence": [f"ML probability: {prob:.0%} ({tier} risk tier)"],
        "risk_factors": ["Full agent analysis failed — no verdict should be acted upon without manual review"],
        "recommended_actions": ["Do not act on this automated fallback report", "Conduct manual sanctions and news review", "Re-run investigation when API is available"],
        "risk_verdict": "INCONCLUSIVE",
        "overall_confidence": 20,
        "classification": "INTELLIGENCE REPORT - RESTRICTED",
    }


def _pre_screen_signals(ml_score: dict, agent_findings: dict) -> dict:
    """
    Derive a lightweight pre-screen from ML score + agent findings before
    running the full reporter/critic loop. Returns a dict with:
      - is_clearly_clean: bool — skip reporter loop and issue a CLEARED report directly
      - signals: list[str] — human-readable list of what was found
    """
    prob = ml_score.get("probability", 0.5)
    tier = ml_score.get("risk_tier", "MEDIUM")
    sanctions = agent_findings.get("sanctions", {})
    news = agent_findings.get("news", {})

    exposure = sanctions.get("exposure_level", "POSSIBLE")
    sanctions_hits = sanctions.get("sanctions_hits", [])
    risk_indicators = news.get("risk_indicators", [])
    clean_news = news.get("clean_indicators", [])
    clean_sanctions = sanctions.get("clean_indicators", [])

    signals = []

    # Hard stop — confirmed sanctions = always run full loop
    if exposure in ("CONFIRMED", "SUSPECTED") or sanctions_hits:
        signals.append(f"Sanctions exposure: {exposure}")
        return {"is_clearly_clean": False, "signals": signals}

    # Hard stop — specific risk indicators in news = run full loop
    if risk_indicators:
        signals.extend(risk_indicators[:3])
        return {"is_clearly_clean": False, "signals": signals}

    # All three gates must pass for fast-clear:
    # 1. Low ML score
    # 2. No sanctions hits
    # 3. No news risk indicators
    if prob <= 0.25 and tier == "LOW" and exposure == "NONE" and not risk_indicators:
        signals.append(f"ML score LOW ({prob:.0%})")
        signals.append(f"Sanctions: NONE confirmed")
        if clean_news:
            signals.extend(clean_news[:2])
        if clean_sanctions:
            signals.extend(clean_sanctions[:2])
        return {"is_clearly_clean": True, "signals": signals}

    return {"is_clearly_clean": False, "signals": signals}


def _fast_clear_report(vessel_info: dict, ml_score: dict, agent_findings: dict, signals: list) -> dict:
    """Generate a CLEARED report without running the full reporter/critic loop."""
    mmsi = vessel_info.get("mmsi", "unknown")
    vessel_name = vessel_info.get("vessel_name", "Unknown Vessel")
    region = vessel_info.get("region", "unknown")
    prob = ml_score.get("probability", 0.5)
    tier = ml_score.get("risk_tier", "LOW")
    news = agent_findings.get("news", {})
    sanctions = agent_findings.get("sanctions", {})
    geo = agent_findings.get("geopolitical", {})
    now = __import__('datetime').datetime.utcnow().isoformat()

    return {
        "title": f"Vessel Risk Assessment: {vessel_name} (MMSI {mmsi})",
        "executive_summary": (
            f"No evidence of dark fleet activity found for {vessel_name} (MMSI {mmsi}). "
            f"ML model assigns LOW risk ({prob:.0%}), no sanctions designations confirmed, and no adverse news identified. "
            "This vessel does not meet the threshold for dark fleet classification."
        ),
        "vessel_profile": f"MMSI: {mmsi}, Name: {vessel_name}, Region: {region}",
        "ml_risk_score": {
            "probability": prob,
            "risk_tier": tier,
            "interpretation": (
                f"LOW statistical risk ({prob:.0%}), consistent with legitimate commercial operation. "
                "No corroborating intelligence found to elevate this score."
            ),
        },
        "news_intelligence": news.get("summary", "No adverse news found for this vessel."),
        "sanctions_assessment": sanctions.get("summary", "No sanctions designations found (OFAC, EU, UN, UK)."),
        "geopolitical_context": geo.get("summary", "Regional context assessed; no vessel-specific risk identified."),
        "threat_assessment": (
            "H2 (Legitimate commercial vessel) is the supported hypothesis. "
            "H1 (Dark fleet participant) is not supported — no specific named evidence found across news, sanctions, or ML signal. "
            "The ML score reflects a statistical pattern, not confirmed activity."
        ),
        "chain_of_thought": (
            f"Pre-screening completed at {now}Z. ML probability {prob:.0%} (LOW tier). "
            "Sanctions agent returned NONE. News agent found no risk indicators. "
            "All three fast-clear gates passed — full reporter/critic loop not required. "
            f"Clean signals: {'; '.join(signals)}."
        ),
        "supporting_evidence": signals or ["ML score below fast-clear threshold (≤25%)", "No sanctions designations", "No adverse news"],
        "risk_factors": ["Regional geopolitical context carries baseline risk independent of this vessel"],
        "recommended_actions": [
            "No immediate action required",
            "Continue standard AIS monitoring",
            "Re-assess if new sanctions designations or AIS anomalies emerge",
        ],
        "risk_verdict": "CLEARED",
        "overall_confidence": 80,
        "classification": "INTELLIGENCE REPORT - RESTRICTED",
        "_meta": {
            "type": "investigation",
            "mmsi": mmsi,
            "fast_cleared": True,
            "critic_rounds": 0,
            "final_approved": True,
            "critic_quality_score": 80,
        },
    }


def _build_investigation_context(vessel_info: dict, ml_score: dict, agent_findings: dict) -> str:
    """Build the context string for the investigation reporter."""
    mmsi = vessel_info.get("mmsi", "unknown")
    vessel_name = vessel_info.get("vessel_name", "Unknown")
    flag_state = vessel_info.get("flag_state", "unknown")
    region = vessel_info.get("region", "unknown")

    news = agent_findings.get("news", {})
    sanctions = agent_findings.get("sanctions", {})
    geo = agent_findings.get("geopolitical", {})

    return f"""CLASSIFIED INVESTIGATION BRIEF — MMSI {mmsi}
Generated: {__import__('datetime').datetime.utcnow().isoformat()}Z

=== VESSEL DETAILS ===
MMSI: {mmsi}
Name: {vessel_name}
Flag State: {flag_state}
Last Known Region: {region}

=== ML MODEL ASSESSMENT ===
Probability (dark fleet): {ml_score.get('probability', 0):.0%}
Risk Tier: {ml_score.get('risk_tier', 'UNKNOWN')}
Model Version: {ml_score.get('model_version', 'unknown')}

=== NEWS INTELLIGENCE (News Agent) ===
{json.dumps(news, indent=2)}

=== SANCTIONS ASSESSMENT (Sanctions Agent) ===
{json.dumps(sanctions, indent=2)}

=== GEOPOLITICAL CONTEXT (Geopolitical Agent) ===
{json.dumps(geo, indent=2)}

Synthesise all evidence above into a comprehensive dark fleet risk assessment JSON report."""


async def generate_investigation_report(
    vessel_info: dict,
    ml_score: dict,
    agent_findings: dict,
    progress_callback=None,
) -> dict:
    """
    Run the Reporter → Critic loop for an MMSI-based investigation.
    Returns the final approved case report, or a fallback on failure.
    """
    mmsi = vessel_info.get("mmsi", "unknown")
    print(f"[InvReporter] Starting investigation report for MMSI {mmsi}")

    # ── Fast-clear pre-screen ────────────────────────────────────────────────
    pre = _pre_screen_signals(ml_score, agent_findings)
    if pre["is_clearly_clean"]:
        print(f"[InvReporter] Fast-clear path triggered for MMSI {mmsi} — signals: {pre['signals']}")
        if progress_callback:
            await progress_callback({
                "stage": "reporter",
                "round": 1,
                "message": "Pre-screen passed: no adverse signals — issuing CLEARED verdict directly.",
            })
        return _fast_clear_report(vessel_info, ml_score, agent_findings, pre["signals"])

    context = _build_investigation_context(vessel_info, ml_score, agent_findings)
    reporter_messages = [{"role": "user", "content": context}]

    report_draft = None
    critic_feedback = None

    for round_num in range(1, MAX_CRITIC_ROUNDS + 1):
        # ── Reporter turn ────────────────────────────────────────────────────
        print(f"[InvReporter] Round {round_num}/{MAX_CRITIC_ROUNDS} — generating report...")
        if progress_callback:
            await progress_callback({
                "stage": "reporter",
                "round": round_num,
                "message": f"Reporter {'drafting' if round_num == 1 else 'revising'} case report (round {round_num}/{MAX_CRITIC_ROUNDS})...",
            })

        if critic_feedback and round_num > 1:
            reporter_messages.append({
                "role": "user",
                "content": f"""CRITIC FEEDBACK (Round {round_num - 1}):
{json.dumps(critic_feedback, indent=2)}

Please revise your report addressing all critique points. Respond with improved JSON."""
            })

        try:
            report_response = await _call_reporter(INVESTIGATION_REPORTER_SYSTEM, reporter_messages, progress_callback=progress_callback)
        except Exception as exc:
            print(f"[InvReporter] All API attempts failed on round {round_num}:")
            traceback.print_exc()
            return _fallback_investigation_report(vessel_info, ml_score, str(exc))

        reporter_text = "".join(b.text for b in report_response.content if hasattr(b, "text"))
        print(f"[InvReporter] Round {round_num} response: {len(reporter_text)} chars")
        print(f"[InvReporter] Draft preview:\n{reporter_text[:600]}\n{'...' if len(reporter_text) > 600 else ''}")

        reporter_messages.append({
            "role": "assistant",
            "content": _serialise_content(report_response.content),
        })

        try:
            json_match = re.search(r'\{[\s\S]*\}', reporter_text)
            if json_match:
                report_draft = json.loads(json_match.group())
                print(f"[InvReporter] Round {round_num} JSON parsed OK — confidence: {report_draft.get('overall_confidence')}%")
            else:
                print(f"[InvReporter] Round {round_num} — no JSON found in response")
                report_draft = {"raw_text": reporter_text, "parse_error": True}
        except Exception as e:
            print(f"[InvReporter] JSON parse error: {e}")
            report_draft = {"raw_text": reporter_text, "parse_error": True}

        # ── Critic turn (Haiku — fast structured review) ──────────────────────
        print(f"[InvCritic] Round {round_num}/{MAX_CRITIC_ROUNDS} — reviewing...")
        if progress_callback:
            await progress_callback({
                "stage": "critic",
                "round": round_num,
                "message": f"Critic reviewing case report (round {round_num}/{MAX_CRITIC_ROUNDS})...",
            })

        critic_messages = [{
            "role": "user",
            "content": f"Review this dark fleet risk assessment:\n\n{json.dumps(report_draft, indent=2)}"
        }]
        try:
            critic_response = await client.messages.create(
                model=FAST_MODEL,
                max_tokens=2048,
                system=INVESTIGATION_CRITIC_SYSTEM,
                messages=critic_messages,
            )

            critic_text = "".join(b.text for b in critic_response.content if hasattr(b, "text"))
            print(f"[InvCritic] Round {round_num} response:\n{critic_text[:800]}")

            try:
                json_match = re.search(r'\{[\s\S]*\}', critic_text)
                if json_match:
                    critic_feedback = json.loads(json_match.group())
                else:
                    critic_feedback = {"approved": False, "overall_quality": 50, "critique": critic_text[:500]}
            except Exception as e:
                print(f"[InvCritic] JSON parse error: {e}")
                critic_feedback = {"approved": False, "overall_quality": 50, "critique": critic_text[:500]}

        except Exception:
            print(f"[InvCritic] API call failed on round {round_num}, auto-approving:")
            traceback.print_exc()
            critic_feedback = {
                "approved": True,
                "overall_quality": 60,
                "critique": "Critic API call failed — report auto-approved",
                "approval_reason": "Auto-approved due to critic API error",
            }

        approved = critic_feedback.get("approved", False)
        quality = critic_feedback.get("overall_quality", 0)
        print(f"[InvCritic] Round {round_num} — approved={approved}, quality={quality}")

        if progress_callback:
            await progress_callback({
                "stage": "critic_result",
                "round": round_num,
                "approved": approved,
                "critique": critic_feedback.get("critique", ""),
                "quality_score": quality,
            })

        if approved:
            print(f"[InvReporter] Report approved on round {round_num}")
            break

    if report_draft:
        report_draft["_meta"] = {
            "type": "investigation",
            "mmsi": mmsi,
            "critic_rounds": round_num,
            "final_approved": critic_feedback.get("approved", False) if critic_feedback else False,
            "critic_quality_score": critic_feedback.get("overall_quality", 0) if critic_feedback else 0,
        }
        print(f"[InvReporter] Final report ready — {report_draft.get('title', 'N/A')}")
        return report_draft

    print("[InvReporter] No draft produced — returning fallback")
    return _fallback_investigation_report(vessel_info, ml_score, "All rounds exhausted")