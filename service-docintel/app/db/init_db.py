import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.storage.postgres import init_db
from app.services.storage.qdrant import QdrantManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Initialize database and Qdrant collection"""
    try:
        logger.info("Initializing database...")
        await init_db()

        logger.info("Initializing Qdrant collection...")
        await QdrantManager.initialize_collection()

        logger.info("Initialization complete!")
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        raise
    finally:
        # Close connections
        from app.services.storage.postgres import PostgresPool
        await PostgresPool.close()
        await QdrantManager.close()


if __name__ == "__main__":
    asyncio.run(main())