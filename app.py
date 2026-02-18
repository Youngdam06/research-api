from fastapi import FastAPI, Query, HTTPException, status
import requests
import redis
import json
import hashlib
import os
from typing import List, Dict, Any, Optional
import re
from collections import Counter
from requests.exceptions import HTTPError, RequestException
STOPWORDS = {
    "the","of","and","in","for","on","with","to","a","an","by","from","at","as",
    "is","are","be","this","that","using","use","based","via","into","between",
    "study","analysis","approach","method","methods","review","system","model",
    "models","data","application","applications"
}

# ===== Standard Error Definitions (Numeric Codes) =====

ERROR_INVALID_QUERY = {
    "http_status": status.HTTP_422_UNPROCESSABLE_ENTITY,  # 422
    "code": 422,
    "message": "Invalid query parameter",
    "description": "Required query parameter is missing or has invalid format."
}

ERROR_NOT_FOUND = {
    "http_status": status.HTTP_404_NOT_FOUND,  # 404
    "code": 404,
    "message": "Resource not found",
    "description": "The requested paper or resource could not be found."
}

ERROR_UPSTREAM_FAILED = {
    "http_status": status.HTTP_502_BAD_GATEWAY,  # 502
    "code": 502,
    "message": "Upstream provider error",
    "description": "Failed to fetch data from OpenAlex or Crossref."
}

ERROR_INTERNAL = {
    "http_status": status.HTTP_500_INTERNAL_SERVER_ERROR,  # 500
    "code": 500,
    "message": "Internal server error",
    "description": "An unexpected error occurred on the server."
}

app = FastAPI(title="Research Metadata API", version="1.0.0")

# ===== Redis Server 
REDIS_HOST = os.getenv("REDIS_HOST", "redis-cache")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)
# --------- Helpers: caching -----------
def make_cache_key(prefix: str, params: dict) -> str:
    raw = json.dumps(params, sort_keys=True)
    digest = hashlib.md5(raw.encode()).hexdigest()
    return f"{prefix}:{digest}"

def get_cache(key: str):
    try:
        cached = redis_client.get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass
    return None

def set_cache(key: str, value: dict, ttl: int):
    try:
        redis_client.setex(key, ttl, json.dumps(value))
    except Exception:
        pass

def is_cacheable_response(response: dict) -> bool:
    # jangan cache kalau kosong
    if not response:
        return False

    # jangan cache error
    if "detail" in response:
        return False

    # khusus search / trends → harus ada data
    if "results" in response and len(response["results"]) == 0:
        return False

    return True


# --------- Helpers: Errors Handler -----------
def raise_api_error(error_def: dict, details: dict | None = None):
    payload = {
        "status": "error",
        "code": error_def["code"],
        "message": error_def["message"],
        "description": error_def["description"],
        "details": details,
    }
    raise HTTPException(status_code=error_def["http_status"], detail=payload)

# --------- Helpers: Lookup paper by doi -----------
def fetch_openalex_by_doi(doi: str):
    # OpenAlex bisa search by DOI pakai filter
    url = "https://api.openalex.org/works"
    params = {
        "filter": f"doi:{doi.lower()}"
    }
    headers = {
        "User-Agent": "ResearchMetadataAPI/1.0 (mailto:fathoniadam933@gmail.com)"
    }

    r = requests.get(url, params=params, headers=headers, timeout=15)

    if r.status_code == 404:
        return None
    
    r.raise_for_status()
    data = r.json()

    results = data.get("results", [])
    if not results:
        return None

    return normalize_openalex(results[0])


def fetch_crossref_by_doi(doi: str):
    # CrossRef punya endpoint langsung by DOI
    url = f"https://api.crossref.org/works/{doi}"
    headers = {
        "User-Agent": "ResearchMetadataAPI/1.0 (mailto:fathoniadam933@gmail.com)"
    }

    r = requests.get(url, headers=headers, timeout=15)

    if r.status_code == 404:
        return None
    
    r.raise_for_status()
    data = r.json()

    item = data.get("message")
    if not item:
        return None

    return normalize_crossref(item)


# --------- Helpers: Trends ---------
def extract_keywords(titles: List[str], top: int = 10):
    words = []

    for title in titles:
        if not title:
            continue

        # lowercase + ambil huruf aja
        tokens = re.findall(r"[a-zA-Z]+", title.lower())

        for t in tokens:
            if len(t) < 3:
                continue
            if t in STOPWORDS:
                continue
            words.append(t)

    counter = Counter(words)
    most_common = counter.most_common(top)

    return [
        {"keyword": k, "count": v}
        for k, v in most_common
    ]

def extract_bigrams(titles: List[str], top: int = 10):
    pairs = []

    for title in titles:
        if not title:
            continue

        tokens = re.findall(r"[a-zA-Z]+", title.lower())

        # bersihin token
        clean = [
            t for t in tokens
            if len(t) >= 3 and t not in STOPWORDS
        ]

        # bikin bigram
        for i in range(len(clean) - 1):
            pair = clean[i] + " " + clean[i + 1]
            pairs.append(pair)

    counter = Counter(pairs)
    most_common = counter.most_common(top)

    return [
        {"bigram": k, "count": v}
        for k, v in most_common
    ]

def extract_trigrams(titles: List[str], top: int = 10):
    triples = []

    for title in titles:
        if not title:
            continue

        tokens = re.findall(r"[a-zA-Z]+", title.lower())

        clean = [
            t for t in tokens
            if len(t) >= 3 and t not in STOPWORDS
        ]

        # bikin trigram
        for i in range(len(clean) - 2):
            triple = clean[i] + " " + clean[i + 1] + " " + clean[i + 2]
            triples.append(triple)

    counter = Counter(triples)
    most_common = counter.most_common(top)

    return [
        {"trigram": k, "count": v}
        for k, v in most_common
    ]

def trends_per_year(results: List[Dict[str, Any]], top: int = 5):
    # group titles by year
    by_year: Dict[int, List[str]] = {}

    for item in results:
        year = item.get("year")
        title = item.get("title")

        if not year or not title:
            continue

        by_year.setdefault(year, []).append(title)

    output = {}

    for year, titles in sorted(by_year.items()):
        output[year] = {
            "unigrams": extract_keywords(titles, top=top),
            "bigrams": extract_bigrams(titles, top=top),
            "trigrams": extract_trigrams(titles, top=top),
        }

    return output

# --------- Helpers: Normalizers ---------

def normalize_openalex(item: Dict[str, Any]) -> Dict[str, Any]:
    authors = []
    for a in item.get("authorships", []):
        author = a.get("author")
        if author and author.get("display_name"):
            authors.append(author["display_name"])

    return {
        "title": item.get("title"),
        "authors": authors,
        "year": item.get("publication_year"),
        "doi": item.get("doi"),
        
    }


def normalize_crossref(item: Dict[str, Any]) -> Dict[str, Any]:
    # title di CrossRef biasanya list
    title_list = item.get("title", [])
    title = title_list[0] if isinstance(title_list, list) and title_list else None

    authors = []
    for a in item.get("author", []):
        given = a.get("given", "")
        family = a.get("family", "")
        name = (given + " " + family).strip()
        if name:
            authors.append(name)

    # year bisa ada di issued -> date-parts
    year = None
    issued = item.get("issued", {}).get("date-parts")
    if issued and isinstance(issued, list) and len(issued) > 0 and len(issued[0]) > 0:
        year = issued[0][0]

    doi = item.get("DOI")
    if doi:
        doi = "https://doi.org/" + doi

    return {
        "title": title,
        "authors": authors,
        "year": year,
        "doi": doi,
        
    }


# --------- Fetchers ---------

def fetch_openalex(query: str, from_year: int | None, to_year: int | None, limit: int):
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": min(limit, 25),
    }

    # filter tahun (pakai range publication_year)
    if from_year and to_year:
        params["filter"] = f"publication_year:{from_year}-{to_year}"
    elif from_year:
        params["filter"] = f"publication_year:{from_year}-9999"
    elif to_year:
        params["filter"] = f"publication_year:0-{to_year}"

    headers = {
        "User-Agent": "ResearchMetadataAPI/1.0 (mailto:fathoniadam933@gmail.com)"
    }

    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()

    print("OpenAlex raw count:", len(data.get("results", [])))  # 👈 debug

    results = []
    for item in data.get("results", []):
        normalized = normalize_openalex(item)
        if normalized.get("doi"):   
            results.append(normalized)

    print("OpenAlex normalized count:", len(results))  # 👈 debug

    return results



def fetch_crossref(query: str, from_year: int | None, to_year: int | None, limit: int):
    url = "https://api.crossref.org/works"
    params = {
        "query": query,
        "rows": min(limit, 25),
    }

    # filter tanggal
    filters = []
    if from_year:
        filters.append(f"from-pub-date:{from_year}")
    if to_year:
        filters.append(f"until-pub-date:{to_year}")

    if filters:
        params["filter"] = ",".join(filters)

    headers = {
        "User-Agent": "ResearchMetadataAPI/1.0 (mailto:your-email@example.com)"
    }

    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()

    items = data.get("message", {}).get("items", [])

    results = []
    for item in items:
        normalized = normalize_crossref(item)
        if normalized.get("doi"):  
            results.append(normalized)

    return results


# --------- Utils ---------

def deduplicate_by_doi(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique = []

    for item in items:
        doi = item.get("doi")
        key = doi.lower() if isinstance(doi, str) else None

        if key and key in seen:
            continue

        if key:
            seen.add(key)

        unique.append(item)

    return unique


# --------- Endpoints ---------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/papers/search")
def search(
    query: str = Query(...),
    from_year: int | None = Query(None),
    to_year: int | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
):
    cache_key = make_cache_key("search", {
        "query": query,
        "from_year": from_year,
        "to_year": to_year,
        "limit": limit
    })

    cached = get_cache(cache_key)
    if cached:
        return cached

    try:
        results = []
        per_source_limit = max(1, limit // 2)

        oa_results = fetch_openalex(query, from_year, to_year, per_source_limit)
        cr_results = fetch_crossref(query, from_year, to_year, per_source_limit)

        results.extend(oa_results)
        results.extend(cr_results)

        results = deduplicate_by_doi(results)[:limit]

        response = {
            "query": query,
            "filters": {
                "from_year": from_year,
                "to_year": to_year,
            },
            "count": len(results),
            "results": results,
        }

        if is_cacheable_response(response):
            set_cache(cache_key, response, ttl=60 * 60 * 3)  # 3 jam

        return response

    except Exception:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "code": 502,
                "message": "Upstream service error",
                "description": "Failed to fetch data from OpenAlex or Crossref."
            }
        )



@app.get("/v1/trends")
def trends(
    query: str = Query(...),
    from_year: int | None = Query(None),
    to_year: int | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    top: int = Query(10, ge=1, le=50),
):
    cache_key = make_cache_key("trends", {
        "query": query,
        "from_year": from_year,
        "to_year": to_year,
        "limit": limit,
        "top": top
    })

    cached = get_cache(cache_key)
    if cached:
        return cached

    try:
        results = []
        results.extend(fetch_openalex(query, from_year, to_year, limit))
        results.extend(fetch_crossref(query, from_year, to_year, limit))

        results = deduplicate_by_doi(results)
        titles = [r["title"] for r in results if r.get("title")]

        response = {
            "query": query,
            "filters": {
                "from_year": from_year,
                "to_year": to_year,
            },
            "total_papers": len(results),
            "top": top,
            "unigrams": extract_keywords(titles, top),
            "bigrams": extract_bigrams(titles, top),
            "trigrams": extract_trigrams(titles, top),
            "per_year": trends_per_year(results, top=min(5, top)),
        }

        if is_cacheable_response(response):
            set_cache(cache_key, response, ttl=60 * 60 * 6)  # 6 jam

        return response

    except Exception:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "code": 502,
                "message": "Upstream service error",
                "description": "Failed to fetch trend data from OpenAlex or Crossref."
            }
        )

@app.get("/v1/papers/lookup")
def lookup_paper(
    doi: str = Query(...)
):
    doi_clean = doi.replace("https://doi.org/", "").strip()

    cache_key = make_cache_key("lookup", {"doi": doi_clean})
    cached = get_cache(cache_key)

    if cached:
        return cached

    try:
        result = fetch_openalex_by_doi(doi_clean)
        if not result:
            result = fetch_crossref_by_doi(doi_clean)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": "error",
                    "code": 404,
                    "message": "Paper not found",
                    "description": "No paper was found for the given DOI in OpenAlex and Crossref.",
                    "details": {"doi": doi_clean}
                }
            )

        response = {
            "paper": result
        }

        set_cache(cache_key, response, ttl=60 * 60 * 24)  # 24 jam

        return response

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "code": 502,
                "message": "Upstream service error",
                "description": "Failed to fetch paper metadata."
            }
        )


