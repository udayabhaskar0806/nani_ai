"""N.A.N.I. Deep Research Engine
Conducts recursive, multi-layered deep research on technical topics, architectures, and concepts.
"""

import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from urllib.parse import quote_plus

class DeepResearcher:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def search_web(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """Searches DuckDuckGo HTML endpoint without requiring paid API keys."""
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        results = []

        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    links = soup.find_all("a", class_="result__snippet")
                    titles = soup.find_all("a", class_="result__url")
                    
                    for i in range(min(len(links), max_results)):
                        snippet = links[i].get_text(strip=True)
                        href = titles[i].get("href", "") if i < len(titles) else ""
                        results.append({
                            "title": snippet[:60] + "...",
                            "snippet": snippet,
                            "url": href
                        })
        except Exception as e:
            results.append({"title": "Search Error", "snippet": f"Could not perform live search: {str(e)}", "url": ""})

        return results

    def research(self, topic: str, engine) -> str:
        """Executes a deep research loop on the given topic."""
        # 1. Search the web for recent context
        search_results = self.search_web(topic, max_results=3)
        context_str = ""
        for r in search_results:
            context_str += f"- {r.get('snippet')} ({r.get('url')})\n"

        # 2. Formulate the first-principles "Why?" prompt
        prompt = f"""Conduct a deep, first-principles research investigation into:
Topic: "{topic}"

Live Web Context Found:
{context_str if context_str else 'No direct external web snippets available. Rely on first-principles systems foundations.'}

Investigation Requirements:
1. THE CORE MECHANICS: How does this work at the lowest relevant layer? (CPU cycles, memory allocation, network stack, or algorithmic math).
2. THE 'WHY? WHY? WHY?' CHAIN: Ask and answer at least 3 sequential layers of 'Why?' regarding why it is designed or behaves this way.
3. LIMITATIONS & TRADEOFFS: What are the theoretical and practical bottlenecks? (Cache misses, latency, memory ceilings, concurrency hazards).
4. THE SYNTHESIS & VERDICT: What is the optimal, pragmatic way to use or solve this?
"""
        return engine.generate(prompt)
