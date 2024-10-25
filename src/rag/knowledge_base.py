import re
from dataclasses import dataclass
from tqdm import tqdm
from pathlib import Path
import time
from neo4j import Driver, GraphDatabase, Session
from sentence_transformers import SentenceTransformer

from config import load_config
from utils import get_logger


@dataclass
class Block:
    content: str
    level: int
    tags: list[str]
    embedding: list[float] | None = None


class KnowledgeBaseProcessor:
    def __init__(self) -> None:
        self.config = load_config()
        self.logger = get_logger(__name__)

        # Initialize embedding model
        model_name = self.config["knowledge_base"]["embedding"]["model"]
        self.model = SentenceTransformer(model_name)
        self.similarity_threshold = self.config["knowledge_base"]["embedding"]["similarity_threshold"]

        # Initialize Neo4j connection
        neo4j_config = self.config["knowledge_base"]["neo4j"]
        self.driver: Driver = GraphDatabase.driver(
            neo4j_config["uri"],
            auth=(neo4j_config["user"], neo4j_config["password"]),
        )

    def __del__(self) -> None:
        """Cleanup Neo4j connection."""
        if hasattr(self, "driver"):
            self.driver.close()

    def _setup_database(self) -> None:
        with self.driver.session() as session:
            # Create constraints
            session.run("""
                CREATE CONSTRAINT block_content IF NOT EXISTS
                FOR (b:Block) REQUIRE b.content IS UNIQUE
            """)

            session.run("""
                CREATE CONSTRAINT tag_name IF NOT EXISTS
                FOR (t:Tag) REQUIRE t.name IS UNIQUE
            """)

            # Create vector index
            idx_config = self.config["knowledge_base"]["indexes"][0]
            session.run(f"""
                CALL db.index.vector.createNodeIndex(
                    '{idx_config["name"]}',
                    '{idx_config["node_label"]}',
                    '{idx_config["property"]}',
                    {idx_config["dimension"]},
                    'cosine'
                )
            """)

    def extract_metadata(self, content: str) -> list[str]:
        """Extract hashtags and wiki-links from content."""
        hashtags = re.findall(r"#([^\s#\[\]]+)", content)
        wikilinks = re.findall(r"\[\[(.*?)\]\]", content)
        return list(set(hashtags + wikilinks))  # Remove duplicates

    def parse_blocks(self, content: str) -> list[Block]:
        """Parse content into blocks with metadata."""
        blocks = []
        current_block = None

        for line in content.splitlines():
            if line.strip().startswith("- "):
                if current_block:
                    blocks.append(current_block)

                level = (len(line) - len(line.lstrip())) // 4
                content = line.strip("- ").strip()
                tags = self.extract_metadata(content)
                embedding = self.model.encode(content).tolist()

                current_block = Block(content=content, level=level, tags=tags, embedding=embedding)

        if current_block:
            blocks.append(current_block)

        return blocks

    def create_block_node(self, session: Session, block: Block, file_path: str) -> None:
        """Create a node for a block with its embedding."""
        query = """
        MERGE (b:Block {content: $content})
        SET b.embedding = $embedding,
            b.level = $level,
            b.source_file = $source_file,
            b.last_modified = $last_modified
        """
        session.run(
            query,
            {
                "content": block.content,
                "embedding": block.embedding,
                "level": block.level,
                "source_file": file_path,
                "last_modified": Path(file_path).stat().st_mtime,
            },
        )

    def create_tag_relationship(self, session: Session, content: str, tag: str) -> None:
        """Create tag node and relationship."""
        query = """
        MERGE (t:Tag {name: $tag})
        WITH t
        MATCH (b:Block {content: $content})
        MERGE (b)-[:TAGGED]->(t)
        """
        session.run(query, {"tag": tag, "content": content})

    def create_semantic_relationships(self, session: Session) -> None:
        """Create SIMILAR relationships between semantically similar blocks."""
        query = """
        MATCH (b1:Block)
        MATCH (b2:Block)
        WHERE elementId(b1) < elementId(b2)  // Using elementId() instead of id()
        WITH b1, b2, gds.similarity.cosine(b1.embedding, b2.embedding) as similarity
        WHERE similarity > $threshold
        MERGE (b1)-[:SIMILAR {score: similarity}]->(b2)
        """
        session.run(query, {"threshold": self.similarity_threshold})

    def process_file(self, file_path: Path, batch_size: int = 100) -> None:
        """Process a single file into the knowledge base."""
        try:
            content = file_path.read_text(encoding="utf-8")
            blocks = self.parse_blocks(content)

            with self.driver.session() as session:
                # Process blocks in batches
                for i in range(0, len(blocks), batch_size):
                    batch = blocks[i : i + batch_size]
                    for block in batch:
                        # Pass the file_path here
                        self.create_block_node(session, block, str(file_path))
                    self.logger.info(f"Processed batch of {len(batch)} blocks from {file_path.name}")

                # Create semantic relationships after all blocks are created
                self.create_semantic_relationships(session)

        except Exception as e:
            self.logger.exception(f"Error processing {file_path}: {e!s}")

    def initialize_knowledge_base(self) -> None:
        """Initialize the knowledge base with all notes."""
        self.logger.info("Starting knowledge base initialization...")

        # First count total files to process
        total_files = 0
        for source in self.config["knowledge_base"]["sources"]:
            source_path = Path(source["path"])
            total_files += len(list(source_path.glob(source["file_pattern"])))

        with tqdm(total=total_files, desc="Building Knowledge Base", unit="file") as pbar:
            for source in self.config["knowledge_base"]["sources"]:
                source_path = Path(source["path"])

                files = list(source_path.glob(source["file_pattern"]))
                for file_path in files:
                    self.process_file(file_path)
                    pbar.set_postfix_str(f"Current file: {file_path.name}")
                    pbar.update(1)

        self.logger.info("Knowledge base initialization completed")

    def query_similar_content(self, content: str, limit: int = 5) -> list[dict]:
        """Find similar content using vector similarity."""
        embedding = self.model.encode(content).tolist()

        with self.driver.session() as session:
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

    def is_file_processed(self, session: Session, file_path: Path) -> bool:
        """Check if file has already been processed."""
        query = """
        MATCH (b:Block)
        WHERE b.source_file = $file_path
        RETURN count(b) > 0 as exists
        """
        result = session.run(query, {"file_path": str(file_path)})
        return result.single()["exists"]

    def update_knowledge_base(self) -> None:
        """Update existing knowledge base with new or modified notes."""
        self.logger.info("Starting knowledge base update...")

        with self.driver.session() as session:
            for source in self.config["knowledge_base"]["sources"]:
                source_path = Path(source["path"])
                self.logger.info(f"Processing source: {source_path}")

                for file_path in source_path.glob(source["file_pattern"]):
                    # Check if file exists in DB and get its last modified time
                    query = """
                    MATCH (b:Block)
                    WHERE b.source_file = $file_path
                    RETURN max(b.last_modified) as last_modified
                    """
                    result = session.run(query, {"file_path": str(file_path)})
                    db_last_modified = result.single()["last_modified"]

                    # Get file's current modification time
                    current_modified = file_path.stat().st_mtime

                    # Process file if it's new or modified
                    if not db_last_modified or float(db_last_modified) < current_modified:
                        self.logger.info(f"Processing modified/new file: {file_path.name}")

                        # Delete existing nodes for this file if any
                        session.run(
                            """
                            MATCH (b:Block)
                            WHERE b.source_file = $file_path
                            DETACH DELETE b
                            """,
                            {"file_path": str(file_path)},
                        )

                        # Process the file
                        self.process_file(file_path)
                    else:
                        self.logger.debug(f"Skipping unmodified file: {file_path.name}")

        self.logger.info("Knowledge base update completed")
