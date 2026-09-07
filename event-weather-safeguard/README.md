# 🛡️ SafeStageWX: Event Weather & Climate Safeguard

> **An enterprise-grade, mobile-responsive event safety platform and AI assistant that protects outdoor events (concerts, festivals, athletic events) by combining live NWS warning polygons, SPC mesoscale discussions, interactive weather radar, automated evacuation decision math, and conversational AI safety grounding.**
>
> 🇺🇸 **United States & National Weather Service (NWS) Scope**: SafeStageWX is built exclusively for outdoor venues located within the 50 U.S. states and U.S. territories (Puerto Rico, U.S. Virgin Islands, Guam, American Samoa, Northern Mariana Islands). All meteorological intelligence—including live Doppler radar sweeps, active warning polygons, convective mesoscale discussions, and Area Forecast Discussions (AFDs)—is sourced directly from NOAA and the National Weather Service.

---

<div align="center">

![SafeStageWX Demo](demo.gif)

*Live SafeStageWX Demo: Real-time Threat Monitoring, NWS Point Forecasts, Egress Decision Parameter Imports, and Omni Video Generation.*

</div>

---

## 📋 Overview & Problem Statement

Outdoor venue operators, event directors, and emergency managers face severe weather hazards—including convective lightning, damaging wind gusts, extreme heat, and severe thunderstorms. **SafeStageWX** eliminates guesswork by fusing real-time National Weather Service (NWS) & Storm Prediction Center (SPC) data with deterministic evacuation math and a conversational Gemini 2.5 AI Safety Assistant.

### Key Capabilities:
- 🇺🇸 **U.S. & NWS Jurisdiction Enforcement**: Geocoding validation restricts venue setup exclusively to addresses within the 50 U.S. states and U.S. territories supported by NOAA National Weather Service Weather Forecast Offices (WFOs).
- 🌩️ **Live Threat Monitor & Warning Polygons**: Real-time NWS alerts, interactive RainViewer 480px weather radar overlay, and dynamic Call-to-Action safety banners tailored to active warning types (e.g. hydration for heat, sturdy shelter for lightning/wind).
- 🗓️ **Long-Term Climatological Risk Engine (> 7 Days Out)**: 15-year empirical climate baselines, P10/P50/P90 temperature envelopes, annual climate ribbon positioning, and NOAA CPC ENSO (El Niño / La Niña) teleconnections for far-advance event planning.
- ⚡ **Dynamic Date Horizon Adaptation**: Automatically switches UI modes, navigation tabs, and AI assistant behavior between *Long-Term Climatology* (> 7 days), *7-Day Forecast Window* (1–7 days), and *Tactical Event Day* (Today / 0 days).
- 🚨 **Real-Time Operational Threat Monitoring (Today)**: Real-time synthesis of active NWS warnings, point forecasts, and CWA forecast discussions into immediate crowd safety protocols.
- 🤖 **Gemini 2.5 Safety Assistant**: Deployed on Vertex AI Agent Engine with A2UI rich card rendering for date-specific NWS point forecasts, 15-year climatology baselines, SPC mesoscale discussions, and custom Emergency Action Plans (EAP).
- ⏱️ **Evacuation & Sheltering Decision Tool**: Official 3-step decision math ($TET = \text{Alert Time} + \text{Walk Time} + 25\% \text{Safety Cushion}$) vs. storm vector speeds to calculate trigger distances and act deadlines.
- 📥 **1-Tap Egress Parameter Import**: Direct import of calculated evacuation parameters into the AI Assistant context thread for downstream decision support.
- 📢 **PA Script Broadcast Generator**: Pre-approved stadium announcements for instant lightning, high-wind stage shutdown, or general weather advisories.
- 🎬 **Omni Video Advisory Generation**: Generates short safety advisory videos using `gemini-omni-flash-preview` and uploads them to public Cloud Storage.

---

## ☁️ Google Cloud Tools & Architecture

SafeStageWX leverages the full Google Cloud & Vertex AI Agent Development Kit (ADK) stack:

| Google Cloud Tool | Integration & Usage |
|---|---|
| 🧠 **Vertex AI Memory Bank** | Remembers cross-session venue preferences, default addresses, and structural wind threshold rules across conversations. |
| 🗄️ **Google Cloud Firestore** | Persists event profiles (`manage_event_details_firestore`), attendee counts, venue coordinates, and calculated safety plans. |
| 🖼️ **Google Cloud Storage (GCS)** | Direct in-memory byte upload for generated video advisories (`qwiklabs-gcp-04-72024f788a4d-static-assets-bucket`) returning public HTTPS URLs. |
| 📖 **Vertex AI RAG Engine** | Grounds safety advice on venue structural wind load standards, NWS evacuation guidelines, and stadium crowd management protocols. |
| 🎨 **Media Generation (Gemini Omni & Imagen 3)** | Utilizes `gemini-omni-flash-preview` in the global region for video advisory synthesis (`generate_event_safety_video`) and Imagen 3 for visual safety cards. |
| 🪟 **A2UI (Agent-to-User Interface)** | Renders rich, interactive UI display cards (weather summaries, structural risk profiles, EAP summaries) directly inside the chat stream. |
| 🌐 **Google Cloud Run** | Hosts the containerized FastAPI proxy and mobile-first glassmorphism web interface (`event-weather-safeguard-frontend`). |

---

## 🏛️ Application Architecture & Navigation

### 1️⃣ **Tab 1: Climatological Summary & Threat Monitor**
- **Dynamic Horizon Switching**: Automatically toggles between **Climatological Summary** (for events scheduled $>7$ days away) and **Threat Monitor** (within the 7-day NWS forecast window or on event day).
- **Climatological Mode (> 7 Days)**:
  - **Annual Temperature Ribbon Chart**: 12-month climate distribution with the target event date pinpointed.
  - **15-Year Percentile Bell Curves**: 10th percentile, median, and 90th percentile daily high and low temperatures.
  - **NOAA CPC ENSO Indicator**: Real-time ENSO phase tracking (El Niño / La Niña / Neutral) with regional teleconnections.
  - **Precipitation Odds & Structural Wind Frequencies**: Rain day probabilities, downpour odds, and ANSI E1.21 25 mph / 35 mph gust exceedance frequencies.
  - **Site Safeguards Checklist**: Categorized operational mitigations for temporary flooring, heat exhaustion, and stage ballasting.
- **Threat Monitor Mode (≤ 7 Days)**:
  - **Dynamic Call to Action Banner**: Automatically recommends safety actions based on active NWS warning polygons.
  - **Interactive Radar Map**: 480px RainViewer radar centered on venue coordinates with a gold location star badge overlay.
  - **Action Cards**: Live polygon status indicators and calculated Lead Time to Shelter.

### 2️⃣ **Tab 2: AI Assistant**
- **Dynamic Date-Horizon Orientation**: Welcome message, status badge, input placeholder, and 4 quick sample questions automatically adapt to whether the event is months away (15-yr climatology & ENSO), within 7 days (NWS point forecasts & SPC outlooks), or today (tactical live radar & warning polygons).
- **Conversational Safety Loop**: Powered by Gemini 2.5 on Vertex AI Reasoning Engine (`reasoningEngines/1691330358496198656`).
- **A2UI Rich Renderer**: Native rendering of flat A2UI cards for weather summaries, risk profiles, and safety plans.
- **Custom Tools**:
  - `get_climatological_risk_profile`: 15-year empirical climate baselines, percentile ranges, annual ribbon positioning, and NOAA ENSO teleconnections for events > 7 days out.
  - `get_nws_point_forecast`: Date-specific 7-day NWS point forecasts.
  - `get_nws_active_alerts`: Live severe weather watches, warnings, and advisories.
  - `spc_mesoscale_discussions`: NOAA SPC technical severe weather boundary analysis.
  - `calculate_coordinates_and_address`: Geocoding via Nominatim.
  - `manage_event_details_firestore`: Event profile persistence in Cloud Firestore.
  - `generate_event_safety_video`: Omni video generation with GCS upload and artifact saving.

### 3️⃣ **Tab 3: Safety Tools & Config**
- **Venue Reference Map**: Interactive map with venue location star pin and primary sturdy shelter rules.
- **Warning Radius Selector**: Buffer monitoring zone toggle (10 / 20 / 30 miles).
- **Evacuation Decision Math**:
  $$\text{Total Evacuation Time (TET)} = (\text{Alert Time} + \text{Walk Time}) \times 1.25$$
  Calculates Time Until Arrival (TUA), Trigger Distance, and Decision Deadline (Act Time).
- **Import to AI Assistant**: Button to inject parameters straight into the chat assistant.
- **PA Broadcast Generator**: Ready-to-read stadium scripts with 1-tap copy functionality.

---

## 🧪 Evaluation Benchmark

**Eval Query:**
> *"I am hosting an outdoor event on August 13 at 501 Wilmington Island Road, Savannah, GA with 100 guests. Check active warning polygons, calculate evacuation decision trigger distances for 40 MPH convective storms, and provide recommended safety actions."*

---

## 🛠️ Languages & Technologies Used

### 💻 Programming Languages
*   **Python**: Core agent backend reasoning loops (`app/agent.py`), database seeding (`scripts/seed_firestore.py`), and FastAPI proxy (`frontend/main.py`).
*   **JavaScript (ES6)**: Tab switching, interactive maps, and card rendering logic in the frontend (`frontend/static/app.js`).
*   **HTML5 & CSS3**: Glassmorphism dashboard interface.

### 🛠️ Frameworks & Core Libraries
*   **FastAPI**: Runs both the frontend proxy and the agent backend.
*   **Google Agent Development Kit (ADK)**: Scaffolds the agent backend, system prompts, memory, and tools.
*   **`a2a-sdk` (Agent-to-Agent)**: Transmits messages and rendering events.
*   **`a2ui-agent-sdk`**: Handles defining and serializing rich, interactive card component structures.
*   **Uvicorn & uv**: Server runtime and dependency package management.

### ☁️ Google Cloud & AI Platform
*   **Vertex AI**: Hosts core models (`gemini-3.6-flash` and `gemini-omni-flash-preview` for safety video generation).
*   **Cloud Run**: Serves the containerized frontend and backend microservices.
*   **Cloud Firestore**: Serverless database for saving safety profiles.
*   **Cloud Storage (GCS)**: Public blob storage hosting generated video advisories.
*   **Cloud Build & Artifact Registry**: Container build and hosting pipeline.

### 🌍 Third-Party APIs
*   **National Weather Service (NWS) API**: Real-time severe weather alert monitoring.
*   **Nominatim**: Geocoding address strings to coordinates.
*   **Leaflet.js & RainViewer Map**: Renders live weather radar overlay.

---

## 🚀 Live Links & Resources

- 🌐 **Live Web Application**: [https://safestagewx-frontend-1066893422734.us-central1.run.app](https://safestagewx-frontend-1066893422734.us-central1.run.app)
- 🐙 **GitHub Repository**: [https://github.com/felix1028/buildwithgemini-safestagewx](https://github.com/felix1028/buildwithgemini-safestagewx)
- 🎥 **Demo Recording Video**: [demo_video.webm](demo_video.webm) | [demo.gif](demo.gif)

---

## 📄 License & Intellectual Property

Copyright © 2026 Felix Scott (felix1028). All Rights Reserved.

This project is licensed under a **Proprietary / Source-Available License**. 
- **Permitted**: Public viewing, cloning, and local execution for personal evaluation, peer review, academic study, and hackathon judging (including the Google Cloud / Build with Gemini Challenge).
- **Prohibited**: Unauthorized commercial exploitation, redistribution, hosting as a commercial Software-as-a-Service (SaaS), sublicensing, or creating closed-source derivative products without explicit written authorization from the copyright holder.
- **Safety Advisory**: Provided "AS IS" without warranty. SafeStageWX is an advisory decision-support system and does not replace official National Weather Service (NWS) directives or local emergency management commands.

See the full [LICENSE](LICENSE) file for complete terms and liability disclaimers.
