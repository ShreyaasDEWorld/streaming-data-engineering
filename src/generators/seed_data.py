
# src/generators/seed_data.py

import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from faker import Faker

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

fake = Faker()
Faker.seed(42)
random.seed(42)

DB = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": os.getenv("PGPORT", "5432"),
    "dbname": os.getenv("PGDATABASE", "streaming_platform"),
    "user": os.getenv("PGUSER"),
    "password": os.getenv("PGPASSWORD"),
}

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
START = datetime(2025, 1, 1, tzinfo=timezone.utc)


def random_date(start=START, end=NOW):
    """Generate a reproducible UTC timestamp."""
    seconds = int((end - start).total_seconds())
    return start + timedelta(seconds=random.randint(0, seconds))


def insert_many(cur, sql, rows):
    if rows:
        cur.executemany(sql, rows)


def main():
    if not DB["user"] or not DB["password"]:
        raise ValueError("Set PGUSER and PGPASSWORD in your .env file.")

    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:

            # This is a dedicated seed-data reset.
            # It deletes existing rows from these project tables.
            # Do not run against a database containing data you need.
            cur.execute("""
                TRUNCATE TABLE
                    ad_impressions,
                    support_tickets,
                    payments,
                    viewing_events,
                    devices,
                    content_genres,
                    genres,
                    content,
                    subscription_status_history,
                    subscriptions,
                    subscription_plans,
                    profiles,
                    customers
                RESTART IDENTITY CASCADE;
            """)

            # 1. Subscription plans
            plans = [
                (1, "Basic with Ads", 6.99, "USD", "HD", 1, True),
                (2, "Standard", 12.99, "USD", "Full HD", 2, False),
                (3, "Premium", 19.99, "USD", "4K", 4, False),
                (4, "Mobile", 4.99, "USD", "SD", 1, True),
                (5, "Family", 24.99, "USD", "4K", 5, False),
            ]
            insert_many(cur, """
                INSERT INTO subscription_plans
                    (plan_id, plan_name, monthly_price, currency,
                     video_quality, max_screens, has_ads)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, plans)

            # 2. Customers
            countries = ["US", "GB", "IN", "NO", "CA", "AU"]
            channels = ["Organic", "Social", "Referral", "Paid Search", "Partner"]
            customers = []

            for cid in range(1, 101):
                customers.append((
                    cid,
                    f"customer{cid}@example.com",
                    fake.name(),
                    random.choice(countries),
                    random.choice(channels),
                    random_date(),
                ))

            insert_many(cur, """
                INSERT INTO customers
                    (customer_id, email, full_name, country_code,
                     acquisition_channel, registered_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, customers)

            # 3. Profiles: one or two per customer
            profiles = []
            profile_to_customer = {}
            profile_id = 1

            for cid in range(1, 101):
                count = random.choice([1, 1, 1, 2])
                for number in range(count):
                    profiles.append((
                        profile_id,
                        cid,
                        "Main" if number == 0 else "Family",
                        random.randint(1970, 2015),
                        number == 1 and random.random() < 0.3,
                        random_date(),
                    ))
                    profile_to_customer[profile_id] = cid
                    profile_id += 1

            insert_many(cur, """
                INSERT INTO profiles
                    (profile_id, customer_id, profile_name, birth_year,
                     is_kids_profile, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, profiles)

            # 4. Subscriptions: one per customer
            subscriptions = []
            subscription_dates = {}
            status_history = []

            for sid, cid in enumerate(range(1, 101), start=1):
                started = random_date()
                plan_id = random.randint(1, 5)
                state = random.choices(
                    ["Active", "Paused", "Cancelled", "Expired"],
                    weights=[65, 10, 15, 10],
                    k=1,
                )[0]

                period_start = started
                period_end = started + timedelta(days=30)
                cancelled_at = (
                    random_date(started, NOW)
                    if state == "Cancelled" else None
                )

                subscriptions.append((
                    sid, cid, plan_id, started, None,
                    period_start, period_end, cancelled_at,
                ))
                subscription_dates[sid] = (started, cid, plan_id)

                # A small lifecycle history for each subscription
                status_history.append((
                    len(status_history) + 1,
                    sid,
                    "Active",
                    started,
                    f"seed-sub-{sid}-1",
                ))

                if state != "Active":
                    changed_at = started + timedelta(
                        days=random.randint(5, 60)
                    )
                    if changed_at <= NOW:
                        status_history.append((
                            len(status_history) + 1,
                            sid,
                            state,
                            changed_at,
                            f"seed-sub-{sid}-2",
                        ))

            insert_many(cur, """
                INSERT INTO subscriptions
                    (subscription_id, customer_id, plan_id, started_at,
                     trial_ends_at, current_period_start,
                     current_period_end, cancelled_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, subscriptions)

            insert_many(cur, """
                INSERT INTO subscription_status_history
                    (status_history_id, subscription_id, status,
                     status_date, source_event_id)
                VALUES (%s, %s, %s, %s, %s)
            """, status_history)

            # 5. Genres
            genre_names = [
                "Drama", "Comedy", "Action", "Documentary",
                "Thriller", "Animation", "Sci-Fi", "Family",
            ]
            insert_many(cur, """
                INSERT INTO genres (genre_id, genre_name)
                VALUES (%s, %s)
            """, [(i, name) for i, name in enumerate(genre_names, 1)])

            # 6. Content: movies, series, and episodes
            content_rows = []

            for content_id in range(1, 101):
                if content_id <= 60:
                    kind, parent_id = "Movie", None
                elif content_id <= 80:
                    kind, parent_id = "Series", None
                else:
                    kind = "Episode"
                    parent_id = random.randint(61, 80)

                content_rows.append((
                    content_id,
                    f"Stream Title {content_id:03d}",
                    kind,
                    parent_id,
                    random_date().date(),
                    random.randint(20, 180),
                    random.choice(["G", "PG", "PG-13", "TV-14", "TV-MA"]),
                    random.choice(["English", "Hindi", "Norwegian", "Spanish"]),
                    random.choice(["US", "IN", "GB", "NO"]),
                    True,
                ))

            insert_many(cur, """
                INSERT INTO content
                    (content_id, title, content_type, parent_content_id,
                     release_date, duration_minutes, age_rating,
                     original_language, country_of_origin, is_available)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, content_rows)

            content_genres = []
            for cid in range(1, 101):
                chosen = random.sample(range(1, 9), k=random.choice([1, 2, 3]))
                for gid in chosen:
                    content_genres.append((cid, gid))

            insert_many(cur, """
                INSERT INTO content_genres (content_id, genre_id)
                VALUES (%s, %s)
            """, content_genres)

            # 7. Devices: one per profile
            devices = []
            profile_to_device = {}

            for did, pid in enumerate(profile_to_customer, start=1):
                devices.append((
                    did,
                    pid,
                    random.choice(["Smart TV", "Mobile", "Tablet", "Web"]),
                    random.choice(["Android", "iOS", "Windows", "Tizen"]),
                    random_date(),
                ))
                profile_to_device[pid] = did

            insert_many(cur, """
                INSERT INTO devices
                    (device_id, profile_id, device_type,
                     device_os, registered_at)
                VALUES (%s, %s, %s, %s, %s)
            """, devices)

            # 8. Viewing events
            viewing = []
            event_types = ["Play", "Pause", "Resume", "Stop", "Complete", "Error"]

            for eid in range(1, 1001):
                pid = random.choice(list(profile_to_customer))
                cid = random.randint(1, 100)
                event_time = random_date()
                event_type = random.choices(
                    event_types,
                    weights=[40, 10, 10, 15, 23, 2],
                    k=1,
                )[0]
                duration = (
                    0 if event_type in ["Play", "Pause", "Resume", "Error"]
                    else random.randint(30, 7200)
                )

                viewing.append((
                    eid,
                    f"view-event-{eid}",
                    pid,
                    cid,
                    profile_to_device[pid],
                    event_type,
                    event_time,
                    duration,
                    event_time + timedelta(minutes=random.randint(0, 120)),
                ))

            insert_many(cur, """
                INSERT INTO viewing_events
                    (viewing_event_id, source_event_id, profile_id,
                     content_id, device_id, event_type, event_timestamp,
                     watch_duration_seconds, ingestion_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, viewing)

            # 9. Payments
            payments = []
            payment_statuses = ["Succeeded", "Succeeded", "Succeeded", "Failed", "Refunded"]

            for pid in range(1, 301):
                sid = random.randint(1, 100)
                plan_id = subscription_dates[sid][2]
                plan_price = plans[plan_id - 1][2]

                payments.append((
                    pid,
                    sid,
                    f"payment-ref-{pid}",
                    plan_price,
                    "USD",
                    random.choice(payment_statuses),
                    random.choice(["Card", "PayPal", "Wallet"]),
                    random_date(),
                    random_date(),
                ))

            insert_many(cur, """
                INSERT INTO payments
                    (payment_id, subscription_id, payment_reference,
                     amount, currency, payment_status, payment_method,
                     transaction_at, ingestion_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, payments)

            # 10. Ad impressions
            ads = []
            for aid in range(1, 301):
                pid = random.choice(list(profile_to_customer))
                ads.append((
                    aid,
                    pid,
                    random.randint(1, 100),
                    f"campaign-{random.randint(1, 20)}",
                    random_date(),
                    random.random() < 0.08,
                    round(random.uniform(0.001, 0.05), 4),
                ))

            insert_many(cur, """
                INSERT INTO ad_impressions
                    (impression_id, profile_id, content_id, campaign_id,
                     impression_timestamp, clicked, revenue)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, ads)

            # 11. Support tickets
            tickets = []
            for tid in range(1, 41):
                cid = random.randint(1, 100)
                created = random_date()
                resolved = (
                    created + timedelta(hours=random.randint(1, 96))
                    if random.random() < 0.7 else None
                )

                if resolved and resolved > NOW:
                    resolved = None

                tickets.append((
                    tid,
                    cid,
                    cid,  # one subscription per customer in this seed
                    random.choice([
                        "Billing", "Playback", "Account",
                        "Cancellation", "Technical",
                    ]),
                    random.choice(["Open", "In Progress", "Resolved", "Closed"]),
                    random.choice(["Low", "Medium", "High"]),
                    created,
                    resolved,
                ))

            insert_many(cur, """
                INSERT INTO support_tickets
                    (ticket_id, customer_id, subscription_id, issue_category,
                     ticket_status, priority, created_at, resolved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, tickets)

    print("Seed data generated successfully.")
    print("Customers: 100")
    print(f"Profiles: {len(profiles)}")
    print("Subscriptions: 100")
    print(f"Status history records: {len(status_history)}")
    print("Content items: 100")
    print(f"Viewing events: {len(viewing)}")
    print(f"Payments: {len(payments)}")
    print(f"Ad impressions: {len(ads)}")
    print(f"Support tickets: {len(tickets)}")


if __name__ == "__main__":
    main()
