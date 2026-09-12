"""Synthetic dataset generator for ATLAS.

Generates an entirely synthetic "global events" dataset -- persons,
organizations, locations, events, relationships, and transactions -- at a
chosen scale, and writes each table to a CSV file under data/synthetic/.

This is not just a data generator: it also injects two kinds of *known*
ground truth so later phases can measure precision/recall rather than just
"looks plausible":

1. Near-duplicate person records (e.g. "Muhammad Ali" / "M. Ali") with a
   recorded true identity, for evaluating entity resolution (Phase 4/8).
2. A handful of extreme-outlier transaction amounts, for evaluating
   anomaly detection (Phase 5/8).

Usage (from the project root):

    python scripts/generate_data.py --size 1000
    python scripts/generate_data.py --size 10000
    python scripts/generate_data.py --size 100000

All identities, organizations, and events are synthetic. No real person or
organization is represented.
"""

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402

RELATIONSHIP_TYPES = ["KNOWS", "WORKS_FOR", "ASSOCIATED_WITH", "PARTICIPATED_IN"]
EVENT_TYPES = ["conference", "protest", "meeting", "transaction_event", "public_statement", "incident"]
ORG_TYPES = ["company", "ngo", "government", "university", "media"]

# Fraction of persons that get an injected near-duplicate record.
DUPLICATE_RATE = 0.05
# Fraction of transactions whose amount is replaced with an extreme outlier.
ANOMALY_RATE = 0.01


def new_id() -> str:
    return str(uuid.uuid4())


def make_alias_variant(name: str, rng: random.Random) -> str:
    """Produce a plausible near-duplicate spelling of a person's name.

    Used to create entity-resolution ground truth: two rows that a human
    (or a good algorithm) should recognize as referring to the same person,
    despite not being identical strings.
    """
    parts = name.split()
    variant_kind = rng.choice(["initial", "typo", "honorific", "middle_drop"])

    if variant_kind == "initial" and len(parts) >= 2:
        return f"{parts[0][0]}. {' '.join(parts[1:])}"
    if variant_kind == "honorific" and len(parts) >= 2:
        return f"{rng.choice(['Mr.', 'Dr.', 'Eng.'])} {name}"
    if variant_kind == "middle_drop" and len(parts) >= 3:
        return f"{parts[0]} {parts[-1]}"
    if variant_kind == "typo" and len(name) > 4:
        idx = rng.randint(1, len(name) - 2)
        return name[:idx] + name[idx + 1 :]
    return name.replace(" ", "  ", 1)  # fallback: double space, still a "near duplicate"


def generate_locations(fake: Faker, n: int) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        rows.append(
            {
                "location_id": new_id(),
                "city": fake.city(),
                "country": fake.country(),
                "latitude": float(fake.latitude()),
                "longitude": float(fake.longitude()),
            }
        )
    return pd.DataFrame(rows)


def generate_organizations(fake: Faker, n: int, rng: random.Random) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        rows.append(
            {
                "organization_id": new_id(),
                "name": fake.company(),
                "type": rng.choice(ORG_TYPES),
                "country": fake.country(),
            }
        )
    return pd.DataFrame(rows)


def generate_persons(
    fake: Faker, n: int, rng: random.Random, organization_ids: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate persons plus injected near-duplicates.

    Returns (persons_df, ground_truth_df). ground_truth_df maps every
    duplicate's person_id to the true_identity_id it was derived from,
    which is exactly the label an entity-resolution evaluation needs.
    """
    rows = []
    ground_truth_rows = []

    for _ in range(n):
        person_id = new_id()
        name = fake.name()
        rows.append(
            {
                "person_id": person_id,
                "name": name,
                "aliases": "",
                "organization_id": rng.choice(organization_ids) if organization_ids and rng.random() < 0.7 else "",
                "country": fake.country(),
                "city": fake.city(),
            }
        )

        if rng.random() < DUPLICATE_RATE:
            duplicate_id = new_id()
            duplicate_name = make_alias_variant(name, rng)
            base_row = rows[-1]
            rows.append(
                {
                    "person_id": duplicate_id,
                    "name": duplicate_name,
                    "aliases": name,
                    "organization_id": base_row["organization_id"],
                    "country": base_row["country"],
                    "city": base_row["city"],
                }
            )
            ground_truth_rows.append(
                {"person_id": duplicate_id, "true_identity_id": person_id, "true_identity_name": name}
            )

    return pd.DataFrame(rows), pd.DataFrame(ground_truth_rows)


EVENT_DESCRIPTION_TEMPLATES = [
    "{person} attended a {event_type} in {city} representing {org} on {date_str}.",
    "{org} confirmed that {person} took part in a {event_type} held in {city}.",
    "A {event_type} involving {person} and {org} took place in {city} on {date_str}.",
    "{person} issued a public statement regarding {org} following the {event_type} in {city}.",
    "Representatives from {org}, including {person}, met in {city} for a {event_type}.",
]


def generate_events(
    fake: Faker,
    n: int,
    rng: random.Random,
    location_ids: list[str],
    locations_df: pd.DataFrame,
    person_names: list[str],
    org_names: list[str],
) -> pd.DataFrame:
    """Generate events with descriptions that embed real person/org/location
    names, so the NLP entity-extraction module (Phase 6) has something to
    actually find -- a generic Faker sentence has no named entities in it.
    """
    city_by_location_id = dict(zip(locations_df["location_id"], locations_df["city"]))
    rows = []
    start = datetime(2015, 1, 1)
    for _ in range(n):
        location_id = rng.choice(location_ids) if location_ids else ""
        city = city_by_location_id.get(location_id) or fake.city()
        event_type = rng.choice(EVENT_TYPES)
        event_date = start + timedelta(days=rng.randint(0, 3650))
        template = rng.choice(EVENT_DESCRIPTION_TEMPLATES)
        description = template.format(
            person=rng.choice(person_names) if person_names else fake.name(),
            org=rng.choice(org_names) if org_names else fake.company(),
            event_type=event_type,
            city=city,
            date_str=event_date.strftime("%B %d, %Y"),
        )
        rows.append(
            {
                "event_id": new_id(),
                "event_type": event_type,
                "date": event_date.date().isoformat(),
                "location_id": location_id,
                "description": description,
            }
        )
    return pd.DataFrame(rows)


def generate_relationships(
    n: int, rng: random.Random, person_ids: list[str], organization_ids: list[str]
) -> pd.DataFrame:
    all_entities = person_ids + organization_ids
    rows = []
    start = datetime(2010, 1, 1)
    for _ in range(n):
        source, target = rng.sample(all_entities, 2) if len(all_entities) >= 2 else (all_entities[0], all_entities[0])
        start_date = start + timedelta(days=rng.randint(0, 5000))
        rows.append(
            {
                "relationship_id": new_id(),
                "source_entity": source,
                "target_entity": target,
                "relationship_type": rng.choice(RELATIONSHIP_TYPES),
                "start_date": start_date.date().isoformat(),
                "end_date": "",
                "confidence": round(rng.uniform(0.5, 1.0), 2),
            }
        )
    return pd.DataFrame(rows)


def generate_transactions(
    n: int, rng: random.Random, person_ids: list[str], organization_ids: list[str], location_ids: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate transactions plus a ground-truth list of injected anomalies."""
    all_entities = person_ids + organization_ids
    rows = []
    anomaly_rows = []
    start = datetime(2020, 1, 1)

    for _ in range(n):
        source, destination = (
            rng.sample(all_entities, 2) if len(all_entities) >= 2 else (all_entities[0], all_entities[0])
        )
        transaction_id = new_id()
        is_anomalous = rng.random() < ANOMALY_RATE
        amount = round(rng.uniform(50_000, 500_000), 2) if is_anomalous else round(rng.uniform(10, 5_000), 2)

        rows.append(
            {
                "transaction_id": transaction_id,
                "source": source,
                "destination": destination,
                "amount": amount,
                "timestamp": (start + timedelta(minutes=rng.randint(0, 3_000_000))).isoformat(),
                "location_id": rng.choice(location_ids) if location_ids else "",
            }
        )
        if is_anomalous:
            anomaly_rows.append({"transaction_id": transaction_id, "injected_reason": "extreme_amount_outlier"})

    return pd.DataFrame(rows), pd.DataFrame(anomaly_rows)


def generate_dataset(size: int, seed: int = 42) -> dict[str, pd.DataFrame]:
    """Generate one full synthetic dataset of the given target scale.

    `size` roughly controls the persons table; other tables scale
    proportionally so relationships/transactions/events stay meaningful
    relative to the number of entities.
    """
    fake = Faker()
    Faker.seed(seed)
    rng = random.Random(seed)

    n_locations = max(10, size // 20)
    n_organizations = max(5, size // 15)
    n_events = max(10, size // 10)
    n_relationships = size
    n_transactions = size

    locations_df = generate_locations(fake, n_locations)
    organizations_df = generate_organizations(fake, n_organizations, rng)
    persons_df, entity_resolution_gt_df = generate_persons(
        fake, size, rng, organizations_df["organization_id"].tolist()
    )
    events_df = generate_events(
        fake,
        n_events,
        rng,
        locations_df["location_id"].tolist(),
        locations_df,
        persons_df["name"].tolist(),
        organizations_df["name"].tolist(),
    )
    relationships_df = generate_relationships(
        n_relationships, rng, persons_df["person_id"].tolist(), organizations_df["organization_id"].tolist()
    )
    transactions_df, anomaly_gt_df = generate_transactions(
        n_transactions,
        rng,
        persons_df["person_id"].tolist(),
        organizations_df["organization_id"].tolist(),
        locations_df["location_id"].tolist(),
    )

    return {
        "locations": locations_df,
        "organizations": organizations_df,
        "persons": persons_df,
        "events": events_df,
        "relationships": relationships_df,
        "transactions": transactions_df,
        "ground_truth_entity_resolution": entity_resolution_gt_df,
        "ground_truth_anomalies": anomaly_gt_df,
    }


def save_dataset(tables: dict[str, pd.DataFrame], size: int, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for table_name, df in tables.items():
        path = output_dir / f"{table_name}_{size}.csv"
        df.to_csv(path, index=False)
        print(f"  wrote {len(df):>7,} rows -> {path.relative_to(PROJECT_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic ATLAS demo dataset.")
    parser.add_argument(
        "--size",
        type=int,
        default=1000,
        choices=[1000, 10000, 100000],
        help="Approximate number of person records to generate (default: 1000).",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    args = parser.parse_args()

    settings = get_settings()
    print(f"Generating synthetic dataset at scale={args.size} (seed={args.seed})...")
    tables = generate_dataset(args.size, args.seed)
    save_dataset(tables, args.size, settings.synthetic_data_dir)
    print("Done.")


if __name__ == "__main__":
    main()
