"""
Recipe Dredger - Enhanced Public Edition
Intelligent recipe scraper for Mealie/Tandoor with optimized performance and reliability.
Usage: python3 dredger.py [--dry-run] [--limit 10] [--sites my_sites.json] [--no-cache] [--version]
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from langdetect import detect, DetectorFactory
import json
import time
import os
import random
import re
import logging
import sys
import argparse
import signal
from urllib.parse import urlparse
from dotenv import load_dotenv
from typing import Optional, Set, List, Dict, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

# --- CONSTANTS ---
VERSION = "1.0.0-beta.11"

# --- OPTIONAL VISUALS ---
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# --- LOAD ENV VARS ---
load_dotenv()

# --- LOGGING CONFIGURATION ---
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("dredger")

# --- CONFIGURATION DEFAULTS ---
DEFAULT_TARGET = int(os.getenv('TARGET_RECIPES_PER_SITE', 50))
DEFAULT_DEPTH = int(os.getenv('SCAN_DEPTH', 1000))
DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'

# --- PLATFORM SETTINGS ---
MEALIE_ENABLED = os.getenv('MEALIE_ENABLED', 'true').lower() == 'true'
MEALIE_URL = os.getenv('MEALIE_URL', 'http://localhost:9000').rstrip('/')
MEALIE_API_TOKEN = os.getenv('MEALIE_API_TOKEN', 'your-token')

TANDOOR_ENABLED = os.getenv('TANDOOR_ENABLED', 'false').lower() == 'true'
TANDOOR_URL = os.getenv('TANDOOR_URL', 'http://localhost:8080').rstrip('/')
TANDOOR_API_KEY = os.getenv('TANDOOR_API_KEY', 'your-key')

# Rate limiting
DEFAULT_CRAWL_DELAY = float(os.getenv('CRAWL_DELAY', 2.0))
RESPECT_ROBOTS_TXT = os.getenv('RESPECT_ROBOTS_TXT', 'true').lower() == 'true'

# Notifications
NOTIFICATION_WEBHOOK_URL = os.getenv('NOTIFICATION_WEBHOOK_URL', '').strip()

# Library sync
SYNC_LIBRARY = os.getenv('SYNC_LIBRARY', 'true').lower() == 'true'

# Language filtering: accepts a single ISO code ('en') or a comma-separated list
# ('en,pt' or 'en, pt'). Empty value disables the filter.
def parse_language_filter(raw: str) -> List[str]:
    if not raw:
        return []
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        raw = raw[1:-1]
    return [code.strip().lower() for code in raw.split(',') if code.strip()]


LANGUAGE_FILTER: List[str] = parse_language_filter(os.getenv('LANGUAGE_FILTER', ''))

# Seed langdetect for reproducible results
DetectorFactory.seed = 0

# Memory settings
os.makedirs("data", exist_ok=True)
REJECT_FILE = "data/rejects.json"
IMPORTED_FILE = "data/imported.json"
RETRY_FILE = "data/retry_queue.json"
STATS_FILE = "data/stats.json"
SITEMAP_CACHE_FILE = "data/sitemap_cache.json"
CACHE_EXPIRY_DAYS = int(os.getenv('CACHE_EXPIRY_DAYS', 7))

# --- TUNING CONSTANTS ---
MAX_SUB_SITEMAPS = 3
FLUSH_THRESHOLD = 50
SITEMAP_TIMEOUT = 10
IMPORT_TIMEOUT = 20
ROBOTS_TXT_TIMEOUT = 5
MAX_SITEMAP_DEPTH = 2
KNOWN_RECIPE_CLASSES = ['wp-recipe-maker', 'tasty-recipes', 'mv-create-card', 'recipe-card']

# Retry queue tuning (overridable via env)
MAX_RETRY_ATTEMPTS = int(os.getenv('MAX_RETRY_ATTEMPTS', 3))
MIN_RETRY_INTERVAL_HOURS = float(os.getenv('MIN_RETRY_INTERVAL_HOURS', 1))



# --- FALLBACK LIST (10 Major Sites) ---
# Note: The full categorized list (120+ sites) is in sites.json
DEFAULT_SITES = [
    "https://www.seriouseats.com",
    "https://www.bonappetit.com",
    "https://www.recipetineats.com",
    "https://smittenkitchen.com",
    "https://minimalistbaker.com",
    "https://www.justonecookbook.com",
    "https://www.woksoflife.com",
    "https://sallysbakingaddiction.com",
    "https://www.skinnytaste.com",
    "https://www.budgetbytes.com"
]

# --- PARANOID FILTERS ---
LISTICLE_REGEX = re.compile(r'(\d+)-(best|top|must|favorite|easy|healthy|quick|ways|things)', re.IGNORECASE)
BAD_KEYWORDS = ["roundup", "collection", "guide", "review", "giveaway", "shop", "store", "product"]

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class RecipeCandidate:
    url: str
    priority: int = 0 
    
    def __hash__(self):
        return hash(self.url)
    
    def __eq__(self, other):
        return self.url == other.url if isinstance(other, RecipeCandidate) else self.url == other

@dataclass
class SiteStats:
    site_url: str
    recipes_found: int = 0
    recipes_imported: int = 0
    recipes_rejected: int = 0
    errors: int = 0
    last_run: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)

# ============================================================================
# PERSISTENT STORAGE MANAGER
# ============================================================================

class StorageManager:
    def __init__(self):
        self.rejects: Set[str] = self._load_json_set(REJECT_FILE)
        self.imported: Set[str] = self._load_json_set(IMPORTED_FILE)
        self.retry_queue: Dict[str, dict] = self._load_json_dict(RETRY_FILE)
        self.stats: Dict[str, dict] = self._load_json_dict(STATS_FILE)
        self.sitemap_cache: Dict[str, dict] = self._load_json_dict(SITEMAP_CACHE_FILE)
        
        self._changes_since_flush = 0
        self._flush_threshold = FLUSH_THRESHOLD
        
    def _load_json_set(self, filename: str) -> Set[str]:
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    return set(json.load(f))
            except Exception as e:
                logger.warning(f"Error loading {filename}: {e}")
        return set()
    
    def _load_json_dict(self, filename: str) -> dict:
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading {filename}: {e}")
        return {}
    
    def _atomic_write_json(self, filename: str, data):
        # Write to sibling .tmp then os.replace — POSIX rename is atomic, so a
        # crash mid-serialize leaves the prior file intact instead of empty.
        tmp = filename + ".tmp"
        try:
            with open(tmp, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, filename)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise

    def _save_json_set(self, filename: str, data_set: Set[str]):
        self._atomic_write_json(filename, list(data_set))

    def _save_json_dict(self, filename: str, data_dict: dict):
        self._atomic_write_json(filename, data_dict)
    
    def add_imported(self, url: str):
        self.imported.add(url)
        self._changes_since_flush += 1
        self._auto_flush()
    
    def add_reject(self, url: str):
        self.rejects.add(url)
        self._changes_since_flush += 1
        self._auto_flush()
    
    def add_retry(self, url: str, reason: str):
        self.retry_queue[url] = {
            'reason': reason,
            'attempts': 0,
            'last_attempt': datetime.now().isoformat()
        }
        self._changes_since_flush += 1
        self._auto_flush()
    
    def update_stats(self, site_url: str, stats: SiteStats):
        self.stats[site_url] = stats.to_dict()
        self._changes_since_flush += 1
        self._auto_flush()
    
    def get_cached_sitemap(self, site_url: str) -> Optional[dict]:
        if site_url not in self.sitemap_cache: 
            return None
        
        cache_entry = self.sitemap_cache[site_url]
        cached_time = datetime.fromisoformat(cache_entry['timestamp'])
        
        if datetime.now() - cached_time > timedelta(days=CACHE_EXPIRY_DAYS):
            return None
        
        return cache_entry
    
    def cache_sitemap(self, site_url: str, sitemap_url: str, urls: List[str]):
        self.sitemap_cache[site_url] = {
            'sitemap_url': sitemap_url,
            'urls': urls,
            'timestamp': datetime.now().isoformat()
        }
        self._changes_since_flush += 1
        self._auto_flush()
    
    def _auto_flush(self):
        if self._changes_since_flush >= self._flush_threshold:
            self.flush_all()
    
    def flush_all(self):
        self._save_json_set(REJECT_FILE, self.rejects)
        self._save_json_set(IMPORTED_FILE, self.imported)
        self._save_json_dict(RETRY_FILE, self.retry_queue)
        self._save_json_dict(STATS_FILE, self.stats)
        self._save_json_dict(SITEMAP_CACHE_FILE, self.sitemap_cache)
        self._changes_since_flush = 0

# ============================================================================
# GRACEFUL KILLER
# ============================================================================

class GracefulKiller:
    """Catches Docker stop signals to allow safe shutdown."""
    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        signal_name = 'SIGINT (Ctrl+C)' if signum == signal.SIGINT else 'SIGTERM (Docker Stop)'
        logger.info(f"🛑 Received {signal_name}. Initiating graceful shutdown...")
        self.kill_now = True

# ============================================================================
# RATE LIMITER (FIXED: Respects HTTP vs HTTPS scheme)
# ============================================================================
class RateLimiter:
    def __init__(self):
        self.last_request: Dict[str, float] = {}
        self.crawl_delays: Dict[str, float] = {}
        self.session = get_session()
    
    def get_domain(self, url: str) -> str:
        return urlparse(url).netloc
    
    def get_crawl_delay(self, url: str) -> float:
        domain = self.get_domain(url)
        if domain in self.crawl_delays:
            return self.crawl_delays[domain]
        
        delay = DEFAULT_CRAWL_DELAY
        if RESPECT_ROBOTS_TXT:
            try:
                # QC FIX: Use the actual scheme (http or https) from the URL
                parsed = urlparse(url)
                scheme = parsed.scheme if parsed.scheme else "https"
                
                # If checking localhost or LAN IP, use HTTP unless specified otherwise
                if "192.168" in domain or "127.0.0.1" in domain or "localhost" in domain:
                    if scheme == "https": scheme = "http" # Fallback to HTTP for LAN if unsure

                r = self.session.get(f"{scheme}://{domain}/robots.txt", timeout=ROBOTS_TXT_TIMEOUT)
                if r.status_code == 200:
                    for line in r.text.splitlines():
                        if line.lower().startswith('crawl-delay:'):
                            try:
                                delay = float(line.split(':')[1].strip())
                                break
                            except ValueError: 
                                pass
            except Exception: 
                pass
        
        self.crawl_delays[domain] = delay
        return delay
    
    def wait_if_needed(self, url: str):
        domain = self.get_domain(url)
        delay = self.get_crawl_delay(url) # Pass full URL so we know the scheme
        
        if domain in self.last_request:
            elapsed = time.time() - self.last_request[domain]
            if elapsed < delay:
                # Add jitter (0.5x to 1.5x) to mimic human variance
                jitter = random.uniform(0.5, 1.5)
                sleep_time = (delay - elapsed) * jitter
                time.sleep(sleep_time)
        
        self.last_request[domain] = time.time()

# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

def get_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3, 
        backoff_factor=1, 
        status_forcelist=[500, 502, 503, 504, 429],
        allowed_methods=["HEAD", "GET", "POST"]
    )
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) RecipeDredger/{VERSION}'
    })
    return session

# ============================================================================
# SITEMAP CRAWLER (WITH GARBAGE FILTER)
# ============================================================================

class SitemapCrawler:
    def __init__(self, session: requests.Session, storage: StorageManager):
        self.session = session
        self.storage = storage
    
    def find_sitemap(self, base_url: str) -> Optional[str]:
        # 1. Check robots.txt
        try:
            r = self.session.get(f"{base_url}/robots.txt", timeout=ROBOTS_TXT_TIMEOUT)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    if "Sitemap:" in line:
                        return line.split("Sitemap:")[1].strip()
        except Exception as e: 
            logger.debug(f"robots.txt fetch failed for {base_url}: {e}")
        
        # 2. Check standard candidates
        candidates = [
            f"{base_url}/sitemap_index.xml", 
            f"{base_url}/sitemap.xml",
            f"{base_url}/wp-sitemap.xml", 
            f"{base_url}/post-sitemap.xml",
            f"{base_url}/recipe-sitemap.xml"
        ]
        
        for url in candidates:
            try:
                r = self.session.head(url, timeout=ROBOTS_TXT_TIMEOUT)
                if r.status_code == 200: 
                    return url
            except Exception as e: 
                logger.debug(f"Sitemap candidate check failed for {url}: {e}")
        
        return None
    
    def fetch_sitemap_urls(self, url: str, depth: int = 0) -> List[str]:
        if depth > MAX_SITEMAP_DEPTH: 
            return []
        
        try:
            r = self.session.get(url, timeout=SITEMAP_TIMEOUT)
            if r.status_code != 200: 
                return []
            
            # Use BeautifulSoup XML parser for robust parsing
            soup = BeautifulSoup(r.content, 'xml')
            all_urls = []

            # Handle Index Sitemaps (nested)
            if soup.find('sitemap'):
                sub_maps = [loc.text for loc in soup.find_all('loc')]
                targets = [s for s in sub_maps if 'post' in s or 'recipe' in s]
                if not targets: 
                    targets = sub_maps
                
                for sub in targets[:MAX_SUB_SITEMAPS]: 
                    all_urls.extend(self.fetch_sitemap_urls(sub, depth + 1))
                return all_urls
            
            # Handle URL Sitemaps
            if soup.find('url'):
                 raw_urls = [loc.text for loc in soup.find_all('loc')]
                 
                 # --- THE GARBAGE FILTER ---
                 clean_urls = []
                 # Define extensions to skip immediately
                 junk_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf', '.zip'}
                 
                 for u in raw_urls:
                     u_lower = u.lower()
                     # 1. Drop image/binary files immediately
                     if any(u_lower.endswith(ext) for ext in junk_extensions):
                         continue
                     # 2. Drop obvious non-recipe pages
                     if any(x in u_lower for x in ['/privacy-policy', '/contact', '/about', '/login', '/wp-content/', '/cdn-cgi/']):
                         continue
                     clean_urls.append(u)
                 
                 return clean_urls
            
            return []

        except Exception as e:
            logger.warning(f"Sitemap parse error {url}: {e}")
            return []
    
    def get_urls_for_site(self, site_url: str, force_refresh: bool = False) -> List[RecipeCandidate]:
        if not force_refresh:
            cached = self.storage.get_cached_sitemap(site_url)
            if cached:
                return [RecipeCandidate(url=u) for u in cached['urls']]
        
        sitemap_url = self.find_sitemap(site_url)
        if not sitemap_url: 
            return []
        
        urls = self.fetch_sitemap_urls(sitemap_url)
        self.storage.cache_sitemap(site_url, sitemap_url, urls)
        return [RecipeCandidate(url=u) for u in urls]

# ============================================================================
# RECIPE VERIFIER
# ============================================================================
def _contains_recipe_type(node) -> bool:
    """Walk a JSON-LD payload looking for an @type == 'Recipe' object.

    Handles three real-world shapes:
      {"@type": "Recipe", ...}
      {"@type": ["Recipe", "..."], ...}
      {"@graph": [..., {"@type": "Recipe"}, ...]}
    """
    if isinstance(node, dict):
        t = node.get('@type')
        if t == 'Recipe' or (isinstance(t, list) and 'Recipe' in t):
            return True
        for v in node.values():
            if _contains_recipe_type(v):
                return True
    elif isinstance(node, list):
        for v in node:
            if _contains_recipe_type(v):
                return True
    return False


class RecipeVerifier:
    def __init__(self, session: requests.Session):
        self.session = session
    
    def is_paranoid_skip(self, url: str, soup: Optional[BeautifulSoup] = None) -> Optional[str]:
        try:
            path = urlparse(url).path
            slug = path.strip("/").split("/")[-1].lower()

            if LISTICLE_REGEX.search(slug):
                return f"Listicle detected: {slug}"

            # Token-based match (split slug on hyphen) to avoid false positives like
            # "shopska-salad" matching "shop" or "productive-week" matching "product".
            slug_tokens = set(re.split(r'[-_]+', slug))
            for kw in BAD_KEYWORDS:
                if kw in slug_tokens:
                    return f"Bad keyword: {kw}"
            
            if soup:
                title = soup.title.string.lower() if soup.title else ""
                if "best recipes" in title or "top 10" in title: 
                    return "Listicle title"
        
        except Exception as e: 
            logger.debug(f"Paranoid skip check error for {url}: {e}")
        
        return None
    
    def verify_recipe(self, url: str) -> Tuple[bool, Optional[BeautifulSoup], Optional[str]]:
        try:
            r = self.session.get(url, timeout=SITEMAP_TIMEOUT)
            if r.status_code != 200: 
                return False, None, f"HTTP {r.status_code}"
            
            # Recipe detection
            is_recipe = False
            soup = BeautifulSoup(r.content, 'lxml')

            # 1. Proper JSON-LD parsing — only ld+json scripts, only true Recipe @type
            #    (handles @graph variants common on WordPress).
            for script in soup.find_all('script', type='application/ld+json'):
                if not script.string:
                    continue
                try:
                    data = json.loads(script.string)
                except (ValueError, TypeError):
                    continue
                if _contains_recipe_type(data):
                    is_recipe = True
                    break

            # 2. Fall back to recipe-plugin CSS classes
            if not is_recipe:
                if soup.find(class_=lambda x: x and any(cls in x for cls in KNOWN_RECIPE_CLASSES)):
                    is_recipe = True
            
            if not is_recipe:
                return False, soup, "No recipe detected"

            # Paranoid checks
            skip_reason = self.is_paranoid_skip(url, soup)
            if skip_reason: 
                return False, soup, skip_reason
            
            # Language filter — accepts one or many ISO codes
            if LANGUAGE_FILTER:
                try:
                    text = soup.get_text(separator=' ', strip=True)[:1000]
                    if len(text) > 50:  # Need enough text for reliable detection
                        detected_lang = detect(text)
                        if detected_lang not in LANGUAGE_FILTER:
                            allowed = ','.join(LANGUAGE_FILTER)
                            return False, soup, f"Language mismatch: detected '{detected_lang}', want one of '{allowed}'"
                except Exception as e:
                    logger.debug(f"Language detection failed for {url}: {e}")
            
            return True, soup, None
        
        except Exception as e:
            return False, None, f"Exception: {str(e)}"

# ============================================================================
# IMPORT MANAGER (AUTO-DETECT MEALIE VERSION)
# ============================================================================

def _build_tandoor_create_payload(recipe: dict, fallback_url: str) -> dict:
    """Map a `recipe-from-source` scrape result onto a `/api/recipe/` create body.

    The scraped recipe is already close to the create shape (nested steps with
    ingredients, keywords). We only need to:
      - guarantee `steps` is present (the create serializer requires it),
      - set `internal=True` and a `source_url`,
      - clean keywords: a null `id` confuses Tandoor's writable-nested PK lookup,
        and `import_keyword` is not a model field — keep just name/label.
    Image upload and recipe `properties` are intentionally omitted: images need a
    separate multipart call and properties reference space-specific property_type
    ids that may not exist. The recipe still imports without them.
    """
    keywords = []
    for kw in recipe.get('keywords') or []:
        name = kw.get('name') or kw.get('label')
        if not name:
            continue
        keywords.append({"name": name, "label": kw.get('label') or name})

    return {
        "name": recipe.get('name') or "Untitled",
        "description": recipe.get('description') or "",
        "internal": True,
        "source_url": recipe.get('source_url') or fallback_url,
        "servings": recipe.get('servings') or 1,
        "servings_text": recipe.get('servings_text') or "",
        "working_time": recipe.get('working_time') or 0,
        "waiting_time": recipe.get('waiting_time') or 0,
        "steps": recipe.get('steps') or [],
        "keywords": keywords,
    }


class ImportManager:
    def __init__(self, session: requests.Session, storage: StorageManager, rate_limiter: RateLimiter, dry_run: bool):
        self.session = session
        self.storage = storage
        self.rate_limiter = rate_limiter
        self.dry_run = dry_run
        # Cache the working endpoint so we don't guess every time
        self.working_endpoint = None

    def import_to_mealie(self, url: str) -> Tuple[bool, Optional[str]]:
        if self.dry_run:
            logger.info(f"   [DRY RUN] Would import to Mealie: {url}")
            return True, None
        
        headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
        
        # 1. Determine endpoints to try
        # If we already found the right one, use it. Otherwise, try New (v2/v3) then Old (v1)
        if self.working_endpoint:
            endpoints = [self.working_endpoint]
        else:
            endpoints = ["/api/recipes/create/url", "/api/recipes/create-url"]

        self.rate_limiter.wait_if_needed(MEALIE_URL)
        
        last_error = None

        # Auth-failure on the FIRST guess is ambiguous (wrong endpoint vs bad token),
        # so we only try the next endpoint when there's another one to try AND we
        # haven't yet found a working endpoint. If both fail with 401/403, the
        # error is surfaced.
        trying_multiple = len(endpoints) > 1 and self.working_endpoint is None

        for idx, endpoint in enumerate(endpoints):
            try:
                full_url = f"{MEALIE_URL}{endpoint}"
                r = self.session.post(full_url, headers=headers, json={"url": url}, timeout=IMPORT_TIMEOUT)

                # If 404/405, the endpoint is wrong/deprecated. Try the next one.
                if r.status_code in [404, 405]:
                    last_error = f"HTTP {r.status_code} on {endpoint}"
                    continue

                # If 401/403 on the first guess and we have another endpoint left,
                # treat as "wrong endpoint, try the other" rather than caching a
                # broken default.
                if r.status_code in [401, 403] and trying_multiple and idx < len(endpoints) - 1:
                    last_error = f"HTTP {r.status_code} on {endpoint}"
                    continue

                # Success! Save the working endpoint for future requests.
                if self.working_endpoint is None:
                    self.working_endpoint = endpoint
                    logger.debug(f"   🎯 Auto-Detected Mealie API: {endpoint}")

                if r.status_code in [200, 201]:
                    logger.info(f"   ✅ [Mealie] Imported: {url}")
                    return True, None
                elif r.status_code == 409:
                    logger.info(f"   ⚠️ [Mealie] Duplicate: {url}")
                    return True, None
                else:
                    return False, f"HTTP {r.status_code}"
            
            except Exception as e:
                last_error = str(e)
                continue
        
        return False, f"All API attempts failed. Last error: {last_error}"

    def import_to_tandoor(self, url: str) -> Tuple[bool, Optional[str]]:
        """Import a recipe into Tandoor (v2 API).

        Tandoor v2 dropped the old one-shot `/api/recipe/import-url/` endpoint
        (it now 405s — see issue #6). The current flow is two steps:
          1. POST /api/recipe-from-source/  -> scrapes the URL, returns parsed JSON
             (but does NOT persist a normal blog URL).
          2. POST /api/recipe/              -> creates the recipe from that JSON.
        Some sources (YouTube, Tandoor share links) are persisted by step 1
        itself, which returns a `recipe_id`; in that case we skip step 2.
        """
        if self.dry_run:
            logger.info(f"   [DRY RUN] Would import to Tandoor: {url}")
            return True, None

        headers = {"Authorization": f"Bearer {TANDOOR_API_KEY}"}
        try:
            self.rate_limiter.wait_if_needed(TANDOOR_URL)

            # --- Step 1: scrape the URL into recipe JSON ---
            scrape = self.session.post(
                f"{TANDOOR_URL}/api/recipe-from-source/",
                headers=headers,
                json={"url": url},
                timeout=IMPORT_TIMEOUT,
            )
            if scrape.status_code not in (200, 201):
                return False, f"HTTP {scrape.status_code} on /api/recipe-from-source/"

            payload = scrape.json()
            if payload.get('error'):
                return False, payload.get('msg') or "scrape error"

            # Already persisted by the scrape view (YouTube / Tandoor share link)
            if payload.get('recipe_id'):
                logger.info(f"   ✅ [Tandoor] Imported: {url}")
                return True, None

            # Already in the library for this source_url — treat as success
            if payload.get('duplicates'):
                logger.info(f"   ⚠️ [Tandoor] Duplicate: {url}")
                return True, None

            recipe = payload.get('recipe')
            if not recipe:
                return False, "No recipe data returned from scrape"

            # --- Step 2: persist the scraped recipe ---
            create_body = _build_tandoor_create_payload(recipe, fallback_url=url)
            created = self.session.post(
                f"{TANDOOR_URL}/api/recipe/",
                headers=headers,
                json=create_body,
                timeout=IMPORT_TIMEOUT,
            )
            if created.status_code in (200, 201):
                logger.info(f"   ✅ [Tandoor] Imported: {url}")
                return True, None
            return False, f"HTTP {created.status_code} on /api/recipe/"

        except Exception as e:
            return False, str(e)
    
    def import_recipe(self, url: str) -> bool:
        success = False
        
        if MEALIE_ENABLED:
            m_ok, _ = self.import_to_mealie(url)
            success = success or m_ok
        
        if TANDOOR_ENABLED:
            t_ok, _ = self.import_to_tandoor(url)
            success = success or t_ok
            
        return success

# ============================================================================
# CLI & MAIN
# ============================================================================

def validate_config():
    """Check for common misconfigurations."""
    issues = []
    
    if not MEALIE_ENABLED and not TANDOOR_ENABLED and not DRY_RUN:
        issues.append("⚠️  Warning: Both Mealie and Tandoor are disabled. Nothing will be imported!")
    
    if MEALIE_ENABLED and MEALIE_API_TOKEN == 'your-token':
        issues.append("⚠️  Warning: MEALIE_API_TOKEN not configured (still set to default)")
        
    if TANDOOR_ENABLED and TANDOOR_API_KEY == 'your-key':
        issues.append("⚠️  Warning: TANDOOR_API_KEY not configured (still set to default)")
        
    for issue in issues:
        logger.warning(issue)

def check_connectivity(session: requests.Session):
    """Verify API connectivity before starting the crawl. Exit early on failure."""
    if MEALIE_ENABLED and MEALIE_API_TOKEN != 'your-token':
        try:
            headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
            r = session.get(f"{MEALIE_URL}/api/recipes?page=1&perPage=1", headers=headers, timeout=ROBOTS_TXT_TIMEOUT)
            if r.status_code == 200:
                logger.info(f"   ✅ Mealie connectivity OK ({MEALIE_URL})")
            elif r.status_code == 401:
                logger.critical(f"❌ Mealie API token is invalid (HTTP 401). Check MEALIE_API_TOKEN.")
                sys.exit(1)
            else:
                logger.warning(f"⚠️  Mealie returned HTTP {r.status_code} — proceeding anyway")
        except Exception as e:
            logger.critical(f"❌ Cannot reach Mealie at {MEALIE_URL}: {e}")
            sys.exit(1)
    
    if TANDOOR_ENABLED and TANDOOR_API_KEY != 'your-key':
        try:
            headers = {"Authorization": f"Bearer {TANDOOR_API_KEY}"}
            r = session.get(f"{TANDOOR_URL}/api/recipe/?page=1&limit=1", headers=headers, timeout=ROBOTS_TXT_TIMEOUT)
            if r.status_code == 200:
                logger.info(f"   ✅ Tandoor connectivity OK ({TANDOOR_URL})")
            elif r.status_code in [401, 403]:
                logger.critical(f"❌ Tandoor API key is invalid (HTTP {r.status_code}). Check TANDOOR_API_KEY.")
                sys.exit(1)
            else:
                logger.warning(f"⚠️  Tandoor returned HTTP {r.status_code} — proceeding anyway")
        except Exception as e:
            logger.critical(f"❌ Cannot reach Tandoor at {TANDOOR_URL}: {e}")
            sys.exit(1)

def sync_existing_library(session: requests.Session, storage: StorageManager):
    """Fetch URLs already in Mealie/Tandoor to avoid duplicate import attempts."""
    synced = 0
    
    if MEALIE_ENABLED and MEALIE_API_TOKEN != 'your-token':
        headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
        page = 1
        while True:
            try:
                r = session.get(f"{MEALIE_URL}/api/recipes?page={page}&perPage=100", headers=headers, timeout=SITEMAP_TIMEOUT)
                if r.status_code != 200:
                    break
                items = r.json().get('items', [])
                if not items:
                    break
                for item in items:
                    url = item.get('orgURL') or item.get('originalURL', '')
                    if url and url.startswith('http'):
                        storage.imported.add(url)
                        synced += 1
                page += 1
            except Exception as e:
                logger.warning(f"Library sync stopped (page {page}): {e}")
                break
    
    if synced > 0:
        logger.info(f"   📚 Synced {synced} existing library URLs")

def process_candidate(url: str,
                      storage: StorageManager,
                      importer: 'ImportManager',
                      verifier: 'RecipeVerifier',
                      rate_limiter: 'RateLimiter',
                      site_stats: dict) -> str:
    """Verify and import a single candidate URL.

    Returns one of: 'skipped', 'imported', 'rejected', 'retry'.
    On import failure the URL is enqueued in the retry queue rather than dropped.
    """
    if url in storage.imported or url in storage.rejects:
        return 'skipped'

    rate_limiter.wait_if_needed(url)
    is_recipe, _soup, error = verifier.verify_recipe(url)

    if not is_recipe:
        storage.add_reject(url)
        site_stats['rejected'] += 1
        return 'rejected'

    if importer.import_recipe(url):
        storage.add_imported(url)
        site_stats['imported'] += 1
        return 'imported'

    # Import failure -> queue for retry instead of dropping silently
    storage.add_retry(url, reason='import_failed')
    site_stats['errors'] += 1
    return 'retry'


def process_retry_queue(storage: StorageManager,
                        importer,
                        verifier: 'RecipeVerifier',
                        rate_limiter: 'RateLimiter',
                        killer: Optional['GracefulKiller'] = None) -> int:
    """Process pending retries from previous runs. Returns count of successful imports.

    `killer.kill_now` is checked between URLs so a SIGTERM during the retry phase
    stops the loop immediately instead of draining every eligible URL.
    """
    if not storage.retry_queue:
        return 0

    imported_count = 0
    completed_urls = []

    eligible = []
    for url, info in storage.retry_queue.items():
        if info.get('attempts', 0) >= MAX_RETRY_ATTEMPTS:
            storage.add_reject(url)
            completed_urls.append(url)
            continue

        last_attempt = info.get('last_attempt', '')
        if last_attempt:
            try:
                last_time = datetime.fromisoformat(last_attempt)
                if datetime.now() - last_time < timedelta(hours=MIN_RETRY_INTERVAL_HOURS):
                    continue
            except (ValueError, TypeError):
                pass

        eligible.append(url)

    if eligible:
        logger.info(f"🔄 Processing {len(eligible)} retries from previous runs...")

    for url in eligible:
        if killer is not None and killer.kill_now:
            logger.info("⏸️  Retry loop interrupted by shutdown signal")
            break

        rate_limiter.wait_if_needed(url)
        is_recipe, soup, error = verifier.verify_recipe(url)

        if is_recipe:
            if importer.import_recipe(url):
                storage.add_imported(url)
                imported_count += 1
                completed_urls.append(url)
            else:
                storage.retry_queue[url]['attempts'] = storage.retry_queue[url].get('attempts', 0) + 1
                storage.retry_queue[url]['last_attempt'] = datetime.now().isoformat()
        else:
            storage.add_reject(url)
            completed_urls.append(url)

    for url in completed_urls:
        storage.retry_queue.pop(url, None)

    if imported_count > 0:
        logger.info(f"   ✅ Retries: {imported_count} imported, {len(completed_urls) - imported_count} permanently rejected")

    return imported_count

def send_notification(storage: StorageManager):
    """Send a summary notification via webhook (Discord, Slack, ntfy.sh)."""
    if not NOTIFICATION_WEBHOOK_URL:
        return

    summary = (
        f"🍲 Recipe Dredger Complete ({VERSION})\n"
        f"   Imported: {len(storage.imported)}\n"
        f"   Rejected: {len(storage.rejects)}\n"
        f"   Retry Queue: {len(storage.retry_queue)}\n"
        f"   Cached Sitemaps: {len(storage.sitemap_cache)}"
    )

    host = urlparse(NOTIFICATION_WEBHOOK_URL).netloc.lower()

    try:
        if 'ntfy.sh' in host or host.startswith('ntfy.'):
            # ntfy.sh takes the body raw, not JSON-wrapped.
            requests.post(NOTIFICATION_WEBHOOK_URL, data=summary.encode('utf-8'), timeout=ROBOTS_TXT_TIMEOUT)
        elif 'discord' in host:
            requests.post(NOTIFICATION_WEBHOOK_URL, json={"content": summary}, timeout=ROBOTS_TXT_TIMEOUT)
        elif 'slack' in host:
            requests.post(NOTIFICATION_WEBHOOK_URL, json={"text": summary}, timeout=ROBOTS_TXT_TIMEOUT)
        else:
            # Unknown host — send both shapes for best-effort compatibility.
            requests.post(NOTIFICATION_WEBHOOK_URL, json={"content": summary, "text": summary}, timeout=ROBOTS_TXT_TIMEOUT)
        logger.info("📨 Notification sent")
    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")

def print_summary(storage: StorageManager):
    logger.info("=" * 50)
    logger.info("📊 Session Summary:")
    logger.info(f"   Total Imported: {len(storage.imported)}")
    logger.info(f"   Total Rejected: {len(storage.rejects)}")
    logger.info(f"   In Retry Queue: {len(storage.retry_queue)}")
    logger.info(f"   Cached Sitemaps: {len(storage.sitemap_cache)}")
    logger.info("=" * 50)

def load_sites_from_source(source_path: str = None) -> List[str]:
    """Load sites from various sources with priority: CLI > local file > env > defaults"""
    
    def parse_sites_json(data) -> List[str]:
        """Parse sites from JSON, handling both array and object formats."""
        if isinstance(data, list):
            # Simple array format: ["url1", "url2", ...]
            return [s for s in data if isinstance(s, str) and s.startswith('http')]
        elif isinstance(data, dict) and 'sites' in data:
            # Object format: {"sites": ["url1", "url2", ...]}
            sites = data['sites']
            return [s for s in sites if isinstance(s, str) and s.startswith('http')]
        else:
            logger.error("Invalid sites.json format. Expected array or object with 'sites' key.")
            return []
    
    # 1. CLI Argument
    if source_path:
        if os.path.exists(source_path):
            try:
                with open(source_path, 'r') as f: 
                    data = json.load(f)
                    return parse_sites_json(data)
            except Exception as e: 
                logger.error(f"Failed to load CLI sites file: {e}")
                sys.exit(1)
        else:
            logger.error(f"File not found: {source_path}")
            sys.exit(1)

    # 2. Local sites.json
    if os.path.exists('sites.json'):
        try:
            with open('sites.json', 'r') as f: 
                data = json.load(f)
                return parse_sites_json(data)
        except Exception as e:
            logger.warning(f"Failed to load sites.json: {e}")
            pass

    # 3. Environment variable: accepts either a path to a JSON file or a
    #    comma-separated list of URLs (.env.example documents both forms).
    sites_env = os.getenv('SITES', '').strip()
    if sites_env:
        # Strip enclosing quotes (`SITES="..."`)
        if len(sites_env) >= 2 and sites_env[0] == sites_env[-1] and sites_env[0] in ('"', "'"):
            sites_env = sites_env[1:-1]
        # Treat as file path if it looks like one and exists
        looks_like_path = (
            os.sep in sites_env or sites_env.startswith('.') or sites_env.endswith('.json')
        )
        if looks_like_path and os.path.exists(sites_env):
            try:
                with open(sites_env, 'r') as f:
                    return parse_sites_json(json.load(f))
            except Exception as e:
                logger.error(f"Failed to load SITES path {sites_env}: {e}")
                sys.exit(1)
        return [s.strip() for s in sites_env.split(',') if s.strip()]

    # 4. Defaults (The Full Curated List)
    return DEFAULT_SITES

def main():
    parser = argparse.ArgumentParser(description="Recipe Dredger: Intelligent Scraper")
    parser.add_argument("--dry-run", action="store_true", help="Scan without importing")
    parser.add_argument("--limit", type=int, default=DEFAULT_TARGET, help="Recipes to import per site")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="URLs to scan per site")
    parser.add_argument("--sites", type=str, help="Path to JSON file containing site URLs")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh crawl (ignore sitemap cache)")
    parser.add_argument("--version", action="version", version=f"Recipe Dredger {VERSION}")
    args = parser.parse_args()

    # Configuration Override
    DRY_RUN_MODE = args.dry_run or DRY_RUN
    TARGET_COUNT = args.limit
    SCAN_DEPTH_COUNT = args.depth
    FORCE_REFRESH = args.no_cache
    
    # Startup checks
    session = get_session()
    validate_config()
    check_connectivity(session)
    
    sites_list = load_sites_from_source(args.sites)

    logger.info(f"🍲 Recipe Dredger Started ({VERSION})")
    logger.info(f"   Mode: {'DRY RUN' if DRY_RUN_MODE else 'LIVE IMPORT'}")
    logger.info(f"   Targets: {len(sites_list)} sites")
    logger.info(f"   Limit: {TARGET_COUNT} per site")
    
    # Initialize components
    storage = StorageManager()
    killer = GracefulKiller()
    rate_limiter = RateLimiter()
    crawler = SitemapCrawler(session, storage)
    verifier = RecipeVerifier(session)
    importer = ImportManager(session, storage, rate_limiter, DRY_RUN_MODE)
    
    # Sync existing library to avoid duplicate API calls
    if SYNC_LIBRARY and not DRY_RUN_MODE:
        sync_existing_library(session, storage)
    
    # Process retry queue from previous runs
    process_retry_queue(storage, importer, verifier, rate_limiter, killer=killer)
    
    # Process sites
    random.shuffle(sites_list)
    
    # Visual Progress Bar (optional tqdm)
    iterator = sites_list
    if TQDM_AVAILABLE and len(sites_list) > 1:
        iterator = tqdm(sites_list, desc="Processing Sites", unit="site")

    for site in iterator:
        # Check for graceful shutdown
        if killer.kill_now: 
            break
        
        if not TQDM_AVAILABLE: 
            logger.info(f"🌍 Processing Site: {site}")
        
        site_stats = {'imported': 0, 'rejected': 0, 'errors': 0}
        
        raw_candidates = crawler.get_urls_for_site(site, force_refresh=FORCE_REFRESH)
        if not raw_candidates: 
            continue
        
        candidates = raw_candidates[:SCAN_DEPTH_COUNT]
        random.shuffle(candidates)
        
        imported_count = 0
        for candidate in candidates:
            # Check for graceful shutdown in inner loop
            if killer.kill_now:
                break

            if imported_count >= TARGET_COUNT:
                break

            outcome = process_candidate(
                candidate.url, storage, importer, verifier, rate_limiter, site_stats,
            )
            if outcome == 'imported':
                imported_count += 1
            elif outcome == 'retry' and not TQDM_AVAILABLE:
                logger.error(f"   ❌ Import failed (queued for retry): {candidate.url}")
        
        if not TQDM_AVAILABLE:
            logger.info(f"   Site Results: {site_stats['imported']} imported, "
                        f"{site_stats['rejected']} rejected, {site_stats['errors']} errors")
        
        storage.flush_all()
    
    # Print summary if not interrupted
    if not killer.kill_now:
        print_summary(storage)
    else:
        logger.info("⏸️  Gracefully stopped by signal")
    
    # Send notification webhook
    send_notification(storage)
        
    logger.info("🏁 Dredge Cycle Complete")

if __name__ == "__main__":
    main()

