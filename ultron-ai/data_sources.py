"""
External data integrations: news, weather, web search.

Every public function here returns either the expected data structure or a
{"error": "..."} dict — it never raises. That lets brain.py hand the result
straight back to Claude as a tool result and let the model explain the
failure conversationally, instead of the whole app crashing on a bad API
response or a network blip.
"""

import requests

from config import NEWSAPI_KEY, OPENWEATHERMAP_KEY, TAVILY_API_KEY

REQUEST_TIMEOUT = 10  # seconds


def get_news(topic: str) -> dict:
    """Top 5 recent articles about `topic` via NewsAPI's /everything endpoint."""
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": topic,
                "sortBy": "publishedAt",
                "pageSize": 5,
                "language": "en",
                "apiKey": NEWSAPI_KEY,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "ok":
            return {"error": data.get("message", "NewsAPI returned an error")}

        articles = [
            {
                "title": a.get("title"),
                "source": (a.get("source") or {}).get("name"),
                "url": a.get("url"),
                "published_at": a.get("publishedAt"),
            }
            for a in data.get("articles", [])[:5]
        ]

        if not articles:
            return {"error": f"No news articles found for '{topic}'"}

        return {"topic": topic, "articles": articles}

    except requests.exceptions.RequestException as e:
        return {"error": f"News request failed: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error fetching news: {e}"}


def get_weather(location: str) -> dict:
    """Current weather for `location` via OpenWeatherMap."""
    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "q": location,
                "appid": OPENWEATHERMAP_KEY,
                "units": "imperial",
            },
            timeout=REQUEST_TIMEOUT,
        )

        if resp.status_code == 404:
            return {"error": f"Location '{location}' not found"}
        resp.raise_for_status()
        data = resp.json()

        return {
            "location": f"{data.get('name', location)}, {(data.get('sys') or {}).get('country', '')}".strip(", "),
            "temp": data.get("main", {}).get("temp"),
            "condition": (data.get("weather") or [{}])[0].get("description", "unknown"),
            "humidity": data.get("main", {}).get("humidity"),
            "wind_speed": data.get("wind", {}).get("speed"),
        }

    except requests.exceptions.RequestException as e:
        return {"error": f"Weather request failed: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error fetching weather: {e}"}


def web_search(query: str) -> dict:
    """Top 5 web results for `query` via Tavily's search API."""
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": 5,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        results = [
            {
                "title": r.get("title"),
                "snippet": r.get("content"),
                "url": r.get("url"),
            }
            for r in data.get("results", [])[:5]
        ]

        if not results:
            return {"error": f"No search results found for '{query}'"}

        return {"query": query, "results": results}

    except requests.exceptions.RequestException as e:
        return {"error": f"Search request failed: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error during search: {e}"}
