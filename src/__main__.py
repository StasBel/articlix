import logging

from src.crawler import Crawler
from src.source import reliable_sources

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    # Set up the logger.
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run the crawler.
    crawler = Crawler(sources=reliable_sources, al_least_pages=1000)
    crawler.run()
