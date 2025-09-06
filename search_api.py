import os
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, TypeVar, Generic
from abc import ABC, abstractmethod
import requests

T = TypeVar('T')

class SearchAPIException(Exception):
    pass

class SerperAPIException(SearchAPIException):
    pass

class SearXNGException(SearchAPIException):
    pass

@dataclass
class SerperConfig:
    api_key: str
    api_url: str = "https://google.serper.dev/search"
    default_location: str = "us"
    timeout: int = 10
    @classmethod
    def from_env(cls) -> "SerperConfig":
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            raise SerperAPIException("SERPER_API_KEY not set")
        return cls(api_key=api_key)

@dataclass
class SearXNGConfig:
    instance_url: str
    api_key: Optional[str] = None
    default_location: str = "all"
    timeout: int = 10
    @classmethod
    def from_env(cls) -> "SearXNGConfig":
        instance_url = os.getenv("SEARXNG_INSTANCE_URL")
        if not instance_url:
            raise SearXNGException("SEARXNG_INSTANCE_URL not set")
        api_key = os.getenv("SEARXNG_API_KEY")
        return cls(instance_url=instance_url, api_key=api_key)

class SearchResult(Generic[T]):
    def __init__(self, data: Optional[T] = None, error: Optional[str] = None):
        self.data = data
        self.error = error
        self.success = error is None
    @property
    def failed(self) -> bool:
        return not self.success

class SearchAPI(ABC):
    @abstractmethod
    def get_sources(self, query: str, num_results: int = 8, stored_location: Optional[str] = None) -> SearchResult[Dict[str, Any]]:
        pass

class SerperAPI(SearchAPI):
    def __init__(self, api_key: Optional[str] = None, config: Optional[SerperConfig] = None):
        if api_key:
            self.config = SerperConfig(api_key=api_key)
        else:
            self.config = config or SerperConfig.from_env()
        self.headers = {"X-API-KEY": self.config.api_key, "Content-Type": "application/json"}
    @staticmethod
    def extract_fields(items: List[Dict[str, Any]], fields: List[str]) -> List[Dict[str, Any]]:
        return [{k: item.get(k, "") for k in fields if k in item} for item in items]
    def get_sources(self, query: str, num_results: int = 8, stored_location: Optional[str] = None) -> SearchResult[Dict[str, Any]]:
        if not query.strip():
            return SearchResult(error="empty query")
        try:
            gl = (stored_location or self.config.default_location).lower()
            payload = {"q": query, "num": min(max(1, num_results), 10), "gl": gl}
            r = requests.post(self.config.api_url, headers=self.headers, json=payload, timeout=self.config.timeout)
            r.raise_for_status()
            data = r.json()
            results = {
                "organic": self.extract_fields(data.get("organic", []), ["title", "link", "snippet", "date"]),
                "topStories": self.extract_fields(data.get("topStories", []), ["title", "imageUrl"]),
                "images": self.extract_fields(data.get("images", [])[:6], ["title", "imageUrl"]),
                "graph": data.get("knowledgeGraph"),
                "answerBox": data.get("answerBox"),
                "peopleAlsoAsk": data.get("peopleAlsoAsk"),
                "relatedSearches": data.get("relatedSearches"),
            }
            return SearchResult(data=results)
        except requests.RequestException as e:
            return SearchResult(error=f"request failed: {str(e)}")
        except Exception as e:
            return SearchResult(error=f"unexpected error: {str(e)}")

class SearXNGAPI(SearchAPI):
    def __init__(self, instance_url: Optional[str] = None, api_key: Optional[str] = None, config: Optional[SearXNGConfig] = None):
        if instance_url:
            self.config = SearXNGConfig(instance_url=instance_url, api_key=api_key)
        else:
            self.config = config or SearXNGConfig.from_env()
        self.headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            self.headers["X-API-Key"] = self.config.api_key
    def get_sources(self, query: str, num_results: int = 8, stored_location: Optional[str] = None) -> SearchResult[Dict[str, Any]]:
        if not query.strip():
            return SearchResult(error="empty query")
        try:
            url = self.config.instance_url
            if not url.endswith("/search"):
                url = url.rstrip("/") + "/search"
            params = {
                "q": query,
                "format": "json",
                "pageno": 1,
                "categories": "general",
                "language": "all",
                "safesearch": 0,
                "engines": "google,bing,duckduckgo",
                "max_results": min(max(1, num_results), 20),
            }
            if stored_location and stored_location != "all":
                params["language"] = stored_location
            r = requests.get(url, headers=self.headers, params=params, timeout=self.config.timeout)
            r.raise_for_status()
            data = r.json()
            organic = []
            for item in data.get("results", [])[:num_results]:
                organic.append({"title": item.get("title", ""), "link": item.get("url", ""), "snippet": item.get("content", ""), "date": item.get("publishedDate", "")})
            images = []
            for item in data.get("results", []):
                if item.get("img_src"):
                    images.append({"title": item.get("title", ""), "imageUrl": item.get("img_src", "")})
            images = images[:6]
            results = {"organic": organic, "images": images, "topStories": [], "graph": None, "answerBox": None, "peopleAlsoAsk": None, "relatedSearches": data.get("suggestions", [])}
            return SearchResult(data=results)
        except requests.RequestException as e:
            return SearchResult(error=f"request failed: {str(e)}")
        except Exception as e:
            return SearchResult(error=f"unexpected error: {str(e)}")

def create_search_api(search_provider: str = "serper", serper_api_key: Optional[str] = None, searxng_instance_url: Optional[str] = None, searxng_api_key: Optional[str] = None) -> SearchAPI:
    p = (search_provider or "serper").lower()
    if p == "serper":
        return SerperAPI(api_key=serper_api_key)
    if p == "searxng":
        return SearXNGAPI(instance_url=searxng_instance_url, api_key=searxng_api_key)
    raise ValueError("invalid search provider")
