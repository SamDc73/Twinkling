import multiprocessing
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from neo4j import Driver, GraphDatabase, Session
from sentence_transformers import SentenceTransformer
from tqdm.auto import tqdm

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

    def _get_file_signature(self, file_path: Path) -> tuple[float, int]:
        """Get file modification time and size."""
        stat = file_path.stat()
        return (stat.st_mtime, stat.st_size)

    def _get_processed_files(self, session: Session) -> dict[str, tuple[float, int]]:
        """Get all previously processed files and their signatures from DB."""
        result = session.run("""
            MATCH (b:Block)
            WITH b.source_file as file, max(b.last_modified) as mtime, count(*) as size
            RETURN file, mtime, size
        """)
        return {r["file"]: (r["mtime"], r["size"]) for r in result if r["file"]}

    def sync_knowledge_base(self) -> None:
        self.logger.info("Starting knowledge base synchronization...")

        # Collect all files
        all_files = []
        for source_type, source_info in self.config["sources"].items():
            source_path = Path(source_info["path"])
            files = list(source_path.glob(source_info["pattern"]))
            all_files.extend(files)

        with self.driver.session() as session:
            # Get previously processed files
            processed_files = self._get_processed_files(session)

            # Determine which files need processing
            files_to_process = []
            for file_path in all_files:
                file_str = str(file_path)
                current_signature = self._get_file_signature(file_path)

                if file_str not in processed_files or processed_files[file_str] != current_signature:
                    files_to_process.append(file_path)

            if not files_to_process:
                self.logger.info("No files have changed since last sync. Nothing to do.")
                return

            self.logger.info(
                f"Found {len(files_to_process)} files that need processing " f"out of {len(all_files)} total files"
            )

            # Process only changed files
            with tqdm(total=len(files_to_process), desc="Processing Files") as pbar:
                for file_path in files_to_process:
                    # Before processing new version, delete old blocks
                    session.run(
                        """
                        MATCH (b:Block)
                        WHERE b.source_file = $file
                        DETACH DELETE b
                    """,
                        {"file": str(file_path)},
                    )

                    # Process the file
                    self.process_file(file_path)
                    pbar.update(1)

    def extract_metadata(self, content: str) -> list[str]:
        """Extract hashtags and wiki-links from content."""
        hashtags = re.findall(r"#([^\s#\[\]]+)", content)
        wikilinks = re.findall(r"\[\[(.*?)\]\]", content)
        return list(set(hashtags + wikilinks))  # Remove duplicates

    def parse_blocks(self, content: str, embedding_pbar: tqdm | None = None) -> list[Block]:
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
        batches = [texts_to_embed[i : i + batch_size] for i in range(0, len(texts_to_embed), batch_size)]

        if embedding_pbar is not None:
            embedding_pbar.total = len(batches)
            embedding_pbar.reset()

        with multiprocessing.Pool(processes=self.config["system"]["cpu_threads"]) as pool:
            # Process batches in parallel
            embeddings_list = []
            for result in pool.imap(self.model.encode, batches):
                embeddings_list.append(result)
                if embedding_pbar is not None:
                    embedding_pbar.update(1)

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
        try:
            content = file_path.read_text(encoding="utf-8")
            blocks = self.parse_blocks(content)

            # Get file signature
            file_signature = self._get_file_signature(file_path)

            with self.driver.session() as session:
                # Store blocks with file metadata
                session.run(
                    """
                    UNWIND $blocks as block
                    MERGE (b:Block {content: block.content})
                    SET b.embedding = block.embedding,
                        b.level = block.level,
                        b.source_file = $source_file,
                        b.last_modified = $last_modified,
                        b.file_size = $file_size
                """,
                    {
                        "blocks": [{"content": b.content, "embedding": b.embedding, "level": b.level} for b in blocks],
                        "source_file": str(file_path),
                        "last_modified": file_signature[0],  # mtime
                        "file_size": file_signature[1],  # size
                    },
                )

        except Exception as e:
            self.logger.exception(f"Error processing {file_path}: {e}")
