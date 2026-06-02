"""Paper Discovery Agent.

Searches *legal, authorised* scholarly sources for recent papers and normalises
them into :class:`~arts.models.Paper`. Only titles, abstracts and metadata are
used — no unauthorised scraping and no copying of long passages from papers.

Sources:
  * arXiv      (open access, Atom API)
  * Semantic Scholar (Graph API — metadata + abstracts)
  * Crossref   (metadata; abstracts when the publisher provides them)
  * IEEE Xplore (metadata / open-access only, used solely when an API key is set)

When every live source is unavailable (e.g. restricted network), discovery can
fall back to ``samples/sample_papers.json`` so the rest of the pipeline can run.
"""
from __future__ import annotations

import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

from ..config import REPO_ROOT, Config
from ..knowledge import get_field
from ..models import Paper
from ..utils import get_logger, read_json

log = get_logger("fetcher")

ARXIV_ENDPOINT = "http://export.arxiv.org/api/query"
SS_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search"
CROSSREF_ENDPOINT = "https://api.crossref.org/works"
IEEE_ENDPOINT = "https://ieeexploreapi.ieee.org/api/v1/search/articles"

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


def _session(mailto: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {"User-Agent": f"arabic-research-tiktok-agent/0.1 (mailto:{mailto})"}
    )
    return s


def _get(session: requests.Session, url: str, params: dict, timeout: int = 25):
    """GET with one short retry; returns the response or None on failure."""
    for attempt in range(2):
        try:
            r = session.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            log.warning("%s -> HTTP %s", url.split("//")[-1].split("/")[0], r.status_code)
            return None
        except requests.RequestException as e:
            log.warning("request error (%s/2) %s: %s", attempt + 1, url, e)
            time.sleep(1.5 * (attempt + 1))
    return None


def _within_age(pub_date: Optional[str], year: Optional[int], max_age_days: int, today: date) -> bool:
    if pub_date:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
            try:
                d = datetime.strptime(pub_date[:19] if "T" in pub_date else pub_date[:10], fmt).date()
                return (today - d).days <= max_age_days
            except ValueError:
                continue
    if year:
        # fall back to year granularity
        return (today.year - int(year)) * 365 <= max_age_days + 365
    return True


# --------------------------------------------------------------------------- #
# arXiv
# --------------------------------------------------------------------------- #
def fetch_arxiv(session, field_key: str, limit: int) -> list[Paper]:
    field = get_field(field_key)
    cats = field["arxiv_categories"]
    search = " OR ".join(f"cat:{c}" for c in cats)
    params = {
        "search_query": search,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": limit,
    }
    r = _get(session, ARXIV_ENDPOINT, params)
    if not r:
        return []
    papers: list[Paper] = []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        log.warning("arXiv parse error: %s", e)
        return []
    for entry in root.findall(f"{_ATOM}entry"):
        try:
            title = (entry.findtext(f"{_ATOM}title") or "").strip().replace("\n", " ")
            summary = (entry.findtext(f"{_ATOM}summary") or "").strip().replace("\n", " ")
            published = (entry.findtext(f"{_ATOM}published") or "").strip()
            url = (entry.findtext(f"{_ATOM}id") or "").strip()
            authors = [
                (a.findtext(f"{_ATOM}name") or "").strip()
                for a in entry.findall(f"{_ATOM}author")
            ]
            doi = entry.findtext(f"{_ARXIV}doi")
            pdf_url = None
            for link in entry.findall(f"{_ATOM}link"):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href")
            year = int(published[:4]) if published[:4].isdigit() else None
            papers.append(
                Paper(
                    title=title,
                    abstract=summary,
                    source="arxiv",
                    url=url,
                    field=field_key,
                    authors=[a for a in authors if a],
                    year=year,
                    doi=doi,
                    publication_date=published[:10] or None,
                    open_access=True,
                    license="arXiv",
                    pdf_url=pdf_url,
                    paper_id=url.rsplit("/", 1)[-1],
                )
            )
        except Exception as e:  # never let one bad entry kill the source
            log.debug("skip arXiv entry: %s", e)
    log.info("arXiv[%s]: %d papers", field_key, len(papers))
    return papers


# --------------------------------------------------------------------------- #
# Semantic Scholar
# --------------------------------------------------------------------------- #
def fetch_semantic_scholar(session, field_key: str, limit: int) -> list[Paper]:
    field = get_field(field_key)
    params = {
        "query": field["query"],
        "limit": min(limit, 100),
        "fields": "title,abstract,year,authors,externalIds,openAccessPdf,publicationDate,url,venue",
        "sort": "publicationDate:desc",
    }
    r = _get(session, SS_ENDPOINT, params)
    if not r:
        return []
    papers: list[Paper] = []
    for item in (r.json().get("data") or []):
        try:
            if not item.get("abstract") or not item.get("title"):
                continue
            ext = item.get("externalIds") or {}
            oa = item.get("openAccessPdf") or {}
            papers.append(
                Paper(
                    title=item["title"].strip(),
                    abstract=item["abstract"].strip(),
                    source="semantic_scholar",
                    url=item.get("url") or "",
                    field=field_key,
                    authors=[a.get("name", "") for a in (item.get("authors") or [])],
                    year=item.get("year"),
                    doi=ext.get("DOI"),
                    publication_date=item.get("publicationDate"),
                    open_access=bool(oa.get("url")),
                    license=(oa.get("license") if oa else None),
                    pdf_url=oa.get("url"),
                    paper_id=item.get("paperId"),
                )
            )
        except Exception as e:
            log.debug("skip SS entry: %s", e)
    log.info("semantic_scholar[%s]: %d papers", field_key, len(papers))
    return papers


# --------------------------------------------------------------------------- #
# Crossref
# --------------------------------------------------------------------------- #
def _strip_jats(text: str) -> str:
    import re

    text = re.sub(r"</?jats:[^>]+>", "", text)
    return re.sub(r"<[^>]+>", "", text).strip()


def fetch_crossref(session, field_key: str, limit: int, mailto: str, from_date: str) -> list[Paper]:
    field = get_field(field_key)
    params = {
        "query": field["query"],
        "rows": limit,
        "sort": "published",
        "order": "desc",
        "filter": f"from-pub-date:{from_date},type:journal-article",
        "select": "title,author,issued,DOI,URL,abstract,publisher,container-title,license",
        "mailto": mailto,
    }
    r = _get(session, CROSSREF_ENDPOINT, params)
    if not r:
        return []
    papers: list[Paper] = []
    for item in (r.json().get("message", {}).get("items") or []):
        try:
            title_list = item.get("title") or []
            if not title_list:
                continue
            abstract = _strip_jats(item.get("abstract", "")) if item.get("abstract") else ""
            issued = (item.get("issued", {}).get("date-parts") or [[None]])[0]
            year = issued[0] if issued and issued[0] else None
            pub_date = "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(issued)) if year else None
            authors = [
                " ".join(x for x in [a.get("given"), a.get("family")] if x)
                for a in (item.get("author") or [])
            ]
            lic = (item.get("license") or [{}])[0].get("URL")
            papers.append(
                Paper(
                    title=title_list[0].strip(),
                    abstract=abstract,
                    source="crossref",
                    url=item.get("URL") or "",
                    field=field_key,
                    authors=[a for a in authors if a],
                    year=year,
                    institution=(item.get("publisher") or None),
                    doi=item.get("DOI"),
                    publication_date=pub_date,
                    open_access=bool(lic),
                    license=lic,
                    paper_id=item.get("DOI"),
                )
            )
        except Exception as e:
            log.debug("skip Crossref entry: %s", e)
    log.info("crossref[%s]: %d papers", field_key, len(papers))
    return papers


# --------------------------------------------------------------------------- #
# IEEE Xplore (metadata / open-access only; opt-in via API key)
# --------------------------------------------------------------------------- #
def fetch_ieee(session, field_key: str, limit: int, api_key: str) -> list[Paper]:
    field = get_field(field_key)
    params = {
        "apikey": api_key,
        "querytext": field["query"],
        "max_records": min(limit, 25),
        "sort_field": "publication_date",
        "sort_order": "desc",
        "format": "json",
    }
    r = _get(session, IEEE_ENDPOINT, params)
    if not r:
        return []
    papers: list[Paper] = []
    for item in (r.json().get("articles") or []):
        try:
            oa = str(item.get("access_type", "")).upper() == "OPEN_ACCESS"
            papers.append(
                Paper(
                    title=(item.get("title") or "").strip(),
                    # IEEE: use the provided abstract metadata only.
                    abstract=(item.get("abstract") or "").strip(),
                    source="ieee",
                    url=item.get("html_url") or item.get("pdf_url") or "",
                    field=field_key,
                    authors=[a.get("full_name", "") for a in (item.get("authors", {}).get("authors") or [])],
                    year=int(item["publication_year"]) if item.get("publication_year") else None,
                    institution=item.get("publisher"),
                    doi=item.get("doi"),
                    publication_date=item.get("publication_date"),
                    open_access=oa,
                    license=("IEEE Open Access" if oa else "IEEE (metadata only)"),
                    paper_id=str(item.get("article_number")),
                )
            )
        except Exception as e:
            log.debug("skip IEEE entry: %s", e)
    log.info("ieee[%s]: %d papers", field_key, len(papers))
    return papers


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _dedupe(papers: list[Paper]) -> list[Paper]:
    seen_doi: set[str] = set()
    seen_title: set[str] = set()
    out: list[Paper] = []
    for p in papers:
        doi = (p.doi or "").lower().strip()
        tkey = "".join(ch for ch in p.title.lower() if ch.isalnum())[:80]
        if doi and doi in seen_doi:
            continue
        if tkey and tkey in seen_title:
            continue
        if doi:
            seen_doi.add(doi)
        if tkey:
            seen_title.add(tkey)
        out.append(p)
    return out


def load_samples(field_filter: Optional[list[str]] = None) -> list[Paper]:
    path = REPO_ROOT / "samples" / "sample_papers.json"
    if not path.exists():
        return []
    papers = [Paper.from_dict(d) for d in read_json(path)]
    if field_filter:
        papers = [p for p in papers if p.field in field_filter]
    return papers


def discover(cfg: Config) -> list[Paper]:
    """Discover candidate papers across the configured fields and sources."""
    sources = cfg.get("discovery.sources", ["arxiv", "semantic_scholar", "crossref"])
    per_field = int(cfg.get("discovery.per_field_results", 15))
    max_age = int(cfg.get("discovery.max_age_days", 45))
    mailto = cfg.get("discovery.mailto", "research-agent@example.com")
    ieee_key = __import__("os").getenv("IEEE_API_KEY")
    today = date.today()
    from_date = (today - timedelta(days=max_age)).isoformat()

    session = _session(mailto)
    collected: list[Paper] = []
    for field_key in cfg.fields:
        if "arxiv" in sources:
            collected += fetch_arxiv(session, field_key, per_field)
        if "semantic_scholar" in sources:
            collected += fetch_semantic_scholar(session, field_key, per_field)
        if "crossref" in sources:
            collected += fetch_crossref(session, field_key, per_field, mailto, from_date)
        if "ieee" in sources and ieee_key:
            collected += fetch_ieee(session, field_key, per_field, ieee_key)

    # keep only recent + has an abstract we are allowed to use
    fresh = [
        p
        for p in collected
        if p.abstract and _within_age(p.publication_date, p.year, max_age, today)
    ]
    fresh = _dedupe(fresh)
    log.info("discovered %d candidate papers (after filtering)", len(fresh))

    if not fresh and cfg.get("discovery.allow_sample_fallback", True):
        log.warning("no live results — falling back to offline sample fixtures")
        fresh = load_samples(cfg.fields)
    return fresh
