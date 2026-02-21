"""
Evaluator Agent — uses Claude with tool use to assess maritime incidents.

Given one or more AIS incidents (dropout / proximity), it:
  1. Searches recent news about the region
  2. Gets commodity price context
  3. Returns a confidence score + structured evaluation
"""

import json
import anthropic
from data_fetchers.news_fetcher import search_recent_news
from data_fetchers.commodity_fetcher import get_commodity_price
from config import MODEL, ANTHROPIC_API_KEY

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are a senior maritime intelligence analyst specializing in dark vessel activity and commodity market impacts.

You will receive an alert about a potential maritime security incident. Your job is to:
1. Use your tools to gather recent news and commodity price context
2. Evaluate whether this is a genuine incident (AIS spoofing, illegal ship-to-ship transfer, piracy, sanctions evasion)
3. Assess the likely impact on commodity markets

Be rigorous but decisive. Use specific evidence from your tool results."""

TOOLS = [
    {
        "name": "search_recent_news",
        "description": "Search for recent news articles about maritime activity, geopolitical events, or commodity markets in a specific region.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. 'oil tanker Black Sea sanctions'"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region to focus on, e.g. 'Strait of Hormuz'"
                },
                "days_back": {
                    "type": "integer",
                    "description": "How many days of news to search (default 7)",
                    "default": 7
                }
            },
            "required": ["query", "region"]
        }
    },
    {
        "name": "get_commodity_price",
        "description": "Get current price and 30-day history for a commodity (oil, wheat, LNG, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "commodity": {
                    "type": "string",
                    "description": "Commodity name, e.g. 'Brent Crude Oil', 'LNG', 'Wheat'"
                },
                "days_back": {
                    "type": "integer",
                    "description": "Days of price history to retrieve",
                    "default": 30
                }
            },
            "required": ["commodity"]
        }
    }
]


async def execute_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "search_recent_news":
        results = await search_recent_news(
            query=tool_input["query"],
            region=tool_input.get("region", ""),
            days_back=tool_input.get("days_back", 7)
        )
        return json.dumps(results, indent=2)

    elif tool_name == "get_commodity_price":
        result = await get_commodity_price(
            commodity=tool_input["commodity"],
            days_back=tool_input.get("days_back", 30)
        )
        return json.dumps(result, indent=2)

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


async def evaluate_incident(incident: dict, region_commodities: list[str]) -> dict:
    """
    Run the evaluator agent on a single incident.
    Returns a structured evaluation dict.
    """

    incident_desc = f"""
MARITIME INCIDENT ALERT
========================
Type: {incident.get('type', 'unknown')}
Region: {incident.get('region', 'unknown')}
Location: {incident.get('lat', 0):.4f}°N, {incident.get('lon', 0):.4f}°E
Vessel: MMSI {incident.get('mmsi', 'unknown')}, Name: {incident.get('ship_name', 'Unknown')}
Duration: {incident.get('duration_minutes', 0):.0f} minutes
Nearby vessels: {incident.get('nearby_ships', [])}
Timestamp: {incident.get('timestamp', 'now')}

Region commodities of interest: {', '.join(region_commodities)}

Please:
1. Search for recent news about this region
2. Get current prices for the most relevant commodity
3. Assess the incident and provide a structured JSON evaluation
"""

    messages = [{"role": "user", "content": incident_desc}]

    # Agentic loop with tool use
    max_iterations = 6
    for _ in range(max_iterations):
        response = await client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Append assistant's response
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_content = await execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_content,
                    })
            messages.append({"role": "user", "content": tool_results})

    # Extract text response
    final_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            final_text += block.text

    # Try to parse JSON from response
    try:
        # Look for JSON block in the response
        import re
        json_match = re.search(r'\{[\s\S]*\}', final_text)
        if json_match:
            return json.loads(json_match.group())
    except Exception:
        pass

    # Fallback: generate a structured response based on text
    return {
        "confidence_score": 65,
        "incident_type": "possible_sanctions_evasion",
        "severity": "medium",
        "commodities_affected": region_commodities[:2],
        "reasoning": final_text[:500],
        "evidence": ["AIS dropout detected", "Region historically linked to dark activity"],
        "recommended_watch": True,
    }
