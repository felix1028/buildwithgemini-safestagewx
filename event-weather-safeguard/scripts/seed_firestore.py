"""Seed script for Firestore events collection."""

import datetime
from google.cloud import firestore

# Hardcoded project ID as string for Firestore client
PROJECT_ID = "qwiklabs-gcp-04-72024f788a4d"


def seed_events():
    """Seeds sample event records into the Firestore 'events' collection."""
    print(f"Connecting to Firestore with project={PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    events_ref = db.collection("events")

    seeded_items = [
        {
            "event_name": "Austin Summer Music Festival",
            "location": "Austin, TX",
            "event_date": "2026-10-15",
            "event_type": "Music Festival",
            "attendee_count": 2500,
            "weather_threats": ["Extreme Heat", "Flash Floods", "High UV"],
            "prep_status": "Misting stations planned, backup indoor stage reserved",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        {
            "event_name": "Miami Beach Coastal Wedding",
            "location": "Miami, FL",
            "event_date": "2026-12-01",
            "event_type": "Outdoor Wedding",
            "attendee_count": 150,
            "weather_threats": ["Passing Showers", "Coastal Winds"],
            "prep_status": "Clear-span tent on standby, parasols provided",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        {
            "event_name": "Denver July 4th Fireworks & Concert",
            "location": "Denver, CO",
            "event_date": "2026-07-04",
            "event_type": "Outdoor Concert",
            "attendee_count": 5000,
            "weather_threats": ["High Altitude Sun", "Late Afternoon Lightning", "Microburst Winds"],
            "prep_status": "Lightning monitoring system active, gear shading installed",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    ]

    for item in seeded_items:
        doc_id = f"{item['location'].lower().replace(', ', '_').replace(' ', '_')}_{item['event_date']}"
        events_ref.document(doc_id).set(item)
        print(f"✅ Seeded event: {doc_id} -> {item['event_name']}")


if __name__ == "__main__":
    seed_events()
