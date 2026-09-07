"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Why A2A: agents-cli 1.1.0 (GA) deploys ADK agents to Agent Runtime as A2A agents
and no longer registers the reasoning-engine operation schema the old
`agent_engines.get(...).stream_query()` path relied on (operation_schemas() comes
back empty). The container serves the A2A protocol over the Agent Engine HTTP
passthrough, so this proxy fetches the agent's card and sends messages with the
a2a-sdk client (the same path `agents-cli run --mode a2a` uses). This works for
both A2A and plain ADK 1.1.0 deployments (the container serves A2A either way).

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

import os
import re
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    FilePart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TextPart,
    TransportProtocol,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
AGENT_BACKEND_URL = os.environ.get("AGENT_BACKEND_URL")
USE_LOCAL_PLAYGROUND = os.environ.get("LOCAL_PLAYGROUND", "true").lower() == "true"

if AGENT_BACKEND_URL:
    # Connect to custom containerized backend on Cloud Run
    A2A_BASE = f"{AGENT_BACKEND_URL.rstrip('/')}/api/a2a/{AGENT_DIRECTORY}"
    USE_LOCAL_PLAYGROUND = True  # Bypass GCP IAM credentials logic
elif USE_LOCAL_PLAYGROUND:
    A2A_BASE = f"http://127.0.0.1:8080/api/a2a/{AGENT_DIRECTORY}"
else:
    RESOURCE = os.environ.get(
        "AGENT_ENGINE_RESOURCE_NAME",
        "projects/746320986672/locations/us-east1/reasoningEngines/1691330358496198656",
    )
    LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]
    A2A_BASE = (
        f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
        f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
    )

A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds = None
if not USE_LOCAL_PLAYGROUND:
    _creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )


def _auth_headers() -> dict[str, str]:
    if USE_LOCAL_PLAYGROUND:
        return {
            "Content-Type": "application/json",
        }
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.middleware("http")
async def _disable_cache(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = AgentCard(**resp.json())
        # Agent Runtime does not serve a public card URL, so point the client at
        # the passthrough base for message sends.
        card.url = A2A_BASE
        _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI.

    Text parts pass through as {"kind": "text"}. A2UI data parts (tagged
    application/json+a2ui) become {"kind": "a2ui", "data": <message>} so the UI
    renders the card; each data part is one A2UI message (beginRendering or
    surfaceUpdate).
    """
    out: list[dict] = []
    for p in parts:
        root = getattr(p, "root", p)
        if isinstance(root, TextPart) and getattr(root, "text", None):
            out.append({"kind": "text", "text": root.text})
        elif getattr(root, "data", None) is not None:
            meta = getattr(root, "metadata", None) or {}
            mime = meta.get("mimeType") if isinstance(meta, dict) else None
            if mime == _A2UI_MIME:
                out.append({"kind": "a2ui", "data": root.data})
        elif isinstance(root, FilePart):
            uri = getattr(getattr(root, "file", None), "uri", None)
            if uri:
                out.append({"kind": "text", "text": uri})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(
            ClientConfig(
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
                httpx_client=client,
            )
        )
        a2a_client = factory.create(card)

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=message))],
            context_id=_contexts.get(user_id),
        )

        last_task = None
        got_artifact_update = False
        async for event in a2a_client.send_message(msg):
            if not isinstance(event, tuple):
                continue
            task, update = event
            if task is not None:
                last_task = task
                if getattr(task, "context_id", None):
                    _contexts[user_id] = task.context_id
            if isinstance(update, TaskArtifactUpdateEvent):
                got_artifact_update = True
                parts.extend(_extract_parts(update.artifact.parts))

        # Non-streaming fallback: pull parts from the final task's artifacts.
        if not got_artifact_update and last_task is not None:
            for artifact in getattr(last_task, "artifacts", None) or []:
                parts.extend(_extract_parts(artifact.parts))

    if not parts:
        # The turn produced no text or UI (e.g. the agent only ran tools, or a
        # tool stalled). Be honest rather than silent.
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


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


@app.get("/api/afd")
async def get_afd(lat: float = 32.0008, lon: float = -80.9735):
    """Fetches real-time NWS Area Forecast Discussion (AFD) strictly for latitude & longitude coordinates' local office."""
    headers = {"User-Agent": "EventWeatherSafeguard/1.0 (contact@example.com)"}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            pts_res = await client.get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}", headers=headers)
            if pts_res.status_code != 200:
                return JSONResponse({"has_briefing": False, "reason": f"NWS points API error: {pts_res.status_code}"})

            props = pts_res.json().get("properties", {})
            cwa = props.get("cwa")
            office_url = props.get("forecastOffice")

            if not cwa:
                return JSONResponse({"has_briefing": False, "reason": "No local CWA office found for coordinates"})

            web_url = f"https://forecast.weather.gov/product.php?site={cwa}&product=AFD&issuedby={cwa}"

            afd_res = await client.get(f"https://api.weather.gov/products/types/AFD/locations/{cwa}", headers=headers)
            if afd_res.status_code != 200:
                return JSONResponse({"has_briefing": False, "cwa": cwa, "reason": "No discussion product found for local office"})

            graph = afd_res.json().get("@graph", [])
            if not graph:
                return JSONResponse({"has_briefing": False, "cwa": cwa, "reason": "No active discussion products available for local office"})

            latest_id = graph[0].get("id")
            prod_res = await client.get(f"https://api.weather.gov/products/{latest_id}", headers=headers)
            if prod_res.status_code != 200:
                return JSONResponse({"has_briefing": False, "cwa": cwa, "reason": "Failed to load local discussion product"})

            prod_data = prod_res.json()
            raw_text = prod_data.get("productText", "")
            if not raw_text or not raw_text.strip():
                return JSONResponse({"has_briefing": False, "cwa": cwa, "reason": "Empty discussion product text"})

            plain_summary = summarize_afd_plain_english(raw_text)

            return JSONResponse({
                "has_briefing": True,
                "cwa": cwa,
                "forecast_office": office_url,
                "web_url": web_url,
                "issuance_time": prod_data.get("issuanceTime"),
                "product_text": raw_text,
                "plain_english_summary": plain_summary,
            })
        except Exception as e:
            return JSONResponse({"has_briefing": False, "reason": str(e)})


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


@app.get("/api/hwo")
async def get_hwo(lat: float = 32.0008, lon: float = -80.9735):
    """Fetches real-time NWS Hazardous Weather Outlook (HWO) strictly for latitude & longitude coordinates' local office."""
    headers = {"User-Agent": "EventWeatherSafeguard/1.0 (contact@example.com)"}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            pts_res = await client.get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}", headers=headers)
            if pts_res.status_code != 200:
                return JSONResponse({"has_hwo": False, "reason": f"NWS points API error: {pts_res.status_code}"})

            props = pts_res.json().get("properties", {})
            cwa = props.get("cwa")
            office_url = props.get("forecastOffice")

            if not cwa:
                return JSONResponse({"has_hwo": False, "reason": "No local CWA office found for coordinates"})

            web_url = f"https://forecast.weather.gov/product.php?site={cwa}&product=HWO&issuedby={cwa}"

            hwo_res = await client.get(f"https://api.weather.gov/products/types/HWO/locations/{cwa}", headers=headers)
            if hwo_res.status_code != 200:
                return JSONResponse({"has_hwo": False, "cwa": cwa, "reason": "No HWO product endpoint found for local office"})

            graph = hwo_res.json().get("@graph", [])
            if not graph:
                return JSONResponse({"has_hwo": False, "cwa": cwa, "reason": "No active Hazardous Weather Outlooks found for local office"})

            latest_id = graph[0].get("id")
            prod_res = await client.get(f"https://api.weather.gov/products/{latest_id}", headers=headers)
            if prod_res.status_code != 200:
                return JSONResponse({"has_hwo": False, "cwa": cwa, "reason": "Failed to load local HWO product details"})

            prod_data = prod_res.json()
            raw_text = prod_data.get("productText", "")
            if not raw_text or not raw_text.strip():
                return JSONResponse({"has_hwo": False, "cwa": cwa, "reason": "Empty HWO product text"})

            plain_summary = summarize_hwo_plain_english(raw_text)

            return JSONResponse({
                "has_hwo": True,
                "cwa": cwa,
                "forecast_office": office_url,
                "web_url": web_url,
                "issuance_time": prod_data.get("issuanceTime"),
                "product_text": raw_text,
                "plain_english_summary": plain_summary,
            })
        except Exception as e:
            return JSONResponse({"has_hwo": False, "reason": str(e)})



@app.get("/api/climatology")
async def get_climatology(
    lat: float = 32.0008,
    lon: float = -80.9735,
    target_date: str = "2026-08-13",
    location: str = "",
    attendees: int = 100,
    structure: str = "Open Air",
):
    """Fetches comprehensive long-term climatology, annual temperature curve, ENSO teleconnections, and operational safeguards."""
    try:
        from app.climatology import get_climatology_full_report
        report = await get_climatology_full_report(
            lat=lat,
            lon=lon,
            target_date_str=target_date,
            location_name=location,
            structure_type=structure,
            attendee_count=attendees,
        )
        return JSONResponse({"status": "success", "data": report})
    except Exception as e:
        return JSONResponse({"status": "error", "reason": str(e)}, status_code=500)


@app.get("/api/current-threat")
async def get_current_threat(
    lat: float = 32.0008,
    lon: float = -80.9735,
    event_date: str = "",
):
    """Synthesizes real-time active alerts, point forecast, and CWA briefing to spotlight the immediate primary threat for today's event."""
    headers = {"User-Agent": "SafeStageWX (event-weather-safeguard/1.0)"}
    async with httpx.AsyncClient(timeout=8.0) as client:
        # 1. Fetch active alerts
        features = []
        try:
            al_res = await client.get(f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}", headers=headers)
            if al_res.status_code == 200:
                features = al_res.json().get("features", [])
        except Exception:
            pass

        # 2. Fetch point forecast
        forecast_period = None
        cwa = "CHS"
        is_outside_us = False
        try:
            pts_res = await client.get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}", headers=headers)
            if pts_res.status_code == 200:
                props = pts_res.json().get("properties", {})
                cwa = props.get("cwa", "CHS")
                fc_url = props.get("forecast")
                if fc_url:
                    fc_res = await client.get(fc_url, headers=headers)
                    if fc_res.status_code == 200:
                        periods = fc_res.json().get("properties", {}).get("periods", [])
                        if periods:
                            forecast_period = periods[0]
            elif pts_res.status_code == 404:
                is_outside_us = True
        except Exception:
            pass

        if is_outside_us:
            return JSONResponse({
                "status": "outside_domain",
                "is_today": True,
                "severity": "MONITORING",
                "icon": "location_off",
                "headline": "Venue Outside National Weather Service (NWS) Coverage",
                "description": "The selected venue coordinates fall outside the United States National Weather Service forecast domain. SafeStageWX monitors outdoor events within the 50 U.S. states and U.S. territories.",
                "action": "Please configure a venue located within the United States or U.S. territories.",
                "active_alerts": [],
                "short_forecast": "Outside NWS Domain",
                "temperature": "--",
                "wind": "--",
                "cwa": "N/A",
            })

        # 3. Synthesize threats
        active_events = [f.get("properties", {}).get("event", "") for f in features if f.get("properties", {}).get("event")]
        short_fc = forecast_period.get("shortForecast", "") if forecast_period else ""
        detailed_fc = forecast_period.get("detailedForecast", "") if forecast_period else ""
        temp = f"{forecast_period.get('temperature', 85)}°{forecast_period.get('temperatureUnit', 'F')}" if forecast_period else "85°F"
        wind = forecast_period.get("windSpeed", "10 mph") if forecast_period else "10 mph"

        is_warning = any("Warning" in e for e in active_events)
        is_watch = any("Watch" in e for e in active_events)
        is_advisory = any("Advisory" in e or "Statement" in e for e in active_events)
        
        has_convective = any(k in short_fc.lower() or k in detailed_fc.lower() for k in ["thunderstorm", "storm", "lightning", "showers"])
        has_heat = any(k in short_fc.lower() or k in detailed_fc.lower() for k in ["heat", "100", "105", "110"])
        has_wind = any(k in short_fc.lower() or k in detailed_fc.lower() for k in ["wind", "gust", "breezy", "gale"])

        if is_warning:
            severity = "CRITICAL"
            icon = "warning"
            headline = f"Active NWS Warning: {active_events[0]}"
            desc = f"Official NWS {active_events[0]} directly affecting venue coordinates. {detailed_fc}"
            action = "Activate Emergency Action Plan immediately. Direct all attendees to permanent sturdy indoor shelter and halt outdoor performances."
        elif is_watch:
            severity = "HIGH"
            icon = "thunderstorm"
            headline = f"Active NWS Watch: {active_events[0]}"
            desc = f"A {active_events[0]} is active for the venue area. Atmosphere is favorable for severe weather development. {detailed_fc}"
            action = "Brief stage management, stagehands, and security. Stand by for immediate shelter broadcast if warning polygons trigger."
        elif has_convective:
            severity = "ELEVATED"
            icon = "bolt"
            headline = f"{short_fc} Expected Today"
            advisory_suffix = f" (Active NWS Advisory: {active_events[0]})" if is_advisory else ""
            desc = f"{detailed_fc}{advisory_suffix}"
            action = "Enforce 20-mile lightning shelter trigger (18-min lead time). Maintain continuous live Doppler radar monitoring and secure tent ballasts."
        elif is_advisory:
            severity = "ELEVATED"
            icon = "campaign"
            headline = f"Active NWS Advisory: {active_events[0]}"
            desc = f"NWS {active_events[0]} active for venue region. {detailed_fc}"
            action = "Review venue safety checklists. Monitor live Doppler radar and coastal weather updates."
        elif has_heat:
            severity = "ELEVATED"
            icon = "thermostat"
            headline = f"High Heat Index & Sun Exposure (High {temp})"
            desc = f"{detailed_fc}"
            action = "Provide free hydration refill stations, deploy misting fans, and stage EMS cooling cots for heat exhaustion mitigation."
        elif has_wind:
            severity = "ELEVATED"
            icon = "air"
            headline = f"Elevated Wind Conditions ({wind})"
            desc = f"{detailed_fc}"
            action = "Monitor stage anemometer continuously. Prepare to lower video walls at 30 mph and enforce 35 mph stage canopy cutoff."
        else:
            severity = "MONITORING"
            icon = "check_circle"
            headline = f"{short_fc or 'Clear Conditions'} (High {temp})"
            desc = f"{detailed_fc or 'No hazardous weather outlook active. Standard fair weather conditions expected.'}"
            action = "Maintain standard weather monitoring throughout event hours."

        return JSONResponse({
            "status": "success",
            "is_today": True,
            "severity": severity,
            "icon": icon,
            "headline": headline,
            "description": desc,
            "action": action,
            "active_alerts": active_events,
            "short_forecast": short_fc,
            "temperature": temp,
            "wind": wind,
            "cwa": cwa,
        })


# Serve the chat UI (keep this mount last so /chat wins).
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
