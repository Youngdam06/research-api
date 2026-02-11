from fastapi import FastAPI, Query
import requests
from typing import List, Dict, Any
import re
from collections import Counter
from fastapi import HTTPException
STOPWORDS = {
    "the","of","and","in","for","on","with","to","a","an","by","from","at","as",
    "is","are","be","this","that","using","use","based","via","into","between",
    "study","analysis","approach","method","methods","review","system","model",
    "models","data","application","applications"
}



app = FastAPI(title="Research Metadata API", version="1.0.0")

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
    query: str = Query(..., description="Search keyword / title"),
    from_year: int | None = Query(None, description="From publication year"),
    to_year: int | None = Query(None, description="To publication year"),
    limit: int = Query(20, ge=1, le=50, description="Max results"),
):
    results = []

    per_source_limit = max(1, limit // 2)

    # Fetch from OpenAlex
    try:
        oa_results = fetch_openalex(query, from_year, to_year, per_source_limit)
        results.extend(oa_results)
    except Exception as e:
        print("OpenAlex error:", e)

    # Fetch from CrossRef
    try:
        cr_results = fetch_crossref(query, from_year, to_year, per_source_limit)
        results.extend(cr_results)
    except Exception as e:
        print("CrossRef error:", e)

    # Deduplicate by DOI
    results = deduplicate_by_doi(results)

    results = results[:limit]

    return {
        "query": query,
        "filters": {
            "from_year": from_year,
            "to_year": to_year,
        },
        "count": len(results),
        "results": results,
    }

@app.get("/v1/trends")
def trends(
    query: str = Query(...),
    from_year: int | None = Query(None),
    to_year: int | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    top: int = Query(10, ge=1, le=50),
):
    results = []

    try:
        oa_results = fetch_openalex(query, from_year, to_year, limit)
        results.extend(oa_results)
    except Exception as e:
        print("OpenAlex error:", e)

    try:
        cr_results = fetch_crossref(query, from_year, to_year, limit)
        results.extend(cr_results)
    except Exception as e:
        print("CrossRef error:", e)

    results = deduplicate_by_doi(results)

    titles = [r["title"] for r in results if r.get("title")]

    unigram_trends = extract_keywords(titles, top=top)
    bigram_trends = extract_bigrams(titles, top=top)
    trigram_trends = extract_trigrams(titles, top=top)

    yearly = trends_per_year(results, top=min(5, top))

    return {
        "query": query,
        "filters": {
            "from_year": from_year,
            "to_year": to_year,
        },
        "total_papers": len(results),
        "top": top,
        "unigrams": unigram_trends,
        "bigrams": bigram_trends,
        "trigrams": trigram_trends,
        "per_year": yearly
    }

@app.get("/v1/papers/lookup")
def lookup_paper(
    doi: str = Query(..., description="DOI of the paper, e.g. 10.1000/xyz123")
):
    # Normalisasi DOI (hapus https://doi.org/ kalau user masukin itu)
    doi_clean = doi.replace("https://doi.org/", "").strip()

    # Coba dari OpenAlex dulu
    try:
        result = fetch_openalex_by_doi(doi_clean)
        if result:
            return {
                "source": "openalex",
                "paper": result
            }
    except Exception as e:
        print("OpenAlex lookup error:", e)

    # Kalau nggak ketemu / error, coba CrossRef
    try:
        result = fetch_crossref_by_doi(doi_clean)
        if result:
            return {
                "source": "crossref",
                "paper": result
            }
    except Exception as e:
        print("CrossRef lookup error:", e)

    # Kalau dua-duanya gagal
    raise HTTPException(status_code=404, detail="Paper not found for given DOI")