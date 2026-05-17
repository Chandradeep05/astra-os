import httpx
import json
from typing import List, Dict, Any
from app.core.config import settings

class WebSearchTool:
    def __init__(self):
        self.api_key = settings.SERPER_API_KEY
        self.name = "web_search"
        self.description = "Search the live web for current information, news, and real-time data using Serper."

    async def execute(self, query: str) -> str:
        if not self.api_key:
            return "Error: Web search is disabled (No SERPER_API_KEY provided)."
        
        url = "https://google.serper.dev/search"
        headers = {
            'X-API-KEY': self.api_key,
            'Content-Type': 'application/json'
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json={"q": query, "num": 5})
                response.raise_for_status()
                data = response.json()
            
            organic = data.get("organic", [])
            if not organic:
                return f"No results found for '{query}'."

            output = f"SEARCH RESULTS for '{query}':\n\n"
            for res in organic:
                title = res.get("title", "No Title")
                snippet = res.get("snippet", "No description available.")
                link = res.get("link", "#")
                output += f"- {title}: {snippet}\n  Link: {link}\n\n"
            
            return output
        except Exception as e:
            return f"Error during Serper web search: {str(e)}"
