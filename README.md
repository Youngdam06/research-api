# 🎓 OpenResearch API 
OpenResearch API, powered by OpenAlex and Crossref. This API provides simple endpoints for searching papers and looking up metadata by DOI, 
with optional basic keyword and n-gram analysis from paper titles for exploration. Get unified academic metadata from OpenAlex & Crossref with a single request. 
No more parsing multiple providers—one schema to rule them all.

Stop parsing multiple sources. Get unified academic data in one schema.

OpenResearch API simplifies your research workflow by aggregating data from OpenAlex and Crossref into a single, normalized JSON response. Whether you're building an AI tool, a research dashboard, or a data pipeline, we handle the deduplication and schema mapping for you.

Why use OpenResearch API?

- Unified Search: One query to fetch results from multiple providers simultaneously.

- Auto-Deduplication: We use DOI as a unique ID to remove repeated entries.

- Normalized Metadata: Title, authors, and years are always in the same format.

- Trend Insights: Instant n-gram analysis (unigrams, bigrams, trigrams) to track research topics over time.

## What OpenResearch API Offers
- Keyword-based academic paper search

- DOI metadata lookup

- Lightweight keyword trend analysis

- Clean JSON responses with consistent structure
## Avalable Endpoints 
| Endpoint | Method | Description |
|----------|--------|------------|
| /v1/papers/search | GET | Search papers by keyword |
| /v1/papers/lookup | GET | Lookup paper metadata by DOI |
| /v1/trends | GET | Get keyword publication trends |

## Use Cases
- 🧠 AI builders doing data enrichment.

- 📚 Research tools and academic platforms.

- 🚀 Startups building discovery, analysis, or reference features.

- 🔧 Developers who want quick access to paper metadata without managing multiple APIs.

##  Rate Limits

Rate limits depend on your RapidAPI subscription plan.

See RapidAPI pricing page for details.

## Try It on RapidAPI

Access the full documentation and subscribe here:

👉 [https://rapidapi.com/fathoniadam933/api/openresearch-api]
