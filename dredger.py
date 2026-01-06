import requests
import time
import json
import os
import subprocess
from bs4 import BeautifulSoup
from langdetect import detect, DetectorFactory

# --- CONFIGURATION ---
# Uses Environment Variables for Docker (Standardized)

# Mealie Settings
MEALIE_ENABLED = os.getenv('MEALIE_ENABLED', 'true').lower() == 'true'
MEALIE_URL = os.getenv('MEALIE_URL', 'http://YOUR_SERVER_IP:9000')
MEALIE_API_TOKEN = os.getenv('MEALIE_API_TOKEN', 'YOUR_API_TOKEN_HERE')

# Tandoor Settings
TANDOOR_ENABLED = os.getenv('TANDOOR_ENABLED', 'false').lower() == 'true'
TANDOOR_URL = os.getenv('TANDOOR_URL', 'http://YOUR_TANDOOR_IP:8080')
TANDOOR_API_KEY = os.getenv('TANDOOR_API_KEY', 'YOUR_TANDOOR_KEY')

# 🛑 GENERAL SETTINGS
DRY_RUN = os.getenv('DRY_RUN', 'False').lower() == 'true'
TARGET_RECIPES_PER_SITE = int(os.getenv('TARGET_RECIPES_PER_SITE', 50))
SCAN_DEPTH = int(os.getenv('SCAN_DEPTH', 1000))
SCRAPE_LANG = os.getenv('SCRAPE_LANG', 'en').lower() # Default to English
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Seed for consistent language detection
DetectorFactory.seed = 0

# 🏆 THE CURATED LIST
SITES = [
    # --- AFRICAN & SOUL FOOD ---
    "https://www.africanbites.com", "https://lowcarbafrica.com", "https://cheflolaskitchen.com",
    "https://www.myforkinglife.com", "https://grandbaby-cakes.com", "https://divascancook.com",
    "https://coopcancook.com", "https://www.thehungryhutch.com", "https://sweetteaandthyme.com",
    "https://www.butterbeready.com", "https://www.whiskitrealgud.com", "https://www.dashofjazz.com",
    "https://www.meikoandthedish.com", "https://www.preciouscore.com", "https://www.myburntorange.com",
    "https://www.blackfoodie.co", "https://www.karenskitchencookbook.com", "https://www.seasonedskilletblog.com",
    
    # --- CARIBBEAN ---
    "https://caribbeanpot.com", "https://www.alicaaway.com", "https://jehancancook.com",
    "https://www.curiouscuisiniere.com", "https://www.cooklikeajamaican.com", "https://thatgirlcookshealthy.com",
    "https://www.islandsmile.org", "https://www.dominicancooking.com", "https://www.mycolombianrecipes.com",
    "https://www.laylita.com", "https://www.gypsyplate.com", "https://www.jocooks.com",

    # --- INDIAN & MIDDLE EASTERN ---
    "https://www.indianhealthyrecipes.com", "https://ministryofcurry.com", "https://www.cookwithmanali.com",
    "https://www.veganricha.com", "https://pipingpotcurry.com", "https://myfoodstory.com",
    "https://www.teaforturmeric.com", "https://www.dassanasvegrecipes.com", "https://www.hebbarskitchen.com",
    "https://www.funfoodfrolic.com", "https://www.hookedonheat.com", "https://www.myheartbeets.com",
    "https://twosleevers.com", "https://www.spiceupthecurry.com", "https://www.themediterraneandish.com",
    "https://feelgoodfoodie.net", "https://www.recipetineats.com", "https://www.hungrypaprikas.com",
    "https://cleobuttera.com", "https://amiraspantry.com", "https://www.littlespicejar.com",

    # --- LATIN AMERICAN ---
    "https://www.isabeleats.com", "https://www.mexicoinmykitchen.com", "https://pinaenlacocina.com",
    "https://www.muydelish.com", "https://www.maricruzavalos.com", "https://www.thaicaliente.com",
    "https://www.kitchengidget.com", "https://www.mylatinatable.com", "https://www.smartlittlecookie.net",

    # --- EAST ASIAN ---
    "https://www.justonecookbook.com", "https://thewoksoflife.com", "https://seonkyounglongest.com",
    "https://www.maangchi.com", "https://omnivorescookbook.com", "https://hot-thai-kitchen.com",
    "https://rasamalaysia.com", "https://pickledplum.com", "https://www.drivemehungry.com",
    "https://www.chopstickchronicles.com", "https://www.wandercooks.com", "https://www.koreanbapsang.com",
    "https://mykoreankitchen.com", "https://www.futuredish.com", "https://www.hungryhuy.com",
    "https://glebekitchen.com", "https://pupswithchopsticks.com", "https://redhousespice.com",

    # --- INSTANT POT / AIR FRYER ---
    "https://pressureluckcooking.com", "https://www.corriecooks.com", "https://airfryereats.com",
    "https://www.instrupix.com", "https://www.365daysofcrockpot.com", "https://www.stayingclosetohome.com",
    "https://www.recipesthatcrock.com", "https://www.slowcookerfromscratch.com", "https://www.pressurecookrecipes.com",
    "https://www.airfryingfoodie.com", "https://www.fastfoodbistro.com", "https://www.platedcravings.com",

    # --- HIGH QUALITY GENERAL ---
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
    "https://www.saltandbaker.com", "https://www.houseofnasheats.com", "https://www.modernhoney.com",
    "https://www.number-2-pencil.com", "https://www.plainchicken.com", "https://www.southyourmouth.com",
    "https://www.spicysouthernkitchen.com", "https://www.thecountrycook.net", "https://www.theseasonedmom.com",
    "https://www.thechunkychef.com", "https://www.familyfreshmeals.com", "https://www.favfamilyrecipes.com",
    "https://minimalistbaker.com", "https://cookieandkate.com", "https://www.loveandlemons.com",
    "https://ohsheglows.com", "https://www.101cookbooks.com", "https://www.sproutedkitchen.com",
    "https://www.elanaspantry.com", "https://www.skinnykitchen.com", "https://www.eatingbirdfood.com",
    "https://www.runningonrealfood.com", "https://www.feastingathome.com", "https://www.cottercrunch.com",
    "https://www.lexiscleankitchen.com", "https://www.paleorunningmomma.com", "https://www.wholesomeyum.com",
    "https://www.gnom-gnom.com", "https://www.alldayidreamaboutfood.com", "https://www.ibreatheimhungry.com",
    "https://www.ditchedthewheat.com", "https://www.healthylittlefoodies.com", "https://www.superhealthykids.com",
    "https://www.yummytoddlerfood.com", "https://www.forkandbeans.com", "https://www.chocolatecoveredkatie.com"
]

# --- HELPERS ---

def get_mealie_existing_urls():
    if not MEALIE_ENABLED: return set()
    print("🛡️  [Mealie] Verifying API Data Quality...")
    existing = set()
    page = 1
    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
    
    try:
        # Check connection first
        r = requests.get(f"{MEALIE_URL}/api/recipes?page=1&perPage=1", headers=headers, timeout=10)
        
        # ✅ FAILSAFE: If Mealie is enabled but unreachable, STOP immediately.
        # This prevents the script from assuming "0 recipes found" and trying to re-import everything.
        if r.status_code != 200:
            print(f"❌ [Mealie] API FAILURE: {r.status_code}. Cannot connect.")
            if not DRY_RUN:
                print("🛑 Aborting to prevent potential duplication issues.")
                exit(1)
            return set()
            
    except Exception as e:
        print(f"❌ [Mealie] Connection Error: {e}")
        if not DRY_RUN:
            print("🛑 Aborting.")
            exit(1)
        return set()

    print(f"📉 [Mealie] Downloading index...")
    while True:
        try:
            r = requests.get(f"{MEALIE_URL}/api/recipes?page={page}&perPage=1000", headers=headers, timeout=15)
            if r.status_code != 200: break
            items = r.json().get('items', [])
            if not items: break
            for item in items:
                if 'orgURL' in item and item['orgURL']: existing.add(item['orgURL'])
                if 'originalURL' in item and item['originalURL']: existing.add(item['originalURL'])
            print(f"   ...scanned page {page} (Total found: {len(existing)})", end="\r")
            page += 1
        except: break
    print(f"\n🛡️  [Mealie] Index contains {len(existing)} URLs.")
    return existing

def get_tandoor_existing_urls():
    if not TANDOOR_ENABLED: return set()
    print("🛡️  [Tandoor] Verifying API Data Quality...")
    existing = set()
    page = 1
    headers = {"Authorization": f"Bearer {TANDOOR_API_KEY}"}

    while True:
        try:
            r = requests.get(f"{TANDOOR_URL}/api/recipe/?page={page}&limit=100", headers=headers, timeout=10)
            if r.status_code != 200: break
            data = r.json()
            results = data.get("results", [])
            if not results: break

            for recipe in results:
                if recipe.get("source"): existing.add(recipe.get("source"))
            
            print(f"   ...scanned page {page} (Total found: {len(existing)})", end="\r")
            if not data.get("next"): break
            page += 1
        except Exception as e:
            print(f"❌ [Tandoor] Error reading index: {e}")
            break
            
    print(f"\n🛡️  [Tandoor] Index contains {len(existing)} URLs.")
    return existing

def find_sitemap(base_url):
    candidates = [f"{base_url}/post-sitemap.xml", f"{base_url}/sitemap_index.xml", f"{base_url}/sitemap.xml", f"{base_url}/sitemap_posts.xml"]
    for url in candidates:
        try:
            r = requests.head(url, headers=HEADERS, timeout=5)
            if r.status_code == 200: return url
        except: pass
    return None

def verify_is_recipe(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200: return False

        # 🛡️ Language Filter
        try:
            detected_lang = detect(r.text[:2000])
            if detected_lang != SCRAPE_LANG:
                print(f"      ⏩ Skipping ({detected_lang.upper()}): {url}")
                return False
        except:
            return False 

        if '"@type":"Recipe"' in r.text or '"@type": "Recipe"' in r.text: return True
        soup = BeautifulSoup(r.content, 'html.parser')
        if soup.find(class_=lambda x: x and ('wp-recipe-maker' in x or 'tasty-recipes' in x or 'mv-create-card' in x)): return True
        return False
    except: return False

def parse_sitemap(sitemap_url, ignore_set):
    print(f"   📂 Parsing: {sitemap_url}")
    new_candidates = []
    try:
        r = requests.get(sitemap_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.content, 'xml')
        
        if soup.find('sitemap'):
            for sm in soup.find_all('sitemap'):
                loc = sm.find('loc').text
                if len(new_candidates) >= SCAN_DEPTH: break 
                if "post" in loc: new_candidates.extend(parse_sitemap(loc, ignore_set))
            if not new_candidates and soup.find('sitemap'):
                return parse_sitemap(soup.find('sitemap').find('loc').text, ignore_set)
        
        for u in soup.find_all('url'):
            if len(new_candidates) >= SCAN_DEPTH: break 
            loc = u.find('loc').text
            if any(x in loc for x in ['/about', '/contact', '/shop', '/privacy', 'login', 'cart', 'roundup']): continue
            if loc not in ignore_set: 
                new_candidates.append(loc)
    except: pass
    return list(set(new_candidates))

def push_to_mealie(url):
    if not MEALIE_ENABLED: return False
    endpoint = f"{MEALIE_URL}/api/recipes/create/url"
    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}", "Content-Type": "application/json"}
    try:
        r = requests.post(endpoint, json={"url": url}, headers=headers, timeout=10)
        return r.status_code == 201
    except: return False

def push_to_tandoor(url):
    if not TANDOOR_ENABLED: return False
    endpoint = f"{TANDOOR_URL}/api/recipe/from-url/"
    headers = {"Authorization": f"Bearer {TANDOOR_API_KEY}", "Content-Type": "application/json"}
    try:
        r = requests.post(endpoint, json={"url": url}, headers=headers, timeout=10)
        return r.status_code in [200, 201]
    except: return False

# --- MAIN ---
if __name__ == "__main__":
    print(f"🚀 RECIPE DREDGER: {len(SITES)} Sites")
    print(f"🎯 Goal: {TARGET_RECIPES_PER_SITE} NEW recipes/site | Scan Depth: {SCAN_DEPTH}")
    print(f"🗣️  Language: {SCRAPE_LANG.upper()}")
    print("-" * 50)

    # 1. Load Existing Libraries
    existing_mealie = get_mealie_existing_urls()
    existing_tandoor = get_tandoor_existing_urls()

    # Combine for deduplication
    combined_existing = set()
    if MEALIE_ENABLED and TANDOOR_ENABLED:
        combined_existing = existing_mealie.intersection(existing_tandoor)
    elif MEALIE_ENABLED:
        combined_existing = existing_mealie
    elif TANDOOR_ENABLED:
        combined_existing = existing_tandoor

    for site in SITES:
        print(f"\n🌍 Site: {site}")
        sitemap = find_sitemap(site)
        if not sitemap:
            print("   ❌ No sitemap found.")
            continue
            
        targets = parse_sitemap(sitemap, combined_existing)
        if not targets:
            print("   💤 No new recipes found in recent posts.")
            continue

        print(f"   🔎 Scanning {len(targets)} candidates for {TARGET_RECIPES_PER_SITE} good ones...")
        imported_count = 0
        
        for url in targets:
            if imported_count >= TARGET_RECIPES_PER_SITE:
                print("   🎯 Target Reached. Next.")
                break

            if not verify_is_recipe(url):
                continue

            if DRY_RUN:
                print(f"      [DRY RUN] Would import: {url}")
                imported_count += 1
                continue

            # Import Logic
            success_mealie = False
            success_tandoor = False
            
            # Try Mealie
            if MEALIE_ENABLED and url not in existing_mealie:
                if push_to_mealie(url):
                    success_mealie = True
                    existing_mealie.add(url)
            
            # Try Tandoor
            if TANDOOR_ENABLED and url not in existing_tandoor:
                if push_to_tandoor(url):
                    success_tandoor = True
                    existing_tandoor.add(url)

            # Output & Sleeping
            if success_mealie or success_tandoor:
                services = []
                if success_mealie: services.append("Mealie")
                if success_tandoor: services.append("Tandoor")
                print(f"      ✅ Imported to {', '.join(services)}: {url}")
                imported_count += 1
                time.sleep(1.5) # Be polite
            else:
                pass 
            
    print("\n🏁 IMPORT RUN COMPLETE.")
