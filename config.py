"""
Shared configuration for Recipe Dredger and Master Cleaner.
All secrets and platform settings are loaded here to avoid duplication.
"""

import os
import re
from dotenv import load_dotenv

# --- LOAD ENV VARS ---
load_dotenv()

# --- PLATFORM SETTINGS ---
MEALIE_ENABLED = os.getenv('MEALIE_ENABLED', 'true').lower() == 'true'
MEALIE_URL = os.getenv('MEALIE_URL', 'http://localhost:9000').rstrip('/')
MEALIE_API_TOKEN = os.getenv('MEALIE_API_TOKEN', 'your-token')

TANDOOR_ENABLED = os.getenv('TANDOOR_ENABLED', 'false').lower() == 'true'
TANDOOR_URL = os.getenv('TANDOOR_URL', 'http://localhost:8080').rstrip('/')
TANDOOR_API_KEY = os.getenv('TANDOOR_API_KEY', 'your-key')

# --- BEHAVIOR ---
DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# --- DATA FILES ---
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
REJECT_FILE = f"{DATA_DIR}/rejects.json"
IMPORTED_FILE = f"{DATA_DIR}/imported.json"
RETRY_FILE = f"{DATA_DIR}/retry_queue.json"
STATS_FILE = f"{DATA_DIR}/stats.json"
SITEMAP_CACHE_FILE = f"{DATA_DIR}/sitemap_cache.json"
VERIFIED_FILE = f"{DATA_DIR}/verified.json"

# --- FILTERS ---
LISTICLE_REGEX = re.compile(r'(\d+)-(best|top|must|favorite|easy|healthy|quick|ways|things)', re.IGNORECASE)
LISTICLE_REGEX_MATCH = re.compile(r'^(\d+)\s+(best|top|must|favorite|easy|healthy|quick|ways|things)', re.IGNORECASE)

HIGH_RISK_KEYWORDS = [
    "cleaning", "storing", "freezing", "pantry", "kitchen tools",
    "review", "giveaway", "shop", "store", "product", "gift", "unboxing",
    "news", "travel", "podcast", "interview", "night cream", "face mask",
    "skin care", "beauty", "diy", "weekly plan", "menu", "holiday guide",
    "foods to try", "things to eat", "detox water", "lose weight"
]

BAD_KEYWORDS = ["roundup", "collection", "guide", "review", "giveaway", "shop", "store", "product"]

# --- CATEGORISATION (optional, off by default) ---
SET_CATEGORIES = os.getenv('SET_CATEGORIES', 'false').lower() == 'true'
CUISINE_MIN_SCORE = float(os.getenv('CUISINE_MIN_SCORE', 2))
