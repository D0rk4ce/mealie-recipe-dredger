import requests
import time
import re
import json
import os
import sys
import concurrent.futures
import logging
from urllib.parse import urlparse

# --- LOGGING CONFIGURATION ---
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("cleaner")

# --- CONFIGURATION ---
DRY_RUN = os.getenv('DRY_RUN', 'True').lower() == 'true'

MEALIE_ENABLED = os.getenv('MEALIE_ENABLED', 'true').lower() == 'true'
MEALIE_URL = os.getenv('MEALIE_URL', 'http://localhost:9000').rstrip('/')
MEALIE_API_TOKEN = os.getenv('MEALIE_API_TOKEN', 'your-token')

TANDOOR_ENABLED = os.getenv('TANDOOR_ENABLED', 'false').lower() == 'true'
TANDOOR_URL = os.getenv('TANDOOR_URL', 'http://localhost:8080').rstrip('/')
TANDOOR_API_KEY = os.getenv('TANDOOR_API_KEY', 'your-key')

MAX_WORKERS = int(os.getenv('MAX_WORKERS', 2))
REJECT_FILE = "data/rejects.json"
VERIFIED_FILE = "data/verified.json"

# --- FILTERS ---
HIGH_RISK_KEYWORDS = [
    "cleaning", "storing", "freezing", "pantry", "kitchen tools",
    "review", "giveaway", "shop", "store", "product", "gift", "unboxing",
    "news", "travel", "podcast", "interview", "night cream", "face mask", 
    "skin care", "beauty", "diy", "weekly plan", "menu", "holiday guide",
    "foods to try", "things to eat", "detox water", "lose weight"
]

LISTICLE_REGEX = re.compile(r'^(\d+)\s+(best|top|must|favorite|easy|healthy|quick|ways|things)', re.IGNORECASE)

# --- UTILS ---
def load_json_set(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f: return set(json.load(f))
        except: return set()
    return set()

def save_json_set(filename, data_set):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f: json.dump(list(data_set), f)

REJECTS = load_json_set(REJECT_FILE)
VERIFIED = load_json_set(VERIFIED_FILE)

# --- API CLIENTS ---
def get_mealie_recipes():
    if not MEALIE_ENABLED: return []
    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
    recipes, page = [], 1
    logger.info(f"Scanning Mealie library at {MEALIE_URL}...")
    while True:
        try:
            r = requests.get(f"{MEALIE_URL}/api/recipes?page={page}&perPage=1000", headers=headers, timeout=10)
            if r.status_code != 200: break
            items = r.json().get('items', [])
            if not items: break
            recipes.extend(items)
            page += 1
            if page % 5 == 0: logger.debug(f"Fetched page {page-1}...")
        except Exception as e:
            logger.error(f"Error fetching Mealie recipes: {e}")
            break
    logger.info(f"Total Mealie recipes found: {len(recipes)}")
    return recipes

def delete_mealie_recipe(slug, name, reason, url=None):
    if DRY_RUN:
        logger.info(f" [DRY RUN] Would delete from Mealie: '{name}' (Reason: {reason})")
        return
    
    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
    logger.info(f"🗑️ Deleting from Mealie: '{name}' (Reason: {reason})")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            r = requests.delete(f"{MEALIE_URL}/api/recipes/{slug}", headers=headers, timeout=10)
            if r.status_code == 200: break
            time.sleep(1) 
        except Exception as e:
            logger.warning(f"Error deleting {slug} (Attempt {attempt+1}): {e}")
            time.sleep(1)

    if url: REJECTS.add(url)
    if slug in VERIFIED: VERIFIED.remove(slug)

def get_tandoor_recipes():
    if not TANDOOR_ENABLED: return []
    headers = {"Authorization": f"Bearer {TANDOOR_API_KEY}"}
    recipes, page = [], 1
    logger.info(f"Scanning Tandoor library at {TANDOOR_URL}...")
    while True:
        try:
            r = requests.get(f"{TANDOOR_URL}/api/recipe/?page={page}&limit=100", headers=headers, timeout=10)
            if r.status_code != 200: break
            data = r.json()
            results = data.get("results", [])
            if not results: break
            recipes.extend(results)
            if not data.get("next"): break
            page += 1
        except Exception as e:
            logger.error(f"Error fetching Tandoor recipes: {e}")
            break
    logger.info(f"Total Tandoor recipes found: {len(recipes)}")
    return recipes

def delete_tandoor_recipe(recipe_id, name, reason, url=None):
    if DRY_RUN:
        logger.info(f" [DRY RUN] Would delete from Tandoor: '{name}' (Reason: {reason})")
        return

    headers = {"Authorization": f"Bearer {TANDOOR_API_KEY}"}
    logger.info(f"🗑️ Deleting from Tandoor: '{name}' (Reason: {reason})")
    try:
        requests.delete(f"{TANDOOR_URL}/api/recipe/{recipe_id}/", headers=headers, timeout=10)
        time.sleep(0.5)
    except Exception as e:
        logger.error(f"Error deleting {recipe_id}: {e}")

    if url: REJECTS.add(url)

# --- LOGIC ---
def is_junk_content(name, url):
    if not url: return False
    try:
        slug = urlparse(url).path.strip("/").split("/")[-1].lower()
    except: slug = ""
    name_l = name.lower()
    
    for kw in HIGH_RISK_KEYWORDS:
        if kw.replace(" ", "-") in slug or kw in name_l: return True
    
    if LISTICLE_REGEX.match(slug) or LISTICLE_REGEX.match(name_l): return True
    if any(x in url.lower() for x in ["privacy-policy", "contact", "about-us", "login", "cart"]): return True
    return False

def validate_instructions(inst):
    if not inst: return False
    if isinstance(inst, str):
        if len(inst.strip()) == 0: return False
        if "could not detect" in inst.lower(): return False
        return True
    if isinstance(inst, list):
        if len(inst) == 0: return False
        has_content = False
        for step in inst:
            text = step.get('text', '') if isinstance(step, dict) else str(step)
            if text and len(text.strip()) > 0:
                has_content = True
                break
        return has_content
    return True

def check_integrity(recipe, service="mealie"):
    slug_or_id = recipe.get('slug') if service == "mealie" else recipe.get('id')
    if slug_or_id in VERIFIED: return None
    
    name = recipe.get('name')
    url = recipe.get('orgURL') or recipe.get('originalURL') or recipe.get('source')
    
    try:
        inst = None
        if service == "mealie":
            headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
            r = requests.get(f"{MEALIE_URL}/api/recipes/{slug_or_id}", headers=headers, timeout=10)
            if r.status_code == 200:
                inst = r.json().get('recipeInstructions')
        else:
            inst = recipe.get('steps') or recipe.get('description')

        if not validate_instructions(inst):
            return (slug_or_id, name, "Empty/Broken Instructions", url, service)
        
        return (slug_or_id, "VERIFIED")
    except: return None

# --- MAIN ---
if __name__ == "__main__":
    try:
        logger.info("="*40)
        logger.info(f"MASTER CLEANER STARTED")
        logger.info(f"Mode: {'DRY RUN (Safe)' if DRY_RUN else 'LIVE (Destructive)'}")
        logger.info(f"Workers: {MAX_WORKERS}")
        logger.info("="*40)

        all_m = get_mealie_recipes()
        all_t = get_tandoor_recipes()
        
        tasks = [(r, "mealie") for r in all_m] + [(r, "tandoor") for r in all_t]
        
        if not tasks:
            logger.info("No recipes found to scan.")
            sys.exit(0)

        logger.info("--- Phase 1: Surgical Filter Scan ---")
        clean_tasks = []
        for recipe, svc in tasks:
            name = recipe.get('name', 'Unknown')
            url = recipe.get('orgURL') or recipe.get('originalURL') or recipe.get('source')
            id_val = recipe.get('slug') if svc == "mealie" else recipe.get('id')
            
            if is_junk_content(name, url):
                if svc == "mealie": delete_mealie_recipe(id_val, name, "JUNK CONTENT", url)
                else: delete_tandoor_recipe(id_val, name, "JUNK CONTENT", url)
            else:
                clean_tasks.append((recipe, svc))

        logger.info(f"--- Phase 2: Deep Integrity Scan (Checking {len(clean_tasks)} recipes) ---")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(check_integrity, r, s) for r, s in clean_tasks]
            
            for i, f in enumerate(concurrent.futures.as_completed(futures)):
                res = f.result()
                if res:
                    if res[1] == "VERIFIED":
                        VERIFIED.add(res[0])
                    else:
                        r_id, r_name, r_reason, r_url, r_svc = res
                        if r_svc == "mealie": 
                            delete_mealie_recipe(r_id, r_name, r_reason, r_url)
                        else: 
                            delete_tandoor_recipe(r_id, r_name, r_reason, r_url)
                
                if i % 10 == 0:
                    logger.debug(f"Progress: {i}/{len(clean_tasks)}")

        if not DRY_RUN:
            save_json_set(REJECT_FILE, REJECTS)
            save_json_set(VERIFIED_FILE, VERIFIED)
            logger.info("State saved.")
        else:
            logger.info("Dry Run: No state files updated.")

        logger.info("CLEANUP COMPLETE")
        
    except KeyboardInterrupt:
        logger.warning("Operation Interrupted.")
        sys.exit(0)
