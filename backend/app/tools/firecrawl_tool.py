from typing import Any

from app.core.config import settings


class FirecrawlTool:
    def __init__(self) -> None:
        self.api_key = settings.firecrawl_api_key

    def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        try:
            from firecrawl import FirecrawlApp

            app = FirecrawlApp(api_key=self.api_key)
            result = app.search(query=query, limit=max_results)
            return result.get("data", result) if isinstance(result, dict) else result
        except Exception:
            return []

    def scrape(self, url: str) -> dict[str, Any] | None:
        if not self.api_key:
            return None
        try:
            from firecrawl import FirecrawlApp

            app = FirecrawlApp(api_key=self.api_key)
            return app.scrape_url(url)
        except Exception:
            return None
