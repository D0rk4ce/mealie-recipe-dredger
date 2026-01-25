import requests
from bs4 import BeautifulSoup
import json
import time
import os
import random
import re
import logging
import sys
from urllib.parse import urlparse

# --- LOGGING CONFIGURATION ---
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("dredger")

# --- CONFIGURATION ---
MEALIE_ENABLED = os.getenv('MEALIE_ENABLED', 'true').lower() == 'true'
MEALIE_URL = os.getenv('MEALIE_URL', 'http://localhost:9000').rstrip('/')
MEALIE_API_TOKEN = os.getenv('MEALIE_API_TOKEN', 'your-token')

TANDOOR_ENABLED = os.getenv('TANDOOR_ENABLED', 'false').lower() == 'true'
TANDOOR_URL = os.getenv('TANDOOR_URL', 'http://localhost:8080').rstrip('/')
TANDOOR_API_KEY = os.getenv('TANDOOR_API_KEY', 'your-key')

DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'
SCRAPE_LANG = os.getenv('SCRAPE_LANG', 'en')
TARGET_RECIPES_PER_SITE = int(os.getenv('TARGET_RECIPES_PER_SITE', 50))
SCAN_DEPTH = int(os.getenv('SCAN_DEPTH', 1000))

# 🧠 MEMORY SETTINGS
os.makedirs("data", exist_ok=True)
REJECT_FILE = "data/rejects.json"
IMPORTED_FILE = "data/imported.json"

# --- CURATED SOURCES (The Full List) ---
# Overridden by SITES env var if present
ENV_SITES = os.getenv('SITES', '')
if ENV_SITES:
    SITES = [s.strip() for s in ENV_SITES.split(',') if s.strip()]
else:
    SITES = [
        # --- GENERAL / WESTERN ---
        "https://www.seriouseats.com", "https://www.bonappetit.com",
        "https://www.foodandwine.com", "https://www.simplyrecipes.com",
        "https://smittenkitchen.com", "https://www.skinnytaste.com",
        "https://www.budgetbytes.com", "https://www.twopeasandtheirpod.com",
        "https://cookieandkate.com", "https://minimalistbaker.com",
        "https://gimmesomeoven.com", "https://pinchofyum.com",
        "https://www.loveandlemons.com", "https://damndelicious.net",
        "https://www.halfbakedharvest.com", "https://sallysbakingaddiction.com",
        "https://www.wellplated.com", "https://www.acouplecooks.com",
        "https://www.feastingathome.com", "https://www.recipetineats.com",
        "https://www.dinneratthezoo.com", "https://cafedelites.com",
        "https://natashaskitchen.com", "https://www.spendwithpennies.com",
        "https://carlsbadcravings.com", "https://www.averiecooks.com",
        "https://www.closetcooking.com", "https://rasamalaysia.com",
        "https://iamafoodblog.com", "https://www.101cookbooks.com",
        "https://www.sproutedkitchen.com", "https://www.howsweeteats.com",
        "https://joythebaker.com", "https://www.melskitchencafe.com",
        "https://www.ambitiouskitchen.com", "https://www.eatingbirdfood.com",

        # --- ASIAN (East, SE, South) ---
        "https://www.justonecookbook.com", "https://www.woksoflife.com",
        "https://omnivorescookbook.com", "https://glebekitchen.com",
        "https://www.indianhealthyrecipes.com", "https://www.vegrecipesofindia.com",
        "https://www.manjulaskitchen.com", "https://hebbarskitchen.com",
        "https://maangchi.com", "https://www.koreanbapsang.com",
        "https://mykoreankitchen.com", "https://hot-thai-kitchen.com",
        "https://sheasim.com", "https://panlasangpinoy.com",
        "https://www.kawalingpinoy.com", "https://steamykitchen.com",
        "https://chinasichuanfood.com", "https://redhousespice.com",
        "https://seonkyounglongest.com", "https://pupswithchopsticks.com",
        "https://wandercooks.com", "https://www.pressurecookrecipes.com",

        # --- LATIN AMERICAN ---
        "https://www.mexicoinmykitchen.com", "https://www.isabeleats.com",
        "https://pinaenlacocina.com", "https://www.dominicancooking.com",
        "https://www.mycolombianrecipes.com", "https://www.laylita.com",
        "https://www.braziliankitchenabroad.com", "https://www.chilipeppermadness.com",
        "https://www.kitchengidget.com", "https://www.quericavida.com",

        # --- AFRICAN / CARIBBEAN ---
        "https://www.africanbites.com", "https://lowcarbafrica.com",
        "https://www.myactivekitchen.com", "https://9jafoodie.com",
        "https://www.cheflolaskitchen.com", "https://sisijemimah.com",
        "https://originalflava.com", "https://caribbeanpot.com",
        "https://www.alicaspepperpot.com", "https://jehancancook.com",
        "https://www.cookwithdena.com", "https://kausarskitchen.com",

        # --- MEDITERRANEAN / MIDDLE EASTERN ---
        "https://www.themediterraneandish.com", "https://cookieandkate.com",
        "https://www.lazycatkitchen.com", "https://ozlemsturkishtable.com",
        "https://persianmama.com", "https://www.unicornsinthekitchen.com",
        "https://www.myjewishlearning.com/the-nosher", "https://toriavey.com",

        # --- BAKING / DESSERT SPECIFIC ---
        "https://www.kingarthurbaking.com/recipes", "https://preppykitchen.com",
        "https://sugarspunrun.com", "https://www.biggerbolderbaking.com"
    ]

# --- PARANOID FILTERS ---
LISTICLE_REGEX = re.compile(r'(\d+)-(best|top|must|favorite|easy|healthy|quick|ways|things)', re.IGNORECASE)
BAD_KEYWORDS = ["roundup", "collection", "guide", "review", "giveaway", "shop", "store", "product"]

# --- UTILS ---
def load_json_set(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_json_set(filename, data_set):
    with open(filename, 'w') as f:
        json.dump(list(data_set), f)

REJECTS = load_json_set(REJECT_FILE)
IMPORTED = load_json_set(IMPORTED_FILE)

def get_session():
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    return s

def is_paranoid_skip(url, soup=None):
    path = urlparse(url).path
    slug = path.strip("/").split("/")[-1].lower()

    # 1. URL Pattern Check
    if LISTICLE_REGEX.search(slug):
        return f"Listicle detected in URL: {slug}"
    
    for kw in BAD_KEYWORDS:
        if kw in slug: return f"Bad keyword in URL: {kw}"

    # 2. Content Check (if soup available)
    if soup:
        title = soup.title.string.lower() if soup.title else ""
        if "best recipes" in title or "top 10" in title:
            return "Listicle title detected"
    
    return False

def extract_recipe_data(url, session):
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200: return None
        soup = BeautifulSoup(r.content, 'html.parser')

        # Paranoid Check
        reason = is_paranoid_skip(url, soup)
        if reason:
            logger.warning(f"🛡️  Paranoid Skip ({reason}): {url}")
            return None

        # JSON-LD Hunt
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') in ['Recipe', 'recipe']:
                            logger.debug(f"🔍 Found JSON-LD Recipe in list: {url}")
                            return item
                elif isinstance(data, dict):
                    if data.get('@type') in ['Recipe', 'recipe']:
                        logger.debug(f"🔍 Found JSON-LD Recipe: {url}")
                        return data
                    # Handle graph
                    if '@graph' in data:
                        for item in data['@graph']:
                            if item.get('@type') in ['Recipe', 'recipe']:
                                logger.debug(f"🔍 Found JSON-LD Recipe in @graph: {url}")
                                return item
            except: continue
    except Exception as e:
        logger.error(f"❌ Scraping error on {url}: {e}")
    return None

def import_to_mealie(url):
    if DRY_RUN:
        logger.info(f" [DRY RUN] Would import: {url}")
        return True
    
    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
    payload = {"url": url}
    try:
        r = requests.post(f"{MEALIE_URL}/api/recipes/create-url", headers=headers, json=payload, timeout=20)
        if r.status_code == 201:
            logger.info(f"✅ [Mealie] Imported: {url}")
            return True
        elif r.status_code == 409:
            logger.info(f"⚠️ [Mealie] Duplicate: {url}")
            return True # Treat as success to remember it
        else:
            logger.error(f"❌ [Mealie] Failed ({r.status_code}): {url}")
    except Exception as e:
        logger.error(f"❌ [Mealie] Connection Error: {e}")
    return False

def import_to_tandoor(url):
    if DRY_RUN:
        logger.info(f" [DRY RUN] Would import to Tandoor: {url}")
        return True
    
    headers = {"Authorization": f"Bearer {TANDOOR_API_KEY}"}
    payload = {"url": url}
    try:
        r = requests.post(f"{TANDOOR_URL}/api/recipe/import-url/", headers=headers, json=payload, timeout=20)
        if r.status_code in [200, 201]:
            logger.info(f"✅ [Tandoor] Imported: {url}")
            return True
        else:
            logger.error(f"❌ [Tandoor] Failed ({r.status_code}): {url}")
    except Exception as e:
        logger.error(f"❌ [Tandoor] Connection Error: {e}")
    return False

def process_site(base_url):
    logger.info(f"🌍 Processing Site: {base_url}")
    session = get_session()
    
    # Simple Sitemap Discovery
    sitemap_url = f"{base_url}/sitemap.xml"
    # Try generic robots.txt check if sitemap fails could be added here
    
    try:
        r = session.get(sitemap_url, timeout=10)
        if r.status_code != 200:
            logger.warning(f"⚠️ No sitemap found for {base_url}")
            return

        # Basic XML parsing using Regex to avoid heavy deps for sitemaps if lxml fails
        # But we assume lxml or basic string search for links
        urls = re.findall(r'<loc>(https?://[^<]+)</loc>', r.text)
        logger.info(f"   Found {len(urls)} URLs in sitemap.")
        
        random.shuffle(urls) # Randomize to avoid hammering same posts
        
        count = 0
        for url in urls[:SCAN_DEPTH]:
            if count >= TARGET_RECIPES_PER_SITE: break
            if url in IMPORTED or url in REJECTS: continue
            
            # Paranoid URL pre-check
            if is_paranoid_skip(url):
                REJECTS.add(url)
                continue

            data = extract_recipe_data(url, session)
            if data:
                # Language Check
                lang = data.get('inLanguage', 'en')
                if SCRAPE_LANG not in lang and 'en' not in SCRAPE_LANG: # Loose check
                    logger.debug(f"   Skipping language {lang}: {url}")
                    continue

                success = False
                if MEALIE_ENABLED: success = import_to_mealie(url)
                if TANDOOR_ENABLED: success = import_to_tandoor(url) or success
                
                if success:
                    IMPORTED.add(url)
                    count += 1
                    time.sleep(2) # Be polite
            else:
                logger.debug(f"   No recipe found: {url}")
                REJECTS.add(url)
                
    except Exception as e:
        logger.error(f"❌ Site Error {base_url}: {e}")

# --- MAIN LOOP ---
if __name__ == "__main__":
    logger.info("🍲 Recipe Dredger Started")
    logger.info(f"   Mode: {'DRY RUN' if DRY_RUN else 'LIVE IMPORT'}")
    logger.info(f"   Memory: {len(IMPORTED)} imported, {len(REJECTS)} rejected")
    
    random.shuffle(SITES)
    for site in SITES:
        process_site(site)
        save_json_set(REJECT_FILE, REJECTS)
        save_json_set(IMPORTED_FILE, IMPORTED)
        
    logger.info("🏁 Dredge Cycle Complete.")
