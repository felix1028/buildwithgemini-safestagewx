# SafeStageWX: Event Weather & Climate Safeguard

**One-liner:** An enterprise-grade, mobile-responsive event safety platform and AI assistant that protects outdoor events (concerts, festivals, athletic events) by combining live NWS warning polygons, SPC mesoscale discussions, interactive weather radar, automated evacuation decision math, and conversational AI safety grounding.

---

## 🏛️ Application Architecture & Tab Navigation

### **Tab 1: Threat Monitor**
- **Dynamic Call to Action Banner**: Real-time NWS warning polygon status with automated event safety action recommendations (e.g. hydration stations & shade for extreme heat warnings; sturdy indoor evacuation for severe thunderstorm warnings).
- **Live Weather Radar Map**: 480px interactive RainViewer radar overlay centered on venue coordinates with a floating location star pin badge.
- **Action Cards**: Active warning polygon status indicator and dynamic Lead Time to Shelter display.

### **Tab 2: AI Assistant**
- **Conversational Intelligence**: Powered by Gemini 2.5 deployed on Vertex AI Agent Engine (`reasoningEngines/1691330358496198656`).
- **A2UI Rich Card Rendering**: Renders flat A2UI cards for weather summaries, structural risk profiles, and Emergency Action Plans (EAP).
- **Custom Function Tools**:
  - `get_nws_point_forecast`: Date-specific 7-day NWS point forecasts.
  - `get_nws_active_alerts`: Real-time severe weather watches, warnings, and advisories.
  - `spc_mesoscale_discussions`: NOAA SPC technical severe weather boundary analysis translated into crowd safety actions.
  - `calculate_coordinates_and_address`: Geocoding via OpenStreetMap Nominatim.
  - `manage_event_details_firestore`: Event profile persistence in Google Cloud Firestore.
- **Quick Prompt Chips**: 1-tap quick action queries for instant radar/alert analysis.

### **Tab 3: Safety Tools & Config**
- **Venue Location & Map**: High-resolution OpenStreetMap venue reference card with primary sturdy shelter rules.
- **Warning Radius Buffer Selector**: Dynamic monitoring zone toggle (10 / 20 / 30 miles) for severe convective storms.
- **Safety Threshold Summary**: Max safe speed limit display (35 MPH gusts) and active warning buffer status.
- **Evacuation & Sheltering Decision Tool**:
  - Official 3-step egress decision math: **Alert Time + Physical Evac Walk Time + 25% Safety Cushion vs. Storm Vector Speed**.
  - Calculates Total Evacuation Time (TET), Time Until Arrival (TUA), Trigger Distance, and Decision Deadline (Act Time).
  - Includes a **"📥 Import Decision Parameters into AI Assistant"** button that posts exact egress parameters into the AI Assistant context thread.
  - Includes an interactive NWS Storm Speed vs. Trigger Distance matrix lookup table.
- **PA Script Broadcast Generator**: Pre-approved fill-in-the-blank statements for instant stadium/venue announcements (Lightning Evacuation, High Wind Stage Shutdown, General Weather Advisory).

---

## 🛠️ Tool & Infrastructure Summary

- **Core Framework**: Agent Development Kit (ADK) & Agent Runtime (Vertex AI Reasoning Engine).
- **Frontend / Proxy**: Mobile-first glassmorphism HTML/CSS/JS UI served via FastAPI proxy over A2A protocol.
- **Memory & Persistence**: Vertex AI Memory Bank + Cloud Firestore for cross-session venue coordinates, structural wind load ratings, and event profiles.
- **Deployment & Hosting**: Google Cloud Run (`event-weather-safeguard-frontend`), GitHub repository (`felix1028/buildwithgemini-safestagewx`).

---

## 🧪 Core Evaluation Benchmark
**Eval Benchmark Query:**
> *"I am hosting an outdoor event on August 13 at 501 Wilmington Island Road, Savannah, GA with 100 guests. Check active warning polygons, calculate evacuation decision trigger distances for 40 MPH convective storms, and provide recommended safety actions."*
