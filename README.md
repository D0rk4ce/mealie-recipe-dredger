# 🍲 Recipe Dredger (Mealie & Tandoor)

A bulk-import automation tool to populate your self-hosted recipe managers with high-quality recipes.

> **⚠️ Note regarding Tandoor:** This script was built and tested specifically for **Mealie**. Tandoor support was added via community request and is currently **untested** by the author. If you use Tandoor, please report your results in the Issues tab!

![Release](https://img.shields.io/github/v/release/D0rk4ce/mealie-recipe-dredger?include_prereleases&style=flat-square)
This script automates the process of finding **new** recipes. It scans a curated list of high-quality food blogs, detects new posts via sitemaps, checks if you already have them in your library, and imports them automatically.

## 🚀 Features

* **Multi-Platform:** Supports importing to **Mealie** (Primary) and **Tandoor** (Experimental).
* **Multi-Language Support:** Automatically detects and filters recipes. Supports single or multiple languages (e.g., `en` or `en,de,fr`).
* **Smart Deduplication:** Checks your existing libraries first. It will never import a URL you already have.
* **Recipe Verification:** Scans candidate pages for Schema.org JSON-LD to ensure it only imports actual recipes.
* **Deep Sitemap Scanning:** Automatically parses XML sitemaps to find the most recent posts.
* **Curated Source List:** Comes pre-loaded with over 100+ high-quality food blogs covering African, Caribbean, East Asian, Latin American, and General Western cuisines.

## 🐳 Quick Start (Docker)

The most efficient way to run the Dredger is using Docker. You do not need to clone the repository or install Python.

1.  Create a `docker-compose.yml` file:

```yaml
services:
  recipe-dredger:
    image: ghcr.io/d0rk4ce/mealie-recipe-dredger:latest
    container_name: recipe-dredger
    environment:
      - MEALIE_ENABLED=true
      - MEALIE_URL=[http://192.168.1.](http://192.168.1.)X:9000
      - MEALIE_API_TOKEN=your_mealie_token
      - TANDOOR_ENABLED=false
      - TANDOOR_URL=[http://192.168.1.](http://192.168.1.)X:8080
      - TANDOOR_API_KEY=your_tandoor_key
      - SCRAPE_LANG=en,de  # Supports comma-separated lists
      # Optional: Override the built-in site list
      - SITES=[https://example.com](https://example.com),[https://another-blog.com](https://another-blog.com)
    restart: "no"
```

2.  Run the tool:
    ```bash
    docker compose up
    ```

### Scheduling (Cron)
To run this weekly (e.g., Sundays at 3am), add an entry to your host's crontab:

```bash
0 3 * * 0 cd /path/to/docker-compose-folder && docker compose up
```

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

## 🐍 Manual Usage (Python)

If you prefer to run the script manually without Docker:

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/d0rk4ce/mealie-recipe-dredger.git](https://github.com/d0rk4ce/mealie-recipe-dredger.git)
    cd mealie-recipe-dredger
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure:**
    Open `dredger.py` and edit the default values in the `CONFIGURATION` block, or export environment variables in your terminal.

4.  **Run:**
    ```bash
    python dredger.py
    ```

## ⚠️ Disclaimer & Ethics

* This tool is intended for personal archiving and self-hosting purposes.
* **Be Polite:** The script includes delays (`time.sleep`) to prevent overloading site servers. Do not remove these delays.
* **Respect Creators:** Please continue to visit the original blogs to support the content creators who make these recipes possible.

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.