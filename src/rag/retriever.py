from typing import Any

from neo4j import Driver, Session
from sentence_transformers import SentenceTransformer

from config import load_config
from utils import get_logger


class KnowledgeRetriever:
    def __init__(self, driver: Driver, model: SentenceTransformer) -> None:
        self.driver = driver
        self.model = model
        self.config = load_config()
        self.logger = get_logger(__name__)

    def find_similar_content(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Find similar content using vector similarity."""
        embedding = self.model.encode(query).tolist()

        with self.driver.session() as session:
            return self._query_vector_index(session, embedding, limit)

    def _query_vector_index(self, session: Session, embedding: list[float], limit: int) -> list[dict[str, Any]]:
        result = session.run(
            """
            CALL db.index.vector.queryNodes($index_name, $limit, $embedding)
            YIELD node, score
            RETURN node.content as content, score
            """,
            {
                "index_name": self.config["knowledge_base"]["indexes"][0]["name"],
                "limit": limit,
                "embedding": embedding,
            },
        )
        return [{"content": record["content"], "score": record["score"]} for record in result]

    def find_related_concepts(self, tag: str) -> list[dict[str, Any]]:
        """Find concepts related to a specific tag."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (t:Tag {name: $tag})<-[:TAGGED]-(b:Block)-[:SIMILAR]->(related:Block)
                RETURN related.content as content,
                       collect(distinct related.tags) as related_tags,
                       count(*) as relevance
                ORDER BY relevance DESC
                LIMIT 10
                """,
                {"tag": tag},
            )
            return [dict(record) for record in result]

    def explore_knowledge_graph(self, start_content: str, max_depth: int = 2) -> list[dict[str, Any]]:
        """Explore the knowledge graph starting from a piece of content."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH path = (start:Block {content: $content})-[:SIMILAR|TAGGED*1..$depth]-(related:Block)
                RETURN related.content as content,
                       [r in relationships(path) | type(r)] as connection_types,
                       length(path) as distance
                ORDER BY distance
                """,
                {"content": start_content, "depth": max_depth},
            )
            return [dict(record) for record in result]

    def semantic_search(self, query: str, with_tags: list[str] | None = None, limit: int = 5) -> list[dict[str, Any]]:
        """Combine vector similarity with tag filtering."""
        embedding = self.model.encode(query).tolist()

        with self.driver.session() as session:
            query = """
            CALL db.index.vector.queryNodes($index_name, $limit, $embedding)
            YIELD node, score
            """

            if with_tags:
                query += """
                WITH node, score
                MATCH (node)-[:TAGGED]->(t:Tag)
                WHERE t.name IN $tags
                """

            query += """
            RETURN node.content as content,
                   score,
                   collect(distinct t.name) as tags
            ORDER BY score DESC
            """

            result = session.run(
                query,
                {
                    "index_name": self.config["knowledge_base"]["indexes"][0]["name"],
                    "embedding": embedding,
                    "limit": limit,
                    "tags": with_tags or [],
                },
            )
            return [dict(record) for record in result]
