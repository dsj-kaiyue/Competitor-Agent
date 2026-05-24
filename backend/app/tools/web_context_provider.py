from typing import Any

from app.tools.firecrawl_tool import FirecrawlTool


class WebContextProvider:
    def __init__(self) -> None:
        self.firecrawl = FirecrawlTool()

    def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        return self.firecrawl.search(query, max_results)

    def scrape(self, url: str) -> dict[str, Any] | None:
        return self.firecrawl.scrape(url)
