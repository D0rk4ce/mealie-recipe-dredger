# 🍲 Recipe Dredger (Mealie & Tandoor)

![Python](https://img.shields.io/badge/python-3.x-blue?style=flat-square)
![Mealie](https://img.shields.io/badge/Support-Mealie-orange?style=flat-square)
![Tandoor](https://img.shields.io/badge/Support-Tandoor-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

**A bulk-import automation tool to populate your self-hosted recipe managers with high-quality recipes.**

This script automates the process of finding **new** recipes. It scans a curated list of high-quality food blogs, detects new posts via sitemaps, checks if you already have them in your library, and imports them automatically.

## 🚀 Features

* **Multi-Platform:** Supports importing to **Mealie**, **Tandoor**, or both simultaneously.
* **Smart Deduplication:** Checks your existing libraries first. It will never import a URL you already have.
* **Recipe Verification:** Scans candidate pages for Schema.org JSON-LD to ensure it only imports actual recipes.
* **Deep Sitemap Scanning:** Automatically parses XML sitemaps to find the most recent posts.
* **Curated Source List:** Comes pre-loaded with over 100+ high-quality food blogs covering African, Caribbean, East Asian, Latin American, and General Western cuisines.

## 📋 Prerequisites

* A self-hosted instance of [Mealie](https://mealie.io/) OR [Tandoor](https://docs.tandoor.dev/).
* Python 3.8+
* API Tokens for your services.

## 🛠️ Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/D0rk4ce/mealie-recipe-dredger.git](https://github.com/D0rk4ce/mealie-recipe-dredger.git)
    cd mealie-recipe-dredger
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

Open `mealie_dredger.py` in your text editor. You **must** update the configuration block at the top of the file to enable the services you want to use.

```python
# --- CONFIGURATION ---

# Mealie Settings
MEALIE_ENABLED = True
MEALIE_URL = "[http://192.168.1.100:9000](http://192.168.1.100:9000)"
MEALIE_API_TOKEN = "your_mealie_token_here"

# Tandoor Settings
TANDOOR_ENABLED = False  # Change to True to enable
TANDOOR_URL = "[http://192.168.1.101:8080](http://192.168.1.101:8080)"
TANDOOR_API_KEY = "your_tandoor_key_here"
```

## 🏃 Usage

Run the script manually:

```bash
python mealie_dredger.py
```

### Automation (Cron)
To keep your recipe book constantly updated, set this up as a weekly cron job:

```bash
0 3 * * 0 /usr/bin/python3 /path/to/mealie_dredger.py >> /path/to/logs/mealie_import.log 2>&1
```

## ⚠️ Disclaimer & Ethics

This tool is intended for personal archiving and self-hosting purposes.

* **Be Polite:** The script includes delays (`time.sleep`) to prevent overloading site servers. Do not remove these delays.
* **Respect Creators:** Please continue to visit the original blogs to support the content creators who make these recipes possible.

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.