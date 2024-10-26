import multiprocessing
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from neo4j import Driver, GraphDatabase, Session
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from config import load_config
from utils import get_logger


# Set start method to 'spawn' for CUDA support
multiprocessing.set_start_method("spawn", force=True)

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
        neo4j_config = self.config["knowledge_base"]["database"]
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

            # Create vector index with hardcoded values
            session.run(f"""
                CALL db.index.vector.createNodeIndex(
                    'block_embedding',
                    'Block',
                    'embedding',
                    {self.config["knowledge_base"]["embedding"]["dimension"]},
                    'cosine'
                )
            """)

    def sync_knowledge_base(self) -> None:
        """Synchronize knowledge base with notes."""
        start_time = time.time()
        self.logger.info("Starting knowledge base synchronization...")

        # Initialize if needed
        with self.driver.session() as session:
            # Check if constraints exist
            result = session.run("""
                SHOW CONSTRAINTS
                YIELD name
                RETURN count(*) as count
            """)
            is_initialized = result.single()["count"] > 0

            if not is_initialized:
                self.logger.info("First-time initialization - setting up database...")
                self._setup_database()

        # Count total files
        total_files = 0
        all_files = []
        sources_config = self.config["sources"]
        for _source_type, source_info in sources_config.items():
            source_path = Path(source_info["path"])
            files = list(source_path.glob(source_info["pattern"]))
            total_files += len(files)
            all_files.extend(files)

        self.logger.info(f"Found {total_files} files to process")

        try:
            # Keep existing progress bar and parallel processing logic
            with tqdm(total=total_files, desc="Synchronizing Knowledge Base", unit="file") as pbar:
                with ThreadPoolExecutor(
                    max_workers=self.config["knowledge_base"]["processing"]["parallel_files"]
                ) as executor:
                    futures = []

                    for file_path in all_files:
                        with self.driver.session() as session:
                            # Check if file exists and get last modified time
                            query = """
                            MATCH (b:Block)
                            WHERE b.source_file = $file_path
                            RETURN max(b.last_modified) as last_modified
                            """
                            result = session.run(query, {"file_path": str(file_path)})
                            db_last_modified = result.single()["last_modified"]
                            current_modified = file_path.stat().st_mtime

                            # Process file if it's new or modified
                            if not db_last_modified or float(db_last_modified) < current_modified:
                                if db_last_modified:
                                    session.run(
                                        """
                                        MATCH (b:Block)
                                        WHERE b.source_file = $file_path
                                        DETACH DELETE b
                                        """,
                                        {"file_path": str(file_path)},
                                    )
                                futures.append(executor.submit(self.process_file, file_path))
                            pbar.update(1)

                    self.logger.info("Processing futures...")
                    # Wait for all processing to complete
                    for future in futures:
                        future.result()
                    self.logger.info("All futures completed")

            total_time = time.time() - start_time
            self.logger.info(
                f"Knowledge base synchronization completed in {total_time/60:.1f} minutes. "
                f"Processed {total_files} files at {total_files/total_time:.1f} files/second"
            )
        except Exception as e:
            self.logger.exception(f"Synchronization failed: {str(e)}")
            raise

    def extract_metadata(self, content: str) -> list[str]:
        """Extract hashtags and wiki-links from content."""
        hashtags = re.findall(r"#([^\s#\[\]]+)", content)
        wikilinks = re.findall(r"\[\[(.*?)\]\]", content)
        return list(set(hashtags + wikilinks))  # Remove duplicates

    def parse_blocks(self, content: str) -> list[Block]:
        """Parse content into blocks with metadata."""
        blocks = []
        texts_to_embed = []

        # First pass: create blocks without embeddings
        for line in content.splitlines():
            if line.strip().startswith("- "):
                level = (len(line) - len(line.lstrip())) // 4
                content = line.strip("- ").strip()
                tags = self.extract_metadata(content)
                blocks.append(Block(content=content, level=level, tags=tags, embedding=None))
                texts_to_embed.append(content)

        # Batch process embeddings using multiprocessing
        batch_size = self.config["knowledge_base"]["processing"]["embedding_batch_size"]

        # Create progress bar for embedding batches
        batches = [texts_to_embed[i : i + batch_size] for i in range(0, len(texts_to_embed), batch_size)]
        with tqdm(total=len(batches), desc="Generating Embeddings", unit="batch") as embed_pbar:
            with multiprocessing.Pool(processes=self.config["system"]["cpu_threads"]) as pool:
                # Process batches in parallel with progress updates
                embeddings_list = []
                for result in pool.imap(self.model.encode, batches):
                    embeddings_list.append(result)
                    embed_pbar.update(1)

                # Flatten results and assign back to blocks
                all_embeddings = [emb for batch in embeddings_list for emb in batch]
                for block, embedding in zip(blocks, all_embeddings, strict=False):
                    block.embedding = embedding.tolist()

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

    def process_file(self, file_path: Path) -> None:
        """Process a single file into the knowledge base."""
        try:
            content = file_path.read_text(encoding="utf-8")
            blocks = self.parse_blocks(content)

            batch_size = self.config["knowledge_base"]["processing"]["batch_size"]

            with self.driver.session() as session:
                # Use unwind for batch operations
                for i in range(0, len(blocks), batch_size):
                    batch = blocks[i : i + batch_size]

                    # Batch create blocks
                    session.run(
                        """
                        UNWIND $blocks as block
                        MERGE (b:Block {content: block.content})
                        SET b.embedding = block.embedding,
                            b.level = block.level,
                            b.source_file = $source_file,
                            b.last_modified = $last_modified
                    """,
                        {
                            "blocks": [
                                {"content": b.content, "embedding": b.embedding, "level": b.level} for b in batch
                            ],
                            "source_file": str(file_path),
                            "last_modified": file_path.stat().st_mtime,
                        },
                    )

                    # Batch create tags
                    tags_data = []
                    for block in batch:
                        for tag in block.tags:
                            tags_data.append({"content": block.content, "tag": tag})

                    if tags_data:
                        session.run(
                            """
                            UNWIND $tags_data as data
                            MERGE (t:Tag {name: data.tag})
                            WITH t, data
                            MATCH (b:Block {content: data.content})
                            MERGE (b)-[:TAGGED]->(t)
                        """,
                            {"tags_data": tags_data},
                        )

        except Exception as e:
            self.logger.exception(f"Error processing {file_path}: {e!s}")
