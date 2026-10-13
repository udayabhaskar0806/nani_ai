"""N.A.N.I. GitHub AI Radar
Scans, tracks, and deeply analyzes trending AI, systems, and machine learning repositories.
"""

import httpx
from typing import List, Dict, Any, Optional
from nani.config import Config

class GitHubRadar:
    def __init__(self, token: Optional[str] = None):
        self.token = token or Config.GITHUB_TOKEN
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "NANI-AI-Radar/1.0"
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def scan_trending_ai(self, query: str = "topic:ai stars:>100", limit: int = 6) -> List[Dict[str, Any]]:
        """Finds newly created or rapidly growing AI repositories."""
        url = "https://api.github.com/search/repositories"
        # If user passed a simple keyword like 'cuda' or 'agents', ensure proper format
        q = query.strip()
        if "stars:" not in q:
            q += " stars:>100"

        params = {
            "q": q,
            "sort": "updated",
            "order": "desc",
            "per_page": limit
        }

        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.get(url, headers=self.headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    results = []
                    for item in items:
                        results.append({
                            "name": item.get("full_name"),
                            "description": item.get("description") or "No description provided.",
                            "stars": item.get("stargazers_count", 0),
                            "forks": item.get("forks_count", 0),
                            "language": item.get("language") or "Unknown",
                            "url": item.get("html_url"),
                            "updated_at": item.get("updated_at"),
                        })
                    return results
                else:
                    return [{"error": f"GitHub API status {resp.status_code}: {resp.text}"}]
        except Exception as e:
            return [{"error": f"Network exception: {str(e)}"}]

    def fetch_repo_details(self, repo_full_name: str) -> Dict[str, Any]:
        """Fetches detailed repository info including README and file structure."""
        base_url = f"https://api.github.com/repos/{repo_full_name}"
        details = {"name": repo_full_name}

        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                # 1. Repo info
                meta_resp = client.get(base_url, headers=self.headers)
                if meta_resp.status_code != 200:
                    return {"error": f"Failed to fetch repo {repo_full_name}: {meta_resp.status_code}"}
                meta = meta_resp.json()
                details.update({
                    "description": meta.get("description"),
                    "stars": meta.get("stargazers_count"),
                    "language": meta.get("language"),
                    "license": meta.get("license", {}).get("name") if meta.get("license") else "None",
                    "default_branch": meta.get("default_branch", "main"),
                    "html_url": meta.get("html_url"),
                })

                # 2. Fetch README
                readme_url = f"{base_url}/readme"
                readme_resp = client.get(readme_url, headers={"Accept": "application/vnd.github.raw+json", **self.headers})
                if readme_resp.status_code == 200:
                    # Truncate readme to 4000 characters to keep prompt compact and fast
                    details["readme_snippet"] = readme_resp.text[:4000]
                else:
                    details["readme_snippet"] = "README not accessible."

                # 3. Fetch top-level file structure
                tree_url = f"{base_url}/contents"
                tree_resp = client.get(tree_url, headers=self.headers)
                if tree_resp.status_code == 200:
                    tree_items = [item["name"] for item in tree_resp.json() if "name" in item]
                    details["files"] = tree_items
                else:
                    details["files"] = []

                return details

        except Exception as e:
            return {"error": f"Exception while fetching {repo_full_name}: {str(e)}"}

    def analyze_repo(self, repo_full_name: str, engine) -> str:
        """Deeply analyzes a repo through NANI's first-principles systems filter."""
        details = self.fetch_repo_details(repo_full_name)
        if "error" in details:
            return f"❌ {details['error']}"

        prompt = f"""Conduct a deep-systems first-principles analysis of this repository:
Repository: {details['name']}
Language: {details.get('language')} | Stars: {details.get('stars')} | License: {details.get('license')}
Files: {', '.join(details.get('files', [])[:20])}

README Excerpt:
{details.get('readme_snippet', '')}

Provide an Iron Man / J.A.R.V.I.S.-style briefing with these sections:
1. THE BREAKTHROUGH: What does this repository actually accomplish? (No marketing fluff)
2. UNDER THE HOOD (SYSTEMS & ARCHITECTURE): How does it work at the hardware/software level? (Memory management, parallelism, compute efficiency, protocols)
3. TRADEOFFS & CRITIQUE: What are the limits, hidden costs, or engineering flaws?
4. N.A.N.I.'s VERDICT: Clone & test, star for reference, or ignore? Why?
"""
        return engine.generate(prompt)
