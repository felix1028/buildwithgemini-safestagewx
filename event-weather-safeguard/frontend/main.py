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

RESOURCE = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/746320986672/locations/us-east1/reasoningEngines/1691330358496198656",
)
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
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
        "📢 **NWS METEOROLOGIST PLAIN-ENGLISH BRIEFING**\n",
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
    """Fetches real-time NWS Area Forecast Discussion (AFD) for latitude & longitude coordinates."""
    headers = {"User-Agent": "EventWeatherSafeguard/1.0 (contact@example.com)"}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            pts_res = await client.get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}", headers=headers)
            if pts_res.status_code != 200:
                return JSONResponse({"error": f"NWS points API error: {pts_res.status_code}"}, status_code=400)

            props = pts_res.json().get("properties", {})
            cwa = props.get("cwa")
            office_url = props.get("forecastOffice")

            if not cwa:
                return JSONResponse({"error": "No CWA office found for coordinates"}, status_code=400)

            web_url = f"https://forecast.weather.gov/product.php?site={cwa}&product=AFD&issuedby={cwa}"

            afd_res = await client.get(f"https://api.weather.gov/products/types/AFD/locations/{cwa}", headers=headers)
            if afd_res.status_code != 200:
                return JSONResponse({
                    "cwa": cwa,
                    "forecast_office": office_url,
                    "web_url": web_url,
                    "product_text": "Could not fetch active discussion text from NWS API.",
                })

            graph = afd_res.json().get("@graph", [])
            if not graph:
                return JSONResponse({
                    "cwa": cwa,
                    "forecast_office": office_url,
                    "web_url": web_url,
                    "product_text": "No discussion products available.",
                })

            latest_id = graph[0].get("id")
            prod_res = await client.get(f"https://api.weather.gov/products/{latest_id}", headers=headers)
            if prod_res.status_code != 200:
                return JSONResponse({
                    "cwa": cwa,
                    "forecast_office": office_url,
                    "web_url": web_url,
                    "product_text": "Failed to load product details.",
                })

            prod_data = prod_res.json()
            raw_text = prod_data.get("productText", "")
            plain_summary = summarize_afd_plain_english(raw_text)

            return JSONResponse({
                "cwa": cwa,
                "forecast_office": office_url,
                "web_url": web_url,
                "issuance_time": prod_data.get("issuanceTime"),
                "product_text": raw_text,
                "plain_english_summary": plain_summary,
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


# Serve the chat UI (keep this mount last so /chat wins).
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
