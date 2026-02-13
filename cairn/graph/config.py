"""Neo4j configuration."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "cairn-dev-password"
    database: str = "neo4j"


def load_neo4j_config() -> Neo4jConfig:
    """Load Neo4j config from environment variables."""
    return Neo4jConfig(
        uri=os.getenv("CAIRN_NEO4J_URI", "bolt://localhost:7687"),
        user=os.getenv("CAIRN_NEO4J_USER", "neo4j"),
        password=os.getenv("CAIRN_NEO4J_PASSWORD", "cairn-dev-password"),
        database=os.getenv("CAIRN_NEO4J_DATABASE", "neo4j"),
    )
