# My agent: Event Weather & Climate Safeguard

One-liner: A conversational agent housed in a mobile-responsive phone app UI that helps event planners identify weather threats and climate risks for an event given its date and location, providing tailored preparedness timelines from months out down to hourly day-of forecasts.

Tool coverage:
- Memory: Remembers the user's event date, event location, identified weather threats, and active alerts across sessions.
- Tools: Historical climatology lookup, NOAA/NWS climate outlook and forecast fetcher, severe weather alert monitor.
- Catalog/UI: Multi-horizon threat timeline card (Months -> Weeks -> Days -> Hours) and hourly forecast risk table with alert status, formatted for mobile screen sizes.
- Image gen: n/a
- Sandbox: Historical weather threat probability calculator (% risk of extreme heat, heavy rain, or high wind for the given date/location).

Core rails (everyone): memory, tools, eval, deploy, frontend (mobile-responsive UI)
My stretch menu (pick later): A2UI threat timeline cards, NOAA/NWS API integration, historical risk calculation in code sandbox, Progressive Web App (PWA) mobile layout.
First eval question: "I am hosting an outdoor event on November 12 in Denver, CO. What are the key weather threats for that date and what should I prepare for months in advance?"
