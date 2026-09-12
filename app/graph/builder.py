"""Graph construction: turn a dataset's relational rows into a NetworkX graph.

Design decision (documented in docs/defense_questions.md): the relational
schema only gives us a handful of *real* structural links between
entities -- it does not, for example, tell us that a person attended an
event. Rather than inventing edges that aren't backed by data, the graph
only contains edges that map directly onto a foreign key or a row in
`relationships`/`transactions`:

  - Person --WORKS_FOR--> Organization        (persons.organization_id)
  - Event  --OCCURRED_AT--> Location          (events.location_id)
  - <source> --<relationship_type>--> <target> (one row per `relationships` entry)
  - <source> --TRANSFERRED_TO--> <destination> (one row per `transactions` entry)

Node types (Person / Organization / Location / Event) and edge types match
the vocabulary in docs/architecture.md and the original project brief.
"""

import networkx as nx
from sqlalchemy.orm import Session

from app.database.models import Event, Location, Organization, Person, RelationshipEdge, Transaction


def build_graph_for_dataset(session: Session, dataset_id: str) -> nx.MultiDiGraph:
    """Build a directed multigraph (multiple edge types between the same
    pair of nodes are allowed) for every entity/relationship/transaction
    belonging to `dataset_id`.
    """
    graph = nx.MultiDiGraph()

    persons = session.query(Person).filter(Person.dataset_id == dataset_id).all()
    organizations = session.query(Organization).filter(Organization.dataset_id == dataset_id).all()
    locations = session.query(Location).filter(Location.dataset_id == dataset_id).all()
    events = session.query(Event).filter(Event.dataset_id == dataset_id).all()
    relationships = session.query(RelationshipEdge).filter(RelationshipEdge.dataset_id == dataset_id).all()
    transactions = session.query(Transaction).filter(Transaction.dataset_id == dataset_id).all()

    for person in persons:
        graph.add_node(
            person.person_id,
            node_type="Person",
            label=person.name,
            country=person.country,
            city=person.city,
            aliases=person.aliases,
        )
    for org in organizations:
        graph.add_node(
            org.organization_id,
            node_type="Organization",
            label=org.name,
            org_type=org.type,
            country=org.country,
        )
    for location in locations:
        graph.add_node(
            location.location_id,
            node_type="Location",
            label=f"{location.city or '?'}, {location.country or '?'}",
            latitude=location.latitude,
            longitude=location.longitude,
        )
    for event in events:
        graph.add_node(
            event.event_id,
            node_type="Event",
            label=event.event_type,
            date=str(event.date) if event.date else None,
            description=event.description,
        )

    for person in persons:
        if person.organization_id and graph.has_node(person.organization_id):
            graph.add_edge(person.person_id, person.organization_id, edge_type="WORKS_FOR", weight=1.0)

    for event in events:
        if event.location_id and graph.has_node(event.location_id):
            graph.add_edge(event.event_id, event.location_id, edge_type="OCCURRED_AT", weight=1.0)

    for rel in relationships:
        if graph.has_node(rel.source_entity) and graph.has_node(rel.target_entity):
            graph.add_edge(
                rel.source_entity,
                rel.target_entity,
                edge_type=rel.relationship_type,
                confidence=rel.confidence,
                start_date=str(rel.start_date) if rel.start_date else None,
                end_date=str(rel.end_date) if rel.end_date else None,
                weight=rel.confidence or 1.0,
            )

    for txn in transactions:
        if graph.has_node(txn.source) and graph.has_node(txn.destination):
            graph.add_edge(
                txn.source,
                txn.destination,
                edge_type="TRANSFERRED_TO",
                amount=txn.amount,
                timestamp=str(txn.timestamp) if txn.timestamp else None,
                weight=1.0,
            )

    return graph
