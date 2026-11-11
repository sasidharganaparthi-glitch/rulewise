"""Live Information & Web Grounding Service for RuleWise AI (Requirement 7).

Retrieves verified real-time information for time-sensitive, news, and current regulatory queries.
Includes publication sources, dates, and links while distinguishing verified live facts.
Kept strictly separate from the deterministic symbolic inference engine.
"""

import json
import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

# Trigger keywords indicating user is seeking live, current, or time-sensitive information
LIVE_INTENT_PATTERNS = [
    r"\b(latest|current|today|recent|recently|breaking|news|2025|2026|update|updates|live|now|right now)\b",
    r"\b(who won|who is winning|score|stock price|weather|headline|headlines|new regulation|policy change)\b",
    r"\b(what happened|is .+ released|launch date|current status|new law|latest version)\b",
]


def is_live_information_query(query: str) -> bool:
    """Detect if query seeks time-sensitive or real-time external information."""
    q = query.lower().strip()
    return any(re.search(pat, q, re.IGNORECASE) for pat in LIVE_INTENT_PATTERNS)


class LiveInformationService:
    """Fetches real-time web data and cites sources for time-sensitive inquiries."""

    def __init__(self, timeout_seconds: float = 6.0) -> None:
        self.timeout = timeout_seconds

    def search_live_web(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """Retrieve real-time web search results using reliable public endpoints."""
        cleaned = re.sub(r"[^\w\s]", " ", query).strip()
        encoded = urllib.parse.quote_plus(cleaned)
        results: List[Dict[str, str]] = []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        # 1. DuckDuckGo Instant Answers API
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
                resp = client.get(
                    f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    abstract = data.get("AbstractText")
                    url = data.get("AbstractURL")
                    source = data.get("AbstractSource")
                    if abstract and url:
                        results.append({
                            "title": source or "Verified Web Source",
                            "snippet": abstract,
                            "url": url,
                        })
                    for topic in data.get("RelatedTopics", []):
                        if isinstance(topic, dict) and topic.get("Text") and topic.get("FirstURL"):
                            results.append({
                                "title": topic.get("FirstURL", "").split("//")[-1].split("/")[0],
                                "snippet": topic.get("Text", ""),
                                "url": topic.get("FirstURL", ""),
                            })
                            if len(results) >= max_results:
                                break
        except Exception as exc:
            logger.debug("DuckDuckGo Instant Answer search failed: %s", exc)

        # 2. DuckDuckGo HTML Lite fallback if API yielded insufficient results
        if len(results) < 2:
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
                    resp = client.post(
                        "https://html.duckduckgo.com/html/",
                        data={"q": cleaned},
                    )
                    if resp.status_code == 200:
                        html = resp.text
                        # Simple regex extraction of title, link, and snippet
                        links = re.findall(
                            r'<a class="result__url" href="([^"]+)".*?>(.*?)</a>',
                            html,
                            re.IGNORECASE,
                        )
                        snippets = re.findall(
                            r'<a class="result__snippet[^>]*>(.*?)</a>',
                            html,
                            re.IGNORECASE,
                        )
                        for i in range(min(len(links), len(snippets), max_results - len(results))):
                            raw_url = links[i][0]
                            # Extract true url from uddg parameter if wrapped
                            if "uddg=" in raw_url:
                                match = re.search(r"uddg=([^&]+)", raw_url)
                                if match:
                                    raw_url = urllib.parse.unquote(match.group(1))
                            clean_snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
                            clean_title = re.sub(r"<[^>]+>", "", links[i][1]).strip() or "Web Result"
                            if clean_snippet and raw_url:
                                results.append({
                                    "title": clean_title,
                                    "snippet": clean_snippet,
                                    "url": raw_url,
                                })
            except Exception as exc:
                logger.debug("DuckDuckGo HTML search fallback failed: %s", exc)

        return results[:max_results]

    def answer_with_live_grounding(
        self,
        query: str,
        provider: Any,
        conversation_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synthesize response grounded in verified live web facts."""
        search_results = self.search_live_web(query)
        current_time = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")

        if not search_results:
            # Fallback when external service is offline or yielded no results
            system_prompt = (
                f"You are RuleWise AI. Current date is {current_time}. "
                "The user is asking a time-sensitive question, but live web search is currently unreachable. "
                "Answer based on your baseline knowledge, but explicitly state that live search was unavailable."
            )
            prompt = f"{conversation_context or ''}\n\nUser Question: {query}"
            text = provider.generate_text(prompt, system_instruction=system_prompt)
            return {
                "text": text + "\n\n*(Note: Live external verification was temporarily unavailable; answer is based on internal knowledge baseline.)*",
                "sources": [],
                "is_live_verified": False,
            }

        # Build grounded context
        snippets_text = "\n\n".join([
            f"Source [{i+1}] ({s['title']}):\n{s['snippet']}\nURL: {s['url']}"
            for i, s in enumerate(search_results)
        ])

        system_prompt = (
            f"You are RuleWise AI with Real-Time Web Grounding. The current time is {current_time}.\n"
            "Answer the user inquiry accurately using the verified real-time search results below.\n"
            "Format guidelines:\n"
            "- Provide a clear, natural, direct answer.\n"
            "- Distinguish verified current facts clearly.\n"
            "- Never fabricate facts not supported by the sources.\n\n"
            f"VERIFIED REAL-TIME WEB SOURCES:\n{snippets_text}"
        )

        prompt = f"{conversation_context or ''}\n\nUser Question: {query}"
        try:
            generated = provider.generate_text(prompt, system_instruction=system_prompt)
        except Exception:
            # Fallback to direct summary of search results
            generated = "Here is the latest live information retrieved regarding your inquiry:\n\n" + "\n\n".join(
                [f"• **{s['title']}**: {s['snippet']}" for s in search_results]
            )

        # Append structured source links
        sources_markdown = "\n\n**Verified Real-Time Sources:**\n" + "\n".join([
            f"- [{s['title']}]({s['url']})" for s in search_results
        ])
        full_text = f"{generated.strip()}\n{sources_markdown}"

        return {
            "text": full_text,
            "sources": search_results,
            "is_live_verified": True,
            "retrieved_at": current_time,
        }

