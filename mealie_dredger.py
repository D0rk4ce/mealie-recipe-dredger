import requests
import time
import json
import sys
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
# ⚠️ REPLACE THESE WITH YOUR OWN DETAILS
MEALIE_URL = "http://YOUR_MEALIE_IP:9000"  # e.g. http://192.168.1.100:9000
API_TOKEN = "YOUR_API_TOKEN_HERE"          # Generate in Mealie: User Profile -> Manage API Tokens

# 🛑 SETTINGS
DRY_RUN = False              # Set to True to test without importing
TARGET_RECIPES_PER_SITE = 50 # Goal: Grab this many NEW recipes per site
SCAN_DEPTH = 1000            # Look at the last X posts to find those recipes
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# 🏆 THE CURATED LIST
# A collection of high-quality food blogs with standard sitemaps
SITES = [
    # [PASTE YOUR FULL LIST OF SITES HERE]
    # For the sake of the GitHub upload, you can include the full list you shared
    # or a truncated sample to keep the file size manageable for readability.
    "https://www.africanbites.com",
    "https://www.justonecookbook.com",
    "https://sallysbakingaddiction.com",
    # ... add the rest of your list ...
]

def get_existing_urls():
    print("🛡️  Audit: Verifying API Data Quality...")
    existing = set()
    page = 1
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    
    try:
        first_check = requests.get(f"{MEALIE_URL}/api/recipes?page=1&perPage=1", headers=headers, timeout=10)
        if first_check.status_code != 200:
            print("❌ API FAILURE: Cannot connect to Mealie. Check URL and Token.")
            sys.exit(1)
            
        first_data = first_check.json()
        total_expected = first_data.get('total', 0)
        print(f"📉 Downloading index (Expecting ~{total_expected} recipes)...")
        
        while True:
            r = requests.get(f"{MEALIE_URL}/api/recipes?page={page}&perPage=1000", headers=headers, timeout=15)
            if r.status_code != 200: break
            items = r.json().get('items', [])
            if not items: break
            for item in items:
                if 'orgURL' in item and item['orgURL']: existing.add(item['orgURL'])
                if 'originalURL' in item and item['originalURL']: existing.add(item['originalURL'])
            print(f"   ...scanned page {page} (Total found: {len(existing)})", end="\r")
            page += 1
    except Exception as e:
        print(f"\n❌ Connection Error: {e}")
        sys.exit(1)

    print(f"\n🛡️  Audit Complete. Index contains {len(existing)} URLs.")
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
        # Simple check for schema or common recipe plugins
        if '"@type":"Recipe"' in r.text or '"@type": "Recipe"' in r.text: return True
        soup = BeautifulSoup(r.content, 'html.parser')
        if soup.find(class_=lambda x: x and ('wp-recipe-maker' in x or 'tasty-recipes' in x or 'mv-create-card' in x)): return True
        return False
    except: return False

def parse_sitemap(sitemap_url, existing_set):
    print(f"   📂 Parsing: {sitemap_url}")
    new_candidates = []
    try:
        r = requests.get(sitemap_url, headers=HEADERS, timeout=15)
        # lxml is faster, but html.parser is more forgiving. Using xml for sitemaps.
        soup = BeautifulSoup(r.content, 'xml')
        
        if soup.find('sitemap'):
            for sm in soup.find_all('sitemap'):
                loc = sm.find('loc').text
                if len(new_candidates) >= SCAN_DEPTH: break 
                if "post" in loc: new_candidates.extend(parse_sitemap(loc, existing_set))
            if not new_candidates and soup.find('sitemap'):
                return parse_sitemap(soup.find('sitemap').find('loc').text, existing_set)
                
        for u in soup.find_all('url'):
            if len(new_candidates) >= SCAN_DEPTH: break 
            loc = u.find('loc').text
            if any(x in loc for x in ['/about', '/contact', '/shop', '/privacy', 'login', 'cart', 'roundup']): continue
            if loc not in existing_set: new_candidates.append(loc)
    except Exception:
        pass
    return list(set(new_candidates))

def push_to_mealie(url):
    endpoint = f"{MEALIE_URL}/api/recipes/create/url"
    headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}
    try:
        r = requests.post(endpoint, json={"url": url}, headers=headers, timeout=10)
        if r.status_code == 201: 
            print(f"      ✅ Imported: {url}")
            return True
        elif r.status_code == 409: 
            return False
        else: 
            return False
    except: 
        return False

# --- MAIN ---
if __name__ == "__main__":
    print(f"🚀 WEEKLY IMPORT (DEEP DREDGE): {len(SITES)} Sites")
    print(f"🎯 Goal: {TARGET_RECIPES_PER_SITE} NEW recipes/site | Scan Depth: {SCAN_DEPTH}")
    print("-" * 50)

    existing_urls = get_existing_urls()

    for site in SITES:
        print(f"\n🌍 Site: {site}")
        sitemap = find_sitemap(site)
        if not sitemap:
            print("   ❌ No sitemap found.")
            continue
            
        targets = parse_sitemap(sitemap, existing_urls)
        if not targets:
            print("   💤 No new recipes found in the top 1000 posts.")
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
                print(f"      [DRY RUN] Valid Recipe: {url}")
                imported_count += 1
            else:
                if push_to_mealie(url):
                    existing_urls.add(url)
                    imported_count += 1
                    time.sleep(1.5) # Be polite to the server
                else:
                    pass 
        
    print("\n🏁 WEEKLY RUN COMPLETE.")
