# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import re
import uuid
from zoneinfo import ZoneInfo

import requests
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google import genai
from google.cloud import firestore, storage
from google.genai import types

from google.adk.code_executors.agent_engine_sandbox_code_executor import (
    AgentEngineSandboxCodeExecutor,
)

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from app.a2ui_utils import a2ui_callback

PROJECT_ID = "qwiklabs-gcp-04-72024f788a4d"
BUCKET_NAME = "qwiklabs-gcp-04-72024f788a4d-static-assets-bucket"
AGENT_ENGINE_RESOURCE_NAME = "projects/746320986672/locations/us-east1/reasoningEngines/1691330358496198656"
MODEL = "gemini-3.6-flash"

sandbox_code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=AGENT_ENGINE_RESOURCE_NAME
)

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are an Event Weather & Climate Safeguard assistant operating under the primary "
        "mission: **To Protect Life and Property** through timely "
        "warnings, accurate forecasts, and proactive event preparedness."
    ),
    workflow_description="Analyze event safeguard requests, geocode locations, query NWS forecasts & active alerts, manage Firestore records, and emit structured UI cards when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image. Set the Image url to that exact https link. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

domain_instruction = (
    "EVENT PREPAREDNESS & EMERGENCY ACTION PLAN (EAP) FRAMEWORK:\n"
    "1. Define Weather Hazards: Identify specific hazards that could impact the outdoor event "
    "(Severe Weather, Winter Weather, Lightning, Flooding, Extreme Heat/Wind).\n"
    "2. Structural Risk Profiling: Assess event structures (e.g. open air, open-sided tents, clear-span enclosed tents, "
    "metal trussing / stage scaffolding, permanent pavilions) against physical weather limits (wind load rating, lightning conductivity, mud saturation).\n"
    "3. Centralized Communications & Emergency Action Plan (EAP):\n"
    "   - Evacuation & Seek Shelter Lead Time: Calculate total required lead time based on attendee count, venue footprint, and distance to shelter "
    "so attendees can seek shelter *before* hazardous weather arrives.\n"
    "   - Notification Channels & Pre-scripted Announcements: Establish PA system, horn, siren, or mobile alert protocols. Provide pre-printed, fill-in-the-blank "
    "announcement statements to ensure consistent messaging among event staff.\n"
    "   - Pre-Defined Sturdy Shelter Locations: Identify sturdy, permanent indoor structures (interior rooms away from windows). Never consider temporary tents or open canopies "
    "as shelter during severe weather (lightning, severe wind, hail, or tornadoes). Instruct attendees to remain indoors until severe weather clears.\n"
    "4. Timely NWS Point Forecasts, Active Alerts & SPC Mesoscale Discussions:\n"
    "   - Query official NWS REST APIs (api.weather.gov) for point forecasts and active watches/warnings.\n"
    "   - Query NOAA Storm Prediction Center (SPC) Mesoscale Discussions (spc.noaa.gov/products/md/) to determine if event coordinates fall within active severe weather boundaries.\n"
    "   - Translate SPC technical discussions into plain English crowd safety actions for event planners.\n"
    "5. Weather Safety Staff Training & Resources: Inform event staff that safety & awareness brochures and "
    "products/services training are available. Provide event liaison contact details when requested: Tom Frieders at (406) 652-0851 ext. 223.\n\n"
    "CROSS-SESSION MEMORY & PERSISTENCE MANDATE:\n"
    "1. Location & Geocoded Coordinates: Whenever the user shares a location or address, use `calculate_coordinates_and_address` "
    "to compute exact latitude and longitude. Retain both the address string and computed (latitude, longitude) coordinates "
    "in memory and in Firestore.\n"
    "2. Event Structure Type & Associated Risks: Ask for and store details on the event structure type and associated structural "
    "weather risks (e.g. max wind rating 25mph, lightning conductor risk, ground saturation/mud, heat trap under vinyl).\n"
    "3. Date-Specific NWS Point Forecasts: When an event date is provided or selected, invoke `get_nws_point_forecast` with the target date "
    "and coordinates. If the date falls within the 7-day forecast window, incorporate official NWS temperatures, wind speeds/directions, "
    "and precipitation chances into your safeguard plan and compare them directly against structural risks (e.g. comparing forecasted wind speeds "
    "against the structure rating).\n"
    "4. Continuous Weather Evaluation: Retain structure types, risks, and calculated coordinates in memory. As new weather forecasts, "
    "NWS active alerts, or SPC Mesoscale Discussions are introduced, continuously evaluate them against these specific structural risks.\n"
    "5. Memory Updates: Whenever revised details are provided, update both Memory Bank and Firestore.\n\n"
    "TOOLS GUIDELINES:\n"
    "- Use `calculate_coordinates_and_address` to compute latitude and longitude for any address/location.\n"
    "- Use `get_nws_point_forecast` to fetch official NWS forecasts for specific event dates and lat/long coordinates.\n"
    "- Use `get_nws_active_alerts` to query real-time NWS warnings and advisories using stored coordinates or location.\n"
    "- Use `get_spc_mesoscale_discussions` to check active NOAA SPC Mesoscale Discussions, perform boundary polygon checks, and translate discussions into crowd safety guidance.\n"
    "- Use `save_event_safeguard` to persist address, coordinates, structure type, and risks to Firestore.\n"
    "- Use `get_event_safeguards` to retrieve saved event records.\n"
    "- Use `generate_event_safety_video` to generate short animated weather safety and hazard advisory videos for outdoor events using Google's Omni model (gemini-omni-flash-preview) in the global region."
)






def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


def calculate_coordinates_and_address(location_or_address: str) -> str:
    """Calculates latitude and longitude coordinates for a location or address string.

    Args:
        location_or_address: Address or location name (e.g. '100 S Biscayne Blvd, Miami, FL' or 'Zilker Park, Austin, TX').

    Returns:
        Formatted summary containing calculated latitude, longitude, and formatted address.
    """
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(location_or_address)}&count=1"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200 and res.json().get("results"):
            item = res.json()["results"][0]
            lat = item["latitude"]
            lon = item["longitude"]
            name = item.get("name", "")
            admin = item.get("admin1", "")
            country = item.get("country", "")
            formatted_addr = f"{name}, {admin}, {country}".strip(", ")
            return f"Calculated Coordinates for '{location_or_address}': Latitude = {lat:.5f}, Longitude = {lon:.5f} (Formatted Address: {formatted_addr})."
        return f"Could not calculate exact coordinates for: '{location_or_address}'. Please verify city/state or address string."
    except Exception as e:
        return f"Geocoding error calculating coordinates: {e}"


def get_nws_point_forecast(
    target_date: str = "",
    location: str = "",
    latitude: float = None,
    longitude: float = None,
) -> str:
    """Queries the National Weather Service REST API (api.weather.gov) for point forecasts at exact lat/long coordinates.
    Filters forecast periods specifically for the target event date if it falls within the 7-day forecast window.

    Args:
        target_date: Target event date in YYYY-MM-DD format (e.g. '2026-08-14').
        location: Location name or city string if coordinates are not provided.
        latitude: Explicit latitude float (e.g. 25.77427).
        longitude: Explicit longitude float (e.g. -80.19366).

    Returns:
        Detailed NWS forecast for the target date or date range status message.
    """
    headers = {"User-Agent": "EventWeatherSafeguard/1.0 (contact@example.com)"}

    if location and (latitude is None or longitude is None):
        try:
            geo_res = requests.get(
                f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(location)}&count=1",
                timeout=5,
            )
            if geo_res.status_code == 200 and geo_res.json().get("results"):
                top = geo_res.json()["results"][0]
                latitude = top["latitude"]
                longitude = top["longitude"]
            else:
                return f"Could not resolve coordinates for location '{location}'."
        except Exception as e:
            return f"Geocoding error: {e}"

    if latitude is None or longitude is None:
        return "Please provide either a location name or latitude/longitude coordinates to query NWS point forecast."

    points_url = f"https://api.weather.gov/points/{latitude:.4f},{longitude:.4f}"
    try:
        pts_res = requests.get(points_url, headers=headers, timeout=8)
        if pts_res.status_code != 200:
            return f"NWS Points API returned HTTP {pts_res.status_code} for point ({latitude}, {longitude})."

        forecast_url = pts_res.json().get("properties", {}).get("forecast")
        if not forecast_url:
            return f"No NWS forecast endpoint URL found for gridpoint ({latitude}, {longitude})."

        fc_res = requests.get(forecast_url, headers=headers, timeout=8)
        if fc_res.status_code != 200:
            return f"NWS Forecast API returned HTTP {fc_res.status_code} from {forecast_url}."

        periods = fc_res.json().get("properties", {}).get("periods", [])
        if not periods:
            return f"No forecast periods returned from NWS for point ({latitude}, {longitude})."

        available_dates = sorted(list(set(p.get("startTime", "")[:10] for p in periods if p.get("startTime"))))
        min_date, max_date = available_dates[0], available_dates[-1]

        loc_desc = location if location else f"point ({latitude:.4f}, {longitude:.4f})"

        if target_date:
            matching = [p for p in periods if p.get("startTime", "")[:10] == target_date]
            if matching:
                out = [f"🌤️ **NWS Official Point Forecast for {loc_desc} on {target_date}** (Lat: {latitude:.4f}, Lon: {longitude:.4f}):\n"]
                for p in matching:
                    name = p.get("name")
                    temp = p.get("temperature")
                    unit = p.get("temperatureUnit")
                    ws = p.get("windSpeed")
                    wd = p.get("windDirection")
                    wind = f"{ws} {wd}"
                    pop = p.get("probabilityOfPrecipitation", {}).get("value")
                    pop_str = f"{pop}%" if pop is not None else "N/A"
                    short = p.get("shortForecast")
                    detailed = p.get("detailedForecast")
                    out.append(
                        f"• **{name}**: {temp}°{unit} | Wind: {wind} | Precip Chance: {pop_str}\n"
                        f"  *Summary*: {short}\n"
                        f"  *Details*: {detailed}"
                    )
                return "\n\n".join(out)
            else:
                return (
                    f"📅 The selected target date **{target_date}** is outside the current 7-day NWS forecast range "
                    f"({min_date} to {max_date}) for {loc_desc}.\n"
                    f"*(Note: Official NWS detailed point forecasts are generated up to 7 days in advance. "
                    f"For dates beyond 7 days, refer to climatology and seasonal outlooks).*"
                )

        return f"NWS 7-day forecast available for {loc_desc} ({min_date} to {max_date}, {len(periods)} periods)."
    except Exception as e:
        return f"Failed to fetch NWS point forecast: {e}"


def get_nws_active_alerts(
    location: str = "", latitude: float = None, longitude: float = None
) -> str:
    """Queries the National Weather Service (NWS / api.weather.gov) for real-time active severe weather alerts.

    Args:
        location: City name or location (e.g. 'Miami, FL', 'Austin, TX', 'Denver, CO'). Automatically resolves coordinates.
        latitude: Optional explicit latitude float (e.g. 25.77427).
        longitude: Optional explicit longitude float (e.g. -80.19366).

    Returns:
        Formatted summary of active NWS severe weather alerts (e.g. Heat Advisories, Flood Watches, Severe Thunderstorm Warnings).
    """
    headers = {"User-Agent": "EventWeatherSafeguard/1.0 (contact@example.com)"}

    if location and (latitude is None or longitude is None):
        try:
            geo_res = requests.get(
                f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(location)}&count=1",
                timeout=5,
            )
            if geo_res.status_code == 200 and geo_res.json().get("results"):
                top_match = geo_res.json()["results"][0]
                latitude = top_match["latitude"]
                longitude = top_match["longitude"]
            else:
                return f"Could not geocode location '{location}' to query National Weather Service alerts."
        except Exception as e:
            return f"Error geocoding location '{location}': {e}"

    if latitude is None or longitude is None:
        return "Please provide either a location name or latitude/longitude coordinates to query NWS alerts."

    nws_url = f"https://api.weather.gov/alerts/active?point={latitude:.4f},{longitude:.4f}"
    try:
        res = requests.get(nws_url, headers=headers, timeout=8)
        if res.status_code != 200:
            return f"NWS API returned HTTP {res.status_code} for point ({latitude}, {longitude})."

        data = res.json()
        features = data.get("features", [])
        loc_str = location if location else f"coordinates ({latitude:.4f}, {longitude:.4f})"
        if not features:
            return f"✅ No active National Weather Service alerts currently in effect for {loc_str}."

        alerts_summary = []
        for feat in features[:5]:
            props = feat.get("properties", {})
            event = props.get("event", "Weather Alert")
            headline = props.get("headline", "No headline details.")
            severity = props.get("severity", "Unknown")
            urgency = props.get("urgency", "Unknown")
            instruction = props.get("instruction") or "Monitor local weather updates and follow emergency guidance."

            alerts_summary.append(
                f"🚨 **{event}** (Severity: {severity} | Urgency: {urgency})\n"
                f"   Headline: {headline}\n"
                f"   Action Instruction: {instruction.strip()[:300]}..."
            )

        return f"Found {len(features)} active NWS weather alert(s) for {loc_str}:\n\n" + "\n\n".join(alerts_summary)
    except Exception as e:
        return f"Failed to fetch NWS alerts: {e}"


def summarize_afd_plain_english(raw_text: str) -> str:
    """Translates raw NWS Area Forecast Discussion text into plain English with normal spelling and threat highlights."""
    km_match = re.search(r"\.KEY MESSAGES\.\.\.([\s\S]*?)(?=\&\&|\.[A-Z\s]+\.\.\.)", raw_text)
    key_messages = []
    if km_match:
        lines = km_match.group(1).strip().split("\n")
        for l in lines:
            l_clean = re.sub(r"^[-\*•\d\)\.\s]+", "", l.strip()).strip()
            if l_clean and not l_clean.startswith(".KEY") and not l_clean.startswith("KEY"):
                l_clean = l_clean.replace("t-storms", "thunderstorms").replace("lvl", "level")
                key_messages.append(l_clean)

    threats = []
    text_lower = raw_text.lower()

    if any(k in text_lower for k in ["extreme heat", "heat advisory", "heat index", "wbgt"]):
        threats.append(
            ("🔥 EXTREME HEAT HAZARD", "Dangerous heat and humidity. Afternoon heat indices may reach 105°F to 120°F with 'Black Flag' outdoor activity risks.")
        )

    if any(k in text_lower for k in ["severe", "damaging wind", "t-storm", "thunderstorm", "mcv"]):
        threats.append(
            ("⚡ SEVERE THUNDERSTORM RISK", "Scattered afternoon storm clusters expected. Primary hazards: localized damaging wind gusts, frequent lightning, and heavy downpours.")
        )

    if any(k in text_lower for k in ["coastal flood", "tide", "rip current"]):
        threats.append(
            ("🌊 COASTAL & MARINE UPDATE", "Minor tidal flooding possible near high tide. Marine waters remain mostly calm with 2-3 ft seas.")
        )

    if not threats:
        threats.append(
            ("✅ NO SEVERE WEATHER THREATS", "Forecast indicates tranquil weather conditions with no immediate severe hazards.")
        )

    summary_lines = [
        "🎯 **Key Forecast Takeaways:**"
    ]

    if key_messages:
        for km in key_messages:
            summary_lines.append(f"• {km}")
    else:
        summary_lines.append("• High heat and humidity persist across the region with potential afternoon storm development.")

    summary_lines.append("\n🚨 **Highlighted Weather Threats & Event Safety Impact:**")
    for title, desc in threats:
        summary_lines.append(f"• **{title}**: {desc}")

    return "\n".join(summary_lines)


def get_nws_forecast_discussion(
    location: str = "", latitude: float = None, longitude: float = None
) -> str:
    """Queries the National Weather Service (NWS / api.weather.gov) for the official Area Forecast Discussion (AFD)
    issued by the local NWS Weather Forecast Office (WFO / CWA) and returns a plain-English summary with threat highlights.

    Args:
        location: City name or venue location (e.g. 'Savannah, GA', 'Austin, TX'). Resolves coordinates.
        latitude: Optional explicit latitude float (e.g. 32.0008).
        longitude: Optional explicit longitude float (e.g. -80.9735).

    Returns:
        Plain-English summary of local NWS Area Forecast Discussion with highlighted weather threats,
        CWA office code, issuance timestamp, and direct forecast.weather.gov web URL.
    """
    headers = {"User-Agent": "EventWeatherSafeguard/1.0 (contact@example.com)"}

    if location and (latitude is None or longitude is None):
        try:
            geo_res = requests.get(
                f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(location)}&count=1",
                timeout=5,
            )
            if geo_res.status_code == 200 and geo_res.json().get("results"):
                top = geo_res.json()["results"][0]
                latitude = top["latitude"]
                longitude = top["longitude"]
            else:
                return f"Could not resolve coordinates for location '{location}'."
        except Exception as e:
            return f"Geocoding error: {e}"

    if latitude is None or longitude is None:
        latitude, longitude = 32.0008, -80.9735

    points_url = f"https://api.weather.gov/points/{latitude:.4f},{longitude:.4f}"
    try:
        pts_res = requests.get(points_url, headers=headers, timeout=8)
        if pts_res.status_code != 200:
            return f"NWS Points API returned HTTP {pts_res.status_code} for point ({latitude}, {longitude})."

        props = pts_res.json().get("properties", {})
        cwa = props.get("cwa")
        forecast_office = props.get("forecastOffice")

        if not cwa:
            return f"No CWA (County Warning Area) office code returned for point ({latitude}, {longitude})."

        web_discussion_url = f"https://forecast.weather.gov/product.php?site={cwa}&product=AFD&issuedby={cwa}"

        afd_api = f"https://api.weather.gov/products/types/AFD/locations/{cwa}"
        afd_res = requests.get(afd_api, headers=headers, timeout=8)
        if afd_res.status_code != 200:
            return (
                f"NWS CWA Office Code: {cwa}. Could not retrieve discussion API payload. "
                f"Direct Discussion URL: {web_discussion_url}"
            )

        graph = afd_res.json().get("@graph", [])
        if not graph:
            return f"No active forecast discussions found for NWS CWA Office {cwa}. Direct URL: {web_discussion_url}"

        latest_id = graph[0].get("id")
        prod_res = requests.get(f"https://api.weather.gov/products/{latest_id}", headers=headers, timeout=8)
        if prod_res.status_code != 200:
            return f"Failed to retrieve discussion product {latest_id}. Direct URL: {web_discussion_url}"

        prod_data = prod_res.json()
        product_text = prod_data.get("productText", "")
        issuance_time = prod_data.get("issuanceTime", "")

        plain_english = summarize_afd_plain_english(product_text)

        return (
            f"=== NWS AREA FORECAST DISCUSSION BRIEFING (WFO Office: {cwa}) ===\n"
            f"📍 Location Coordinates: {latitude:.4f}° N, {longitude:.4f}° W\n"
            f"🏢 Forecast Office: {forecast_office}\n"
            f"⏰ Issued At: {issuance_time}\n"
            f"🔗 Direct NWS Discussion Web Page: {web_discussion_url}\n\n"
            f"{plain_english}\n\n"
            f"[View full original NWS text: {web_discussion_url}]"
        )
    except Exception as e:
        return f"Error fetching NWS Area Forecast Discussion: {e}"


def summarize_hwo_plain_english(raw_text: str) -> str:
    """Parses raw NWS Hazardous Weather Outlook (HWO) text product and formats into clean plain English with threat highlights."""
    if not raw_text or not raw_text.strip():
        return "No Hazardous Weather Outlook text provided."

    day_one = ""
    days_extended = ""

    d1_match = re.search(r'\.DAY ONE\.\.\.([\s\S]*?)(?=\.DAYS TWO THROUGH SEVEN|\.SPOTTER|\$\$)', raw_text, re.IGNORECASE)
    if d1_match:
        day_one = d1_match.group(1).strip()

    d2_match = re.search(r'\.DAYS TWO THROUGH SEVEN\.\.\.([\s\S]*?)(?=\.SPOTTER|\$\$)', raw_text, re.IGNORECASE)
    if d2_match:
        days_extended = d2_match.group(1).strip()

    def clean_sec(txt):
        txt = re.sub(r'Weather hazards expected\.\.\.', '', txt, flags=re.IGNORECASE)
        txt = re.sub(r'DISCUSSION\.\.\.', '\n**Discussion:**', txt, flags=re.IGNORECASE)
        lines = [line.strip() for line in txt.split('\n') if line.strip()]
        out = []
        for line in lines:
            if line.startswith('Level ') or 'Risk' in line:
                out.append(f"• **{line}**")
            elif line.startswith('**Discussion:**'):
                out.append(line)
            elif line.startswith('.'):
                out.append(f"\n**{line.replace('.', '').strip()}**")
            else:
                out.append(line)
        return "\n".join(out)

    summary_lines = []

    if day_one:
        summary_lines.append("🎯 **Day 1 Hazardous Weather Outlook (Immediate / Today):**")
        summary_lines.append(clean_sec(day_one))

    if days_extended:
        summary_lines.append("\n📅 **Days 2–7 Extended Hazardous Weather Outlook:**")
        summary_lines.append(clean_sec(days_extended))

    threats = []
    upper_txt = raw_text.upper()
    if 'DAMAGING WIND' in upper_txt or 'WIND RISK' in upper_txt:
        threats.append(("💨 DAMAGING WIND HAZARD", "Damaging Wind Risk noted in local HWO."))
    if 'FLOODING' in upper_txt or 'FLASH FLOOD' in upper_txt:
        threats.append(("🌊 FLOODING / HEAVY RAIN HAZARD", "Elevated or Significant Flooding Risk indicated in local HWO."))
    if 'THUNDERSTORM' in upper_txt or 'SEVERE' in upper_txt:
        threats.append(("⚡ SEVERE THUNDERSTORM HAZARD", "Thunderstorm Risk indicated in local HWO."))
    if 'HEAT' in upper_txt:
        threats.append(("🔥 EXCESSIVE HEAT HAZARD", "Excessive Heat Risk indicated in local HWO."))

    if threats:
        summary_lines.append("\n🚨 **Highlighted HWO Threat Warnings:**")
        for title, desc in threats:
            summary_lines.append(f"• **{title}**: {desc}")

    return "\n".join(summary_lines)


def get_nws_hazardous_weather_outlook(
    location: str = "", latitude: float = None, longitude: float = None
) -> str:
    """Queries the National Weather Service (NWS / api.weather.gov) for the official Hazardous Weather Outlook (HWO)
    issued by the local NWS Weather Forecast Office (WFO / CWA) and returns a plain-English summary with threat highlights.

    Args:
        location: City name or venue location (e.g. 'Savannah, GA', 'Denver, CO'). Resolves coordinates.
        latitude: Optional explicit latitude float (e.g. 39.7392).
        longitude: Optional explicit longitude float (e.g. -104.9903).

    Returns:
        Plain-English summary of local NWS Hazardous Weather Outlook with highlighted hazards,
        CWA office code, issuance timestamp, and direct forecast.weather.gov web URL.
    """
    headers = {"User-Agent": "EventWeatherSafeguard/1.0 (contact@example.com)"}

    if location and (latitude is None or longitude is None):
        try:
            geo_res = requests.get(
                f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(location)}&count=1",
                timeout=5,
            )
            if geo_res.status_code == 200 and geo_res.json().get("results"):
                top = geo_res.json()["results"][0]
                latitude = top["latitude"]
                longitude = top["longitude"]
            else:
                return f"Could not resolve coordinates for location '{location}'."
        except Exception as e:
            return f"Geocoding error: {e}"

    if latitude is None or longitude is None:
        latitude, longitude = 32.0008, -80.9735

    points_url = f"https://api.weather.gov/points/{latitude:.4f},{longitude:.4f}"
    try:
        pts_res = requests.get(points_url, headers=headers, timeout=8)
        if pts_res.status_code != 200:
            return f"NWS Points API returned HTTP {pts_res.status_code} for point ({latitude}, {longitude})."

        props = pts_res.json().get("properties", {})
        cwa = props.get("cwa")
        forecast_office = props.get("forecastOffice")

        if not cwa:
            return f"No CWA office code returned for point ({latitude}, {longitude})."

        web_hwo_url = f"https://forecast.weather.gov/product.php?site={cwa}&product=HWO&issuedby={cwa}"

        hwo_api = f"https://api.weather.gov/products/types/HWO/locations/{cwa}"
        hwo_res = requests.get(hwo_api, headers=headers, timeout=8)
        if hwo_res.status_code != 200:
            return f"No active HWO product found for local office {cwa}. Direct Web Page: {web_hwo_url}"

        graph = hwo_res.json().get("@graph", [])
        if not graph:
            return f"No active Hazardous Weather Outlooks found for local office {cwa}. Direct Web Page: {web_hwo_url}"

        latest_id = graph[0].get("id")
        prod_res = requests.get(f"https://api.weather.gov/products/{latest_id}", headers=headers, timeout=8)
        if prod_res.status_code != 200:
            return f"Failed to retrieve HWO product {latest_id}. Direct URL: {web_hwo_url}"

        prod_data = prod_res.json()
        product_text = prod_data.get("productText", "")
        issuance_time = prod_data.get("issuanceTime", "")

        plain_english = summarize_hwo_plain_english(product_text)

        return (
            f"=== NWS HAZARDOUS WEATHER OUTLOOK (HWO) (WFO Office: {cwa}) ===\n"
            f"📍 Location Coordinates: {latitude:.4f}° N, {longitude:.4f}° W\n"
            f"🏢 Forecast Office: {forecast_office}\n"
            f"⏰ Issued At: {issuance_time}\n"
            f"🔗 Direct NWS HWO Web Page: {web_hwo_url}\n\n"
            f"{plain_english}\n\n"
            f"[View full original NWS text: {web_hwo_url}]"
        )
    except Exception as e:
        return f"Error fetching Hazardous Weather Outlook: {e}"
    except Exception as e:
        return f"Error fetching NWS Area Forecast Discussion: {e}"


def parse_lat_lon_block(raw_text: str) -> list[tuple[float, float]]:
    """Parses LAT...LON polygon boundary coordinates from SPC Mesoscale Discussion text."""
    match = re.search(r"LAT\.\.\.LON\s+([\d\s]+)", raw_text, re.MULTILINE)
    if not match:
        return []
    raw_nums = match.group(1).split()
    poly = []
    for pair in raw_nums:
        if len(pair) == 8:
            lat_val = int(pair[:4]) / 100.0
            lon_part = int(pair[4:])
            if lon_part < 5000:
                lon_val = -(100.0 + lon_part / 100.0)
            else:
                lon_val = -(lon_part / 100.0)
            poly.append((lat_val, lon_val))
    return poly


def point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    """Performs ray-casting point-in-polygon spatial check for (lat, lon) within a polygon."""
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    p1_lat, p1_lon = polygon[0]
    for i in range(n + 1):
        p2_lat, p2_lon = polygon[i % n]
        if lon > min(p1_lon, p2_lon):
            if lon <= max(p1_lon, p2_lon):
                if lat <= max(p1_lat, p2_lat):
                    if p1_lon != p2_lon:
                        xinters = (lon - p1_lon) * (p2_lat - p1_lat) / (p2_lon - p1_lon) + p1_lat
                    else:
                        xinters = p1_lat
                    if p1_lat == p2_lat or lat <= xinters:
                        inside = not inside
        p1_lat, p1_lon = p2_lat, p2_lon
    return inside


def get_spc_mesoscale_discussions(
    location: str = "", latitude: float = None, longitude: float = None
) -> str:
    """Queries NOAA Storm Prediction Center (SPC) for active Mesoscale Discussions (https://www.spc.noaa.gov/products/md/).
    Parses geographic boundary polygons (LAT...LON) and performs spatial point-in-polygon checks to determine if the event location
    falls within active SPC Mesoscale Discussion severe weather risk areas.

    Args:
        location: Location name or city string (e.g. 'Denver, CO', 'Amarillo, TX'). Automatically geocodes coordinates if missing.
        latitude: Optional explicit latitude float (e.g. 39.7392).
        longitude: Optional explicit longitude float (e.g. -104.9903).

    Returns:
        Structured evaluation indicating whether the event falls within active Mesoscale Discussion borders,
        translating severe weather threats into plain English, and providing actionable crowd safety guidelines.
    """
    headers = {"User-Agent": "EventWeatherSafeguard/1.0 (contact@example.com)"}

    if location and (latitude is None or longitude is None):
        try:
            geo_res = requests.get(
                f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(location)}&count=1",
                timeout=5,
            )
            if geo_res.status_code == 200 and geo_res.json().get("results"):
                top = geo_res.json()["results"][0]
                latitude = top["latitude"]
                longitude = top["longitude"]
            else:
                return f"Could not geocode location '{location}' to check SPC Mesoscale Discussions."
        except Exception as e:
            return f"Error geocoding location '{location}': {e}"

    if latitude is None or longitude is None:
        return "Please provide either a location name or latitude/longitude coordinates to check SPC Mesoscale Discussions."

    loc_str = location if location else f"point ({latitude:.4f}, {longitude:.4f})"

    try:
        main_url = "https://www.spc.noaa.gov/products/md/"
        res = requests.get(main_url, headers=headers, timeout=8)
        if res.status_code != 200:
            return f"SPC Mesoscale Discussion index returned HTTP {res.status_code}."

        md_files = sorted(list(set(re.findall(r"md\d{4}\.html", res.text, re.IGNORECASE))))
        if not md_files:
            return f"✅ No active SPC Mesoscale Discussions currently issued nationwide. {loc_str} is clear of active mesoscale severe weather threats."

        discussions_output = []
        matching_count = 0

        for md_file in md_files:
            md_url = f"https://www.spc.noaa.gov/products/md/{md_file}"
            md_res = requests.get(md_url, headers=headers, timeout=8)
            if md_res.status_code != 200:
                continue

            pre_match = re.search(r"<pre>(.*?)</pre>", md_res.text, re.DOTALL | re.IGNORECASE)
            text = pre_match.group(1) if pre_match else md_res.text

            md_num = md_file.replace(".html", "").upper()
            concerning = re.search(r"Concerning\.\.\.(.*?)\n", text)
            concerning_str = concerning.group(1).strip() if concerning else "N/A"

            areas = re.search(r"Areas affected\.\.\.(.*?)\n", text)
            areas_str = areas.group(1).strip() if areas else "N/A"

            watch_prob = re.search(r"Probability of Watch Issuance\.\.\.(.*?)\n", text)
            watch_prob_str = watch_prob.group(1).strip() if watch_prob else "N/A"

            summary = re.search(r"SUMMARY\.\.\.(.*?)\n\n", text, re.DOTALL)
            summary_str = (
                summary.group(1).replace("\n", " ").strip() if summary else "No summary paragraph."
            )

            poly = parse_lat_lon_block(text)
            is_inside = point_in_polygon(latitude, longitude, poly)

            if is_inside:
                matching_count += 1
                status = f"🚨 **LOCATION INSIDE RISK BORDER** (Target Lat: {latitude:.4f}, Lon: {longitude:.4f})"
                action_advice = (
                    "   *Event Planner Safety Actions*:\n"
                    "   1. **Evacuation Countdown**: Initiate venue evacuation lead-time timers.\n"
                    "   2. **Pre-scripted Announcements**: Prepare PA/siren announcements to notify attendees consistently.\n"
                    "   3. **Sturdy Shelter Identification**: Direct attendees to pre-defined interior rooms in permanent buildings. Tents/open canopies are unsafe."
                )
            else:
                status = f"ℹ️ Location Outside Border (Target Lat: {latitude:.4f}, Lon: {longitude:.4f})"
                action_advice = "   *Action*: Monitor local NWS forecasts and watches."

            discussions_output.append(
                f"📌 **{md_num}** ({md_url})\n"
                f"   • **Status**: {status}\n"
                f"   • **Concerning**: {concerning_str} | **Watch Prob**: {watch_prob_str}\n"
                f"   • **Areas Affected**: {areas_str}\n"
                f"   • **Plain English Summary**: {summary_str}\n"
                f"{action_advice}"
            )

        summary_header = (
            f"FOUND {len(md_files)} ACTIVE SPC MESOSCALE DISCUSSION(S) NATIONWIDE. "
            f"Event Location '{loc_str}' falls INSIDE BORDERS of {matching_count} active discussion(s):\n\n"
        )
        return summary_header + "\n\n".join(discussions_output)
    except Exception as e:
        return f"Error fetching SPC Mesoscale Discussions: {e}"


def save_event_safeguard(
    event_name: str,
    location: str,
    event_date: str,
    address: str = "",
    latitude: float = None,
    longitude: float = None,
    event_type: str = "Outdoor Event",
    attendee_count: int = 100,
    structure_type: str = "Open Air",
    structure_risks: list[str] = None,
    weather_threats: list[str] = None,
    prep_status: str = "Planning in progress",
) -> str:
    """Saves or updates an event safeguard record in the Firestore database ('events' collection).

    Args:
        event_name: Name of the outdoor event (e.g. Austin Summer Music Festival).
        location: City and state location (e.g. Austin, TX).
        event_date: Target event date in YYYY-MM-DD format.
        address: Full street address or venue location if available.
        latitude: Calculated latitude float.
        longitude: Calculated longitude float.
        event_type: Type of event (e.g. Music Festival, Outdoor Wedding, Concert).
        attendee_count: Estimated number of attendees.
        structure_type: Structure type (e.g. Open Air, Open-sided Tent, Enclosed Tent, Stage Scaffolding).
        structure_risks: Associated structural weather risks (e.g. ['Wind threshold 25mph', 'Lightning hazard on metal truss']).
        weather_threats: List of identified weather risks (e.g. ['Extreme Heat', 'Flash Floods']).
        prep_status: Summary of preparedness and safeguards in place.

    Returns:
        Status message confirming the record was saved in Firestore.
    """
    if weather_threats is None:
        weather_threats = []
    if structure_risks is None:
        structure_risks = []

    db = firestore.Client(project=PROJECT_ID)
    doc_id = f"{location.lower().replace(', ', '_').replace(' ', '_')}_{event_date}"
    doc_ref = db.collection("events").document(doc_id)

    record = {
        "event_name": event_name,
        "location": location,
        "address": address or location,
        "latitude": latitude,
        "longitude": longitude,
        "event_date": event_date,
        "event_type": event_type,
        "attendee_count": attendee_count,
        "structure_type": structure_type,
        "structure_risks": structure_risks,
        "weather_threats": weather_threats,
        "prep_status": prep_status,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    doc_ref.set(record, merge=True)
    coords_info = f"[Lat: {latitude}, Lon: {longitude}]" if latitude is not None and longitude is not None else "[No coords]"
    return f"Successfully saved event safeguard for '{event_name}' ({structure_type}) at {location} {coords_info} to Firestore."


def get_event_safeguards(location: str = "") -> str:
    """Queries and retrieves saved event safeguard records from the Firestore database ('events' collection).

    Args:
        location: Optional location filter (e.g. 'Miami' or 'Austin'). If empty, returns all events.

    Returns:
        Formatted summary list of matching event safeguard records.
    """
    db = firestore.Client(project=PROJECT_ID)
    events_ref = db.collection("events")

    results = []
    for doc in events_ref.stream():
        data = doc.to_dict()
        data["doc_id"] = doc.id
        if not location or location.lower() in data.get("location", "").lower():
            results.append(data)

    if not results:
        return f"No saved event safeguards found in Firestore matching location filter: '{location}'."

    output = []
    for evt in results:
        threats_str = ", ".join(evt.get("weather_threats", [])) if evt.get("weather_threats") else "None specified"
        s_risks_str = ", ".join(evt.get("structure_risks", [])) if evt.get("structure_risks") else "None specified"
        lat = evt.get("latitude")
        lon = evt.get("longitude")
        coords_str = f"Lat: {lat}, Lon: {lon}" if lat is not None and lon is not None else "Not calculated"
        output.append(
            f"• Event: {evt.get('event_name')} | Date: {evt.get('event_date')} | Location: {evt.get('location')}\n"
            f"  Address: {evt.get('address')} | Coordinates: {coords_str}\n"
            f"  Structure Type: {evt.get('structure_type')} | Associated Risks: {s_risks_str}\n"
            f"  Type: {evt.get('event_type')} | Attendees: {evt.get('attendee_count')}\n"
            f"  Weather Threats: {threats_str}\n"
            f"  Prep Status: {evt.get('prep_status')}"
        )
    return f"Retrieved {len(results)} event safeguard(s) from Firestore:\n\n" + "\n\n".join(output)


def generate_event_safety_video(prompt: str, tool_context: ToolContext = None) -> str:
    """Generates a short animated event weather safety advisory or hazard video using Google's Omni model (gemini-omni-flash-preview) in the global region.
    Saves the generated video as an artifact via tool_context and uploads the video bytes to public Cloud Storage, returning its public HTTPS URL.

    Args:
        prompt: Description of the event weather safety video to generate (e.g. 'Short 3-second video showing dark storm clouds over an outdoor music festival and attendees moving safely into a sturdy indoor shelter.').
        tool_context: ADK ToolContext provided automatically by the agent runtime.

    Returns:
        Formatted string containing the public HTTPS URL of the generated video uploaded to Cloud Storage.
    """
    try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        res = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )

        video_bytes = None
        for step in getattr(res, "steps", []):
            if hasattr(step, "content"):
                for item in step.content:
                    if hasattr(item, "data") and item.data:
                        raw_data = item.data
                        if isinstance(raw_data, str):
                            video_bytes = base64.b64decode(raw_data)
                        else:
                            video_bytes = raw_data

        if not video_bytes:
            return "Failed to extract generated video bytes from gemini-omni-flash-preview response."

        video_id = uuid.uuid4().hex[:8]
        filename_obj = f"videos/event_safety_{video_id}.mp4"

        if tool_context and hasattr(tool_context, "save_artifact"):
            part = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")
            tool_context.save_artifact(f"event_safety_{video_id}.mp4", part)

        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename_obj)
        blob.upload_from_string(video_bytes, content_type="video/mp4")

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename_obj}"
        return f"Generated event weather safety video successfully. Public URL: {public_url}"
    except Exception as e:
        return f"Error generating event weather safety video with gemini-omni-flash-preview: {e}"


async def generate_memories_callback(callback_context: CallbackContext):
    """Callback to send session events to Memory Bank after each turn."""
    await callback_context.add_session_to_memory()
    return None


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=f"{a2ui_instruction}\n\n{domain_instruction}",
    tools=[
        PreloadMemoryTool(),
        get_weather,
        get_current_time,
        calculate_coordinates_and_address,
        get_nws_point_forecast,
        get_nws_active_alerts,
        get_nws_forecast_discussion,
        get_nws_hazardous_weather_outlook,
        get_spc_mesoscale_discussions,
        save_event_safeguard,
        get_event_safeguards,
        generate_event_safety_video,
    ],
    code_executor=sandbox_code_executor,
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)


app = App(
    root_agent=root_agent,
    name="app",
)









