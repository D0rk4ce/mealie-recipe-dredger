import requests
import time
import json
import os
import re
import sys
import warnings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from langdetect import detect, DetectorFactory
from urllib.parse import urlparse

# Prevent the "XMLParsedAsHTMLWarning" noise
warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

# --- CONFIGURATION (Env Vars for Docker) ---
MEALIE_ENABLED = os.getenv('MEALIE_ENABLED', 'true').lower() == 'true'
MEALIE_URL = os.getenv('MEALIE_URL', 'http://YOUR_SERVER_IP:9000').rstrip('/')
MEALIE_API_TOKEN = os.getenv('MEALIE_API_TOKEN', 'YOUR_MEALIE_TOKEN')

TANDOOR_ENABLED = os.getenv('TANDOOR_ENABLED', 'false').lower() == 'true'
TANDOOR_URL = os.getenv('TANDOOR_URL', 'http://YOUR_TANDOOR_IP:8080').rstrip('/')
TANDOOR_API_KEY = os.getenv('TANDOOR_API_KEY', 'YOUR_TANDOOR_KEY')

DRY_RUN = os.getenv('DRY_RUN', 'False').lower() == 'true'
TARGET_RECIPES_PER_SITE = int(os.getenv('TARGET_RECIPES_PER_SITE', 50))
SCAN_DEPTH = int(os.getenv('SCAN_DEPTH', 1000))
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

raw_lang = os.getenv('SCRAPE_LANG', 'en').lower()
ALLOWED_LANGS = [lang.strip() for lang in raw_lang.split(',') if lang.strip()]

# 🧠 MEMORY SETTINGS
# Ensure the directory exists to prevent FileNotFoundError
os.makedirs("data", exist_ok=True) 

REJECT_FILE = "data/rejects.json"
IMPORTED_FILE = "data/imported.json"
DetectorFactory.seed = 0

# 🛡️ FAILSAFE: NETWORK RETRY LOGIC
def get_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.headers.update(HEADERS)
    return session

SESSION = get_session()

# 🗑️ SURGICAL FILTERS
BAD_SLUG_KEYWORDS = [
    "how-to", "guide", "101", "basics", "tips", "tricks", "hacks",
    "what-is", "difference-between", "benefit-of", "best-way-to",
    "cleaning", "storing", "freezing", "pantry", "kitchen-tools",
    "review", "giveaway", "shop", "store", "product", "gift", "unboxing",
    "news", "travel", "podcast", "interview", "recipes", "ideas", 
    "inspiration", "suggestions", "roundup", "collection", "list-of", 
    "ways-to", "favorites", "meal-plan", "weekly-plan", "menu", 
    "holiday-guide", "best-of", "top-10", "top-20", "top-50", "master-list"
]
LISTICLE_REGEX = re.compile(r'^(\d+)-(best|top|must|favorite|easy|healthy|quick|ways|things)-', re.IGNORECASE)

# 🏆 THE CURATED LIST
DEFAULT_SITES = [
    "https://www.africanbites.com", "https://lowcarbafrica.com", "https://cheflolaskitchen.com",
    "https://www.myforkinglife.com", "https://grandbaby-cakes.com", "https://divascancook.com",
    "https://coopcancook.com", "https://www.thehungryhutch.com", "https://sweetteaandthyme.com",
    "https://www.butterbeready.com", "https://www.whiskitrealgud.com", "https://www.dashofjazz.com",
    "https://www.meikoandthedish.com", "https://www.preciouscore.com", "https://www.myburntorange.com",
    "https://blackfoodie.com", "https://www.karenskitchenstories.com", "https://www.seasonedskilletblog.com",
    "https://caribbeanpot.com", "https://www.alicaaway.com", "https://jehancancook.com",
    "https://www.curiouscuisiniere.com", "https://www.cooklikeajamaican.com", "https://thatgirlcookshealthy.com",
    "https://www.islandsmile.org", "https://www.dominicancooking.com", "https://www.mycolombianrecipes.com",
    "https://www.laylita.com", "https://www.gypsyplate.com", "https://www.jocooks.com",
    "https://www.indianhealthyrecipes.com", "https://ministryofcurry.com", "https://www.cookwithmanali.com",
    "https://www.veganricha.com", "https://pipingpotcurry.com", "https://myfoodstory.com",
    "https://www.teaforturmeric.com", "https://www.dassanasvegrecipes.com", "https://www.hebbarskitchen.com",
    "https://www.funfoodfrolic.com", "https://www.hookedonheat.com", "https://www.myheartbeets.com",
    "https://twosleevers.com", "https://www.spiceupthecurry.com", "https://www.themediterraneandish.com",
    "https://feelgoodfoodie.net", "https://www.recipetineats.com", "https://www.hungrypaprikas.com",
    "https://cleobuttera.com", "https://amiraspantry.com", "https://www.littlespicejar.com",
    "https://www.isabeleats.com", "https://www.mexicoinmykitchen.com", "https://pinaenlacocina.com",
    "https://www.muydelish.com", "https://www.maricruzavalos.com", "https://www.thaicaliente.com",
    "https://www.kitchengidget.com", "https://www.mylatinatable.com", "https://www.smartlittlecookie.net",
    "https://www.justonecookbook.com", "https://thewoksoflife.com", "https://seonkyounglongest.com",
    "https://www.maangchi.com", "https://omnivorescookbook.com", "https://hot-thai-kitchen.com",
    "https://rasamalaysia.com", "https://pickledplum.com", "https://www.drivemehungry.com",
    "https://www.chopstickchronicles.com", "https://www.wandercooks.com", "https://www.koreanbapsang.com",
    "https://mykoreankitchen.com", "https://www.futuredish.com", "https://www.hungryhuy.com",
    "https://glebekitchen.com", "https://pupswithchopsticks.com", "https://redhousespice.com",
    "https://pressureluckcooking.com", "https://www.corriecooks.com", "https://airfryereats.com",
    "https://www.instrupix.com", "https://www.365daysofcrockpot.com", "https://www.stayingclosetohome.com",
    "https://www.recipesthatcrock.com", "https://www.slowcookerfromscratch.com", "https://www.pressurecookrecipes.com",
    "https://www.airfryingfoodie.com", "https://www.fastfoodbistro.com", "https://www.platedcravings.com",
    "https://sallysbakingaddiction.com", "https://preppykitchen.com", "https://sugarspunrun.com",
    "https://www.skinnytaste.com", "https://pinchofyum.com", "https://www.budgetbytes.com",
    "https://www.wellplated.com", "https://natashaskitchen.com", "https://www.gimmesomeoven.com",
    "https://www.thekitchn.com", "https://www.foodiecrush.com", "https://www.twopeasandtheirpod.com",
    "https://www.ambitiouskitchen.com", "https://www.dinneratthezoo.com", "https://www.spendwithpennies.com",
    "https://www.iheartnaptime.net", "https://www.lecremedelacrumb.com", "https://www.melskitchencafe.com",
    "https://www.recipeboy.com", "https://www.recipegirl.com", "https://www.tasteandtellblog.com",
    "https://www.thegunnysack.com", "https://www.thereciperebel.com", "https://www.chef-in-training.com",
    "https://www.julieseatsandtreats.com", "https://www.closetcooking.com", "https://www.carlsbadcravings.com",
    "https://www.yellowblissroad.com", "https://www.liluna.com", "https://www.tastesbetterfromscratch.com",
    "https://minimalistbaker.com", "https://cookieandkate.com", "https://www.loveandlemons.com",
    "https://ohsheglows.com", "https://www.101cookbooks.com", "https://www.sproutedkitchen.com",
    "https://www.elanaspantry.com", "https://www.skinnykitchen.com", "https://www.eatingbirdfood.com",
    "https://www.runningonrealfood.com", "https://www.feastingathome.com", "https://www.cottercrunch.com",
    "https://www.lexiscleankitchen.com", "https://www.paleorunningmomma.com", "https://www.wholesomeyum.com",
    "https://www.gnom-gnom.com", "https://www.alldayidreamaboutfood.com", "https://www.ibreatheimhungry.com",
    "https://www.ditchedthewheat.com", "https://www.healthylittlefoodies.com", "https://www.superhealthykids.com",
    "https://www.yummytoddlerfood.com", "https://www.simplyrecipes.com", "https://www.forkandbeans.com", 
    "https://www.chocolatecoveredkatie.com"
]

env_sites = os.getenv('SITES')
SITES = [s.strip() for s in env_sites.split(',') if s.strip()] if env_sites else DEFAULT_SITES

# --- HELPERS ---

def load_json_set(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return set(json.load(f))
        except: return set()
    return set()

def save_json_set(filename, data_set):
    with open(filename, 'w') as f:
        json.dump(list(data_set), f)

def get_mealie_existing_urls():
    if not MEALIE_ENABLED: return set()
    print("🛡️  [Mealie] Checking for cache drift...")
    existing = load_json_set(IMPORTED_FILE)
    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
    try:
        r = SESSION.get(f"{MEALIE_URL}/api/recipes?page=1&perPage=1", headers=headers, timeout=10)
        if r.status_code != 200: return existing
        server_total = r.json().get('total', 0)
        if abs(server_total - len(existing)) < (server_total * 0.05) and len(existing) > 0:
            print(f"   ✅ Cache healthy ({len(existing)} recipes).")
            return existing
    except: return existing

    print(f"📉 [Mealie] Full Syncing index...")
    existing = set()
    page = 1
    while True:
        try:
            r = SESSION.get(f"{MEALIE_URL}/api/recipes?page={page}&perPage=1000", headers=headers, timeout=15)
            if r.status_code != 200: break
            items = r.json().get('items', [])
            if not items: break
            for item in items:
                for key in ['orgURL', 'originalURL']:
                    if item.get(key): existing.add(item[key])
            print(f"   ...scanned page {page}", end="\r")
            page += 1
        except: break
    save_json_set(IMPORTED_FILE, existing)
    return existing

def get_tandoor_existing_urls():
    if not TANDOOR_ENABLED: return set()
    print("🛡️  [Tandoor] Verifying API Data Quality...")
    existing = set()
    page = 1
    headers = {"Authorization": f"Bearer {TANDOOR_API_KEY}"}
    while True:
        try:
            r = SESSION.get(f"{TANDOOR_URL}/api/recipe/?page={page}&limit=100", headers=headers, timeout=10)
            if r.status_code != 200: break
            data = r.json()
            results = data.get("results", [])
            if not results: break
            for recipe in results:
                if recipe.get("source"): existing.add(recipe.get("source"))
            if not data.get("next"): break
            page += 1
        except: break
    return existing

def get_sitemap_from_robots(base_url):
    try:
        r = SESSION.get(f"{base_url}/robots.txt", timeout=5)
        if r.status_code == 200:
            for line in r.text.splitlines():
                if "Sitemap:" in line:
                    return line.split("Sitemap:")[1].strip()
    except: return None

def find_sitemap(base_url):
    candidates = []
    robots_sm = get_sitemap_from_robots(base_url)
    if robots_sm: candidates.append(robots_sm)
    candidates.extend([f"{base_url}/wp-sitemap.xml", f"{base_url}/recipe-sitemap.xml", 
                       f"{base_url}/post-sitemap.xml", f"{base_url}/sitemap_index.xml", 
                       f"{base_url}/sitemap.xml", f"{base_url}/sitemap_posts.xml"])
    for url in candidates:
        try:
            if SESSION.head(url, timeout=5).status_code == 200: return url
        except: pass
    return None

def is_junk_url(url):
    try:
        slug = urlparse(url).path.strip("/").split("/")[-1].lower()
        if any(kw in slug for kw in BAD_SLUG_KEYWORDS): return True
        if LISTICLE_REGEX.match(slug): return True
        if any(x in url.lower() for x in ["privacy", "contact", "about", "login", "cart", "roundup"]): return True
    except: pass
    return False

def verify_is_recipe(url):
    if is_junk_url(url): return False
    try:
        r = SESSION.get(url, timeout=10)
        if r.status_code != 200: return False
        try:
            if detect(r.text[:2000]) not in ALLOWED_LANGS: return False
        except: return False
        if '"@type":"Recipe"' in r.text or '"@type": "Recipe"' in r.text: return True
        soup = BeautifulSoup(r.content, 'html.parser')
        if soup.find(class_=lambda x: x and ('wp-recipe-maker' in x or 'tasty-recipes' in x or 'mv-create-card' in x)): return True
    except: pass
    return False

def parse_sitemap(sitemap_url, existing_set, reject_set):
    print(f"   📂 Parsing: {sitemap_url}")
    new_candidates = []
    try:
        r = SESSION.get(sitemap_url, timeout=15)
        soup = BeautifulSoup(r.content, 'xml')
        if soup.find('sitemap'):
            for sm in soup.find_all('sitemap'):
                loc = sm.find('loc').text
                if len(new_candidates) >= SCAN_DEPTH: break
                if "post" in loc or "recipe" in loc:
                    new_candidates.extend(parse_sitemap(loc, existing_set, reject_set))
        for u in soup.find_all('url'):
            if len(new_candidates) >= SCAN_DEPTH: break
            loc = u.find('loc').text
            if loc not in existing_set and loc not in reject_set:
                new_candidates.append(loc)
    except: pass
    return list(set(new_candidates))

def push_to_mealie(url):
    endpoint = f"{MEALIE_URL}/api/recipes/create/url"
    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}", "Content-Type": "application/json"}
    try:
        return SESSION.post(endpoint, json={"url": url}, headers=headers, timeout=15).status_code == 201
    except: return False

def push_to_tandoor(url):
    endpoint = f"{TANDOOR_URL}/api/recipe/from-url/"
    headers = {"Authorization": f"Bearer {TANDOOR_API_KEY}", "Content-Type": "application/json"}
    try:
        return SESSION.post(endpoint, json={"url": url}, headers=headers, timeout=15).status_code in [200, 201]
    except: return False

# --- MAIN ---
if __name__ == "__main__":
    try:
        print(f"🚀 RECIPE DREDGER: {len(SITES)} Sites | Language: {', '.join(ALLOWED_LANGS).upper()}")
        reject_urls = load_json_set(REJECT_FILE)
        existing_mealie = get_mealie_existing_urls()
        existing_tandoor = get_tandoor_existing_urls()
        combined_existing = existing_mealie.union(existing_tandoor)
        
        for site in SITES:
            print(f"\n🌍 Site: {site}")
            sitemap = find_sitemap(site)
            if not sitemap: continue
            
            targets = parse_sitemap(sitemap, combined_existing, reject_urls)
            if not targets: continue
            
            print(f"   🔎 Checking {len(targets)} candidates...")
            imported_count = 0
            for url in targets:
                if imported_count >= TARGET_RECIPES_PER_SITE: break
                
                if not verify_is_recipe(url):
                    reject_urls.add(url)
                    continue

                if DRY_RUN:
                    print(f"      [DRY RUN] Valid: {url}")
                    imported_count += 1
                    continue

                m_success = push_to_mealie(url) if MEALIE_ENABLED and url not in existing_mealie else False
                t_success = push_to_tandoor(url) if TANDOOR_ENABLED and url not in existing_tandoor else False
                
                if m_success or t_success:
                    print(f"      ✅ Imported: {url}")
                    combined_existing.add(url)
                    imported_count += 1
                    time.sleep(1.5)
            
            save_json_set(REJECT_FILE, reject_urls)
            save_json_set(IMPORTED_FILE, combined_existing)
            
        print("\n🏁 IMPORT RUN COMPLETE.")

    except KeyboardInterrupt:
        print("\n🛑 INTERRUPTED! Saving memory...")
        save_json_set(REJECT_FILE, reject_urls)
        save_json_set(IMPORTED_FILE, combined_existing)
        sys.exit(0)
