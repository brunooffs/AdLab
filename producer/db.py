# ─────────────────────────────────────────────────────────────────────────────
#  db.py — PostgreSQL connection and ad catalogue loader
#  Fetches real advertisers and campaigns so the producer
#  generates events that reference actual data in the DB.
# ─────────────────────────────────────────────────────────────────────────────

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://lab:labpass@localhost:5432/adlab"
)


def get_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def load_ad_catalogue() -> list[dict]:
    """
    Returns a list of active ads built from real Advertiser + Campaign
    rows in PostgreSQL.

    Each entry looks like:
    {
        "ad_id":         "ad_<campaign_id_short>_001",
        "advertiser_id": "clxyz...",
        "campaign_id":   "clxyz...",
        "ad_type":       "banner",
        "market":        "PT",
    }

    If no campaigns exist yet the function seeds the DB with
    sample data so the producer always has something to work with.
    """
    engine = get_engine()

    with Session(engine) as session:
        rows = session.execute(text("""
            SELECT
                a.id          AS advertiser_id,
                a.name        AS advertiser_name,
                a.tier        AS tier,
                c.id          AS campaign_id,
                c.name        AS campaign_name,
                c.status      AS status
            FROM "Advertiser" a
            JOIN "Campaign"   c ON c."advertiserId" = a.id
            WHERE c.status = 'ACTIVE'
            ORDER BY a.id, c.id
        """)).fetchall()

        if not rows:
            print("No active campaigns found — seeding sample data...")
            _seed_sample_data(session)
            session.commit()
            # Re-fetch after seed
            rows = session.execute(text("""
                SELECT
                    a.id          AS advertiser_id,
                    a.name        AS advertiser_name,
                    a.tier        AS tier,
                    c.id          AS campaign_id,
                    c.name        AS campaign_name,
                    c.status      AS status
                FROM "Advertiser" a
                JOIN "Campaign"   c ON c."advertiserId" = a.id
                WHERE c.status = 'ACTIVE'
                ORDER BY a.id, c.id
            """)).fetchall()

    ad_types = ["banner", "video", "native", "search"]
    markets   = ["PT", "ES", "DE", "FR", "GB", "US"]

    catalogue = []
    for i, row in enumerate(rows):
        # Generate 3 ads per campaign to give the producer variety
        for j in range(1, 4):
            catalogue.append({
                "ad_id":          f"ad_{row.campaign_id[:8]}_{j:03d}",
                "advertiser_id":  row.advertiser_id,
                "campaign_id":    row.campaign_id,
                "advertiser_name": row.advertiser_name,
                "ad_type":        ad_types[(i + j) % len(ad_types)],
                "market":         markets[(i + j) % len(markets)],
                "tier":           row.tier,
            })

    print(f"Loaded {len(catalogue)} ads from {len(rows)} active campaigns")
    return catalogue


def _seed_sample_data(session: Session):
    """
    Seeds the DB with 3 advertisers and 2 campaigns each
    so the producer works even on a fresh install.
    Uses raw SQL to avoid Prisma dependency in Python.
    """
    from datetime import datetime, timezone

    advertisers = [
        ("clab0001", "Acme Corp",      "PREMIUM"),
        ("clab0002", "Bruno Labs",      "PREMIUM"),
        ("clab0003", "StartupXYZ",     "STANDARD"),
    ]

    campaigns = [
        ("clcp0001", "clab0001", "Summer Campaign 2026",   50000.0),
        ("clcp0002", "clab0001", "Black Friday 2026",      120000.0),
        ("clcp0003", "clab0002", "Product Launch Q2",      75000.0),
        ("clcp0004", "clab0002", "Brand Awareness",        30000.0),
        ("clcp0005", "clab0003", "Growth Hack Jan",        10000.0),
        ("clcp0006", "clab0003", "Retargeting Q1",         8000.0),
    ]

    now = datetime.now(timezone.utc)

    for adv_id, name, tier in advertisers:
        session.execute(text("""
            INSERT INTO "Advertiser" (id, name, email, tier, "createdAt", "updatedAt")
            VALUES (:id, :name, :email, :tier, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": adv_id, "name": name,
            "email": f"{name.lower().replace(' ', '')}@lab.com",
            "tier": tier, "now": now
        })

    for camp_id, adv_id, name, budget in campaigns:
        session.execute(text("""
            INSERT INTO "Campaign"
                (id, name, "advertiserId", budget, status,
                 "startDate", "createdAt", "updatedAt")
            VALUES
                (:id, :name, :adv_id, :budget, 'ACTIVE',
                 :now, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": camp_id, "name": name, "adv_id": adv_id,
            "budget": budget, "now": now
        })

    print(f"Seeded {len(advertisers)} advertisers and {len(campaigns)} campaigns")
