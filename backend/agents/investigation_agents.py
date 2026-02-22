"""
Investigation Agents — three specialist Claude agents that run in parallel
for MMSI-based dark fleet investigations.

Flow:
  run_parallel_investigation(vessel_info, progress_callback)
    ├── run_news_agent()          → recent vessel / owner news
    ├── run_sanctions_agent()     → OFAC / EU / UN sanctions exposure
    └── run_geopolitical_agent()  → regional threat context
  Returns combined findings dict for the reporter.
"""

import asyncio
import json
import re
import traceback

import anthropic
from data_fetchers.news_fetcher import search_recent_news
from config import FAST_MODEL, ANTHROPIC_API_KEY

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# ── Shared tool definition ─────────────────────────────────────────────────────

NEWS_TOOL = {
    "name": "search_recent_news",
    "description": "Search for recent news articles about a vessel, company, region, or geopolitical topic.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query, e.g. 'MMSI 311000001 tanker sanctions Iran'"
            },
            "region": {
                "type": "string",
                "description": "Geographic region or empty string for global search"
            },
            "days_back": {
                "type": "integer",
                "description": "How many days of news to search (default 30)",
                "default": 30
            }
        },
        "required": ["query", "region"]
    }
}


async def _execute_news_tool(tool_input: dict) -> str:
    results = await search_recent_news(
        query=tool_input["query"],
        region=tool_input.get("region", ""),
        days_back=tool_input.get("days_back", 30),
    )
    return json.dumps(results, indent=2)


async def _run_agent(system_prompt: str, user_prompt: str, label: str) -> dict:
    """
    Run a single-round tool-use agent call.
    Returns a parsed dict of findings, or a fallback on error.
    """
    messages = [{"role": "user", "content": user_prompt}]

    try:
        for _ in range(4):   # max 4 iterations (user → tool call → result → final)
            response = await client.messages.create(
                model=FAST_MODEL,
                max_tokens=2048,
                system=system_prompt,
                tools=[NEWS_TOOL],
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = await _execute_news_tool(block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                messages.append({"role": "user", "content": tool_results})

        # Extract text from final response
        final_text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )

        # Try to parse JSON from response
        json_match = re.search(r'\{[\s\S]*\}', final_text)
        if json_match:
            return json.loads(json_match.group())

        # Fallback: wrap raw text
        return {"summary": final_text[:800], "parse_error": True}

    except Exception:
        print(f"[{label}] Agent call failed:")
        traceback.print_exc()
        return {"summary": f"{label} failed — using baseline assessment.", "error": True}


# ── Individual agents ──────────────────────────────────────────────────────────

async def run_news_agent(mmsi: str, vessel_name: str, region: str = "") -> dict:
    """Search recent news about the vessel, its operator, and any reported anomalies."""
    system = f"""You are a maritime news intelligence analyst investigating a specific vessel.

Search for recent news about vessel {vessel_name or 'Unknown'} (MMSI {mmsi}), including:
- Direct mentions of the vessel name or MMSI
- News about the vessel's operator, owner, or management company
- Reported AIS gaps, dark periods, or suspicious behaviour
- Port call irregularities or detentions
- Flag state issues

IMPORTANT: Return ONLY valid JSON matching this schema:
{{
  "summary": "string — 2-3 sentence overview of findings",
  "key_findings": ["string", ...],
  "sources": ["string", ...],
  "risk_indicators": ["string", ...]
}}"""

    user = (
        f"Investigate vessel: {vessel_name or 'Unknown'} | MMSI: {mmsi}"
        + (f" | Last known region: {region}" if region else "")
        + "\n\nSearch for news and return your structured findings as JSON."
    )

    result = await _run_agent(system, user, "NewsAgent")
    result["agent"] = "news"
    return result


async def run_sanctions_agent(mmsi: str, vessel_name: str, flag_state: str = "") -> dict:
    """Check sanctions exposure for the vessel, owner, and flag state."""
    system = f"""You are a sanctions compliance analyst at a maritime risk firm.

Investigate the sanctions exposure for vessel {vessel_name or 'Unknown'} (MMSI {mmsi}).

Search for:
- OFAC (US), EU, UN, or UK sanctions designations involving this vessel or MMSI
- Sanctions on the vessel's registered owner, beneficial owner, or operator
- Flag state sanctions risk (flag: {flag_state or 'unknown'})
- Previous sanctions evasion methods (AIS manipulation, ship-to-ship transfers, port deception)
- Any related entities on watchlists

IMPORTANT: Return ONLY valid JSON matching this schema:
{{
  "summary": "string — sanctions risk overview",
  "sanctions_hits": ["string", ...],
  "exposure_level": "CONFIRMED" | "SUSPECTED" | "POSSIBLE" | "NONE",
  "related_entities": ["string", ...],
  "recommended_actions": ["string", ...]
}}"""

    user = (
        f"Perform sanctions due diligence on: {vessel_name or 'Unknown'} | MMSI: {mmsi}"
        + (f" | Flag state: {flag_state}" if flag_state else "")
        + "\n\nSearch for sanctions exposure and return structured findings as JSON."
    )

    result = await _run_agent(system, user, "SanctionsAgent")
    result["agent"] = "sanctions"
    return result


async def run_geopolitical_agent(region: str, vessel_profile: str) -> dict:
    """Assess the geopolitical risk context for the vessel's operating region."""
    system = """You are a geopolitical risk analyst specialising in maritime security.

Assess the geopolitical threat context for a vessel under investigation.

Search for:
- Current geopolitical tensions in the vessel's operating region
- State-sponsored shadow fleet activity linked to this region
- Sanctions evasion corridors and known dark fleet hotspots
- Recent shipping disruptions, piracy incidents, or state actor interference
- Commodity flows being disrupted or manipulated in this region

IMPORTANT: Return ONLY valid JSON matching this schema:
{
  "summary": "string — geopolitical risk overview",
  "threat_level": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
  "key_risks": ["string", ...],
  "state_actors": ["string", ...],
  "regional_context": "string — detailed regional analysis"
}"""

    user = (
        f"Assess geopolitical risk for:\nVessel profile: {vessel_profile}\nOperating region: {region or 'unknown'}"
        "\n\nSearch for regional geopolitical risk and return structured findings as JSON."
    )

    result = await _run_agent(system, user, "GeopoliticalAgent")
    result["agent"] = "geopolitical"
    return result


# ── Orchestrator ───────────────────────────────────────────────────────────────

async def run_parallel_investigation(vessel_info: dict, progress_callback=None) -> dict:
    """
    Run all three specialist agents in parallel and return combined findings.

    vessel_info keys: mmsi, vessel_name, flag_state, region
    """
    mmsi = vessel_info.get("mmsi", "")
    vessel_name = vessel_info.get("vessel_name", "")
    flag_state = vessel_info.get("flag_state", "")
    region = vessel_info.get("region", "")

    vessel_profile = (
        f"Vessel: {vessel_name or 'Unknown'} | MMSI: {mmsi}"
        + (f" | Flag: {flag_state}" if flag_state else "")
        + (f" | Region: {region}" if region else "")
    )

    print(f"[Investigation] Starting parallel agents for MMSI {mmsi}")

    # Notify frontend all three agents are launching
    if progress_callback:
        for stage, msg in [
            ("news_agent", f"News agent searching for vessel intelligence..."),
            ("sanctions_agent", f"Sanctions agent checking exposure databases..."),
            ("geopolitical_agent", f"Geopolitical agent assessing regional risk..."),
        ]:
            await progress_callback({"stage": stage, "message": msg})

    # Run all three in parallel
    news_task = asyncio.create_task(run_news_agent(mmsi, vessel_name, region))
    sanctions_task = asyncio.create_task(run_sanctions_agent(mmsi, vessel_name, flag_state))
    geo_task = asyncio.create_task(run_geopolitical_agent(region, vessel_profile))

    news_result, sanctions_result, geo_result = await asyncio.gather(
        news_task, sanctions_task, geo_task, return_exceptions=True
    )

    # Normalise exceptions to error dicts
    def _safe(result, label):
        if isinstance(result, Exception):
            print(f"[Investigation] {label} raised: {result}")
            return {"summary": f"{label} failed.", "error": True, "agent": label.lower()}
        return result

    news_result = _safe(news_result, "NewsAgent")
    sanctions_result = _safe(sanctions_result, "SanctionsAgent")
    geo_result = _safe(geo_result, "GeopoliticalAgent")

    print(f"[Investigation] All parallel agents complete for MMSI {mmsi}")

    if progress_callback:
        await progress_callback({
            "stage": "investigation",
            "message": "Intelligence gathering complete — compiling findings for reporter...",
        })

    return {
        "news": news_result,
        "sanctions": sanctions_result,
        "geopolitical": geo_result,
    }
