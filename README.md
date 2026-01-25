# 🍲 Recipe Dredger (Mealie & Tandoor)

A bulk-import automation tool to populate your self-hosted recipe managers with high-quality recipes.

> **⚠️ Note regarding Tandoor:** This script was built and tested specifically for **Mealie**. Tandoor support was added via community request and is currently **untested** by the author. If you use Tandoor, please report your results in the Issues tab!

![Release](https://img.shields.io/github/v/release/D0rk4ce/mealie-recipe-dredger?include_prereleases&style=flat-square)

This script automates the process of finding **new** recipes. It scans a curated list of high-quality food blogs, detects new posts via sitemaps, checks if you already have them in your library, and imports them automatically.

## 🚀 Features

* **Multi-Platform:** Supports importing to **Mealie** (Primary) and **Tandoor** (Experimental).
* **Smart Memory:** Uses local JSON files to remember rejected and successfully imported URLs.
* **Multi-Language Support:** Automatically detects and filters recipes. Supports single or multiple languages (e.g., `en` or `en,de,fr`).
* **Smart Deduplication:** Checks your existing libraries first. It will never import a URL you already have.
* **Recipe Verification:** Scans candidate pages for Schema.org JSON-LD to ensure it only imports actual recipes.
* **Deep Sitemap Scanning:** Automatically parses XML sitemaps and robots.txt to find the most recent posts.
* **Curated Source List:** Comes pre-loaded with over 100+ high-quality food blogs covering African, Caribbean, East Asian, Latin American, and General Western cuisines.

## 🐳 Quick Start (Docker)

The most efficient way to run the Dredger is using Docker. You do not need to clone the repository or install Python.

1. Create a `docker-compose.yml` file:

```yaml
services:
  mealie-recipe-dredger:
    image: ghcr.io/d0rk4ce/mealie-recipe-dredger:latest
    container_name: mealie-recipe-dredger
    environment:
      # --- Connection Settings ---
      - MEALIE_ENABLED=true
      - MEALIE_URL=http://192.168.1.X:9000
      - MEALIE_API_TOKEN=your_mealie_token
      - TANDOOR_ENABLED=false
      - TANDOOR_URL=http://192.168.1.X:8080
      - TANDOOR_API_KEY=your_tandoor_key
      
      # --- Scraper Behavior ---
      - DRY_RUN=true                  # 🛡️ SAFETY: Defaults to True. Change to false to import.
      - LOG_LEVEL=INFO                # ℹ️ LOGGING: Change to DEBUG for verbose details.
      - TARGET_RECIPES_PER_SITE=50     # Stop after importing this many per site
      - SCAN_DEPTH=1000                # How many links to check before giving up on a site
      - SCRAPE_LANG=en,de              # Filter content by language
      
      # --- Sources ---
      # Optional: Override the built-in site list
      - SITES=https://example.com,https://another-blog.com
    volumes:
      - ./data:/app/data
    restart: "no"
    
  # 🧹 Maintenance: Master Cleaner
  # Run manually with: docker compose run --rm mealie-cleaner
  mealie-cleaner:
    image: ghcr.io/d0rk4ce/mealie-recipe-dredger:latest
    container_name: mealie-cleaner
    command: python maintenance/master_cleaner.py
    profiles: ["maintenance"]
    environment:
      - DRY_RUN=true            # 🛡️ SAFETY: Set to false to DELETE recipes
      - LOG_LEVEL=INFO          # ℹ️ LOGGING: Change to DEBUG for verbose details.
      - MAX_WORKERS=2           # Default is 2 to prevent database locks
      # --- Mealie Config ---
      - MEALIE_ENABLED=true
      - MEALIE_URL=http://192.168.1.X:9000
      - MEALIE_API_TOKEN=your_mealie_token
      # --- Tandoor Config ---
      - TANDOOR_ENABLED=false
      - TANDOOR_URL=http://192.168.1.X:8080
      - TANDOOR_API_KEY=your_tandoor_key
    volumes:
      - ./data:/app/data
    restart: "no"
```

2. Run the tool:
    ```bash
    # To run the Dredger (Import Mode)
    docker compose up
    ```

### Scheduling (Cron)
To run this weekly (e.g., Sundays at 3am), add an entry to your host's crontab:

```bash
0 3 * * 0 cd /path/to/docker-compose-folder && docker compose up
```

## 🧹 Maintenance Mode (Cleaner)

The image includes a `master_cleaner.py` script to purge duplicates, listicles, and broken recipes.

**To run the cleaner in isolation (Dry Run):**
```bash
docker compose run --rm mealie-cleaner
```

**To actually delete data:**
1. Edit `docker-compose.yml` and set `DRY_RUN=false` in the `mealie-cleaner` service.
2. Run the command above again.

## ⚙️ Configuration Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `MEALIE_ENABLED` | `true` | Set to `false` to disable Mealie imports. |
| `MEALIE_URL` | N/A | Your local Mealie URL (e.g. `http://192.168.1.5:9000`). |
| `MEALIE_API_TOKEN` | N/A | Found in Mealie User Settings > Manage API Tokens. |
| `TANDOOR_ENABLED` | `false` | Set to `true` to enable Tandoor imports. |
| `TANDOOR_URL` | N/A | Your local Tandoor URL. |
| `TANDOOR_API_KEY` | N/A | Your Tandoor API key. |
| `SCRAPE_LANG` | `en` | Comma-separated ISO codes for allowed languages (e.g., `en` or `en,de`). |
| `SITES` | (Curated List) | A comma-separated list of blog URLs to scrape (overrides the built-in list). |
| `DRY_RUN` | `True` | **Dredger:** Scan without importing. **Cleaner:** Scan without deleting. |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` for verbose logs (shows metadata and skip reasons). |
| `TARGET_RECIPES_PER_SITE` | `50` | Stops scanning a specific site after importing this many recipes. |
| `SCAN_DEPTH` | `1000` | Maximum number of sitemap links to check per site before giving up. |

## 🐍 Manual Usage (Python)

If you prefer to run the script manually without Docker:

1. **Clone the repository:**
    ```bash
    git clone https://github.com/d0rk4ce/mealie-recipe-dredger.git
    cd mealie-recipe-dredger
    ```

2. **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3. **Configure:**
    Open `dredger.py` or `maintenance/master_cleaner.py` and edit the default values in the `CONFIGURATION` block, or export environment variables in your terminal.

4. **Run:**
    ```bash
    python dredger.py
    # OR
    python maintenance/master_cleaner.py
    ```

> **Note:** The script creates a `data/` folder to persist `imported.json` and `rejects.json` between runs.

## 🤝 Contributors

* **@rpowel** and **@johnfawkes** - Stability and logging fixes in v1.0.0-beta.5.

## ⚠️ Disclaimer & Ethics

* This tool is intended for personal archiving and self-hosting purposes.
* **Be Polite:** The script includes delays (`time.sleep`) to prevent overloading site servers. Do not remove these delays.
* **Respect Creators:** Please continue to visit the original blogs to support the content creators who make these recipes possible.

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.