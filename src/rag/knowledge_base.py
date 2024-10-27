import gc
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
if load_config()["knowledge_base"]["embedding"]["device"] == "cuda":
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

        # Initialize embedding model with config
        embedding_config = self.config["knowledge_base"]["embedding"]
        self.model = SentenceTransformer(embedding_config["model"], device=embedding_config["device"])
        self.similarity_threshold = embedding_config["similarity_threshold"]

        # Initialize Neo4j connection
        db_config = self.config["knowledge_base"]["database"]
        self.driver: Driver = GraphDatabase.driver(
            db_config["uri"],
            auth=(db_config["user"], db_config["password"]),
        )

    def __del__(self) -> None:
        """Cleanup Neo4j connection."""
        if hasattr(self, "driver"):
            self.driver.close()

    def _setup_database(self) -> None:
        db_config = self.config["knowledge_base"]["database"]

        with self.driver.session() as session:
            # Create configurable constraints
            for constraint in db_config["constraints"]:
                session.run(f"""
                    CREATE CONSTRAINT {constraint['name']} IF NOT EXISTS
                    FOR (b:{constraint['node']}) REQUIRE b.{constraint['property']} IS UNIQUE
                """)

            # Create vector index from config
            vector_idx = db_config["vector_index"]
            session.run(f"""
                CALL db.index.vector.createNodeIndex(
                    '{vector_idx['name']}',
                    '{vector_idx['node']}',
                    '{vector_idx['property']}',
                    {self.config['knowledge_base']['embedding']['dimension']},
                    '{vector_idx['algorithm']}'
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

        # Get chunk and batch sizes from config
        chunk_size = self.config["knowledge_base"]["embedding"]["chunk_size"]
        batch_size = self.config["knowledge_base"]["processing"]["embedding_batch_size"]

        embeddings_list = []
        for i in range(0, len(texts_to_embed), chunk_size):
            chunk = texts_to_embed[i : i + chunk_size]
            batches = [chunk[j : j + batch_size] for j in range(0, len(chunk), batch_size)]

            if embedding_pbar is not None:
                embedding_pbar.total = len(batches)
                embedding_pbar.reset()

            with multiprocessing.Pool(processes=self.config["system"]["cpu_threads"]) as pool:
                for result in pool.imap(self.model.encode, batches):
                    embeddings_list.extend(result)
                    if embedding_pbar is not None:
                        embedding_pbar.update(1)
                gc.collect()
                pool.close()
                pool.join()

        for block, embedding in zip(blocks, embeddings_list, strict=False):
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
