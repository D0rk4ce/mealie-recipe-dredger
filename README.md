# 🍲 Mealie Recipe Dredger

![Python](https://img.shields.io/badge/python-3.x-blue?style=flat-square)
![Mealie](https://img.shields.io/badge/Integration-Mealie-orange?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

**A bulk-import automation tool to populate your self-hosted [Mealie](https://mealie.io/) instance with high-quality recipes.**

Starting a self-hosted recipe manager is great, but manually importing thousands of recipes one by one is tedious. This script automates the process by scanning a curated list of high-quality food blogs, detecting *new* recipes via their sitemaps, and importing them directly into your database.

## 🚀 Features

* **Smart Deduplication:** Checks your existing Mealie library first. It will never import a URL you already have.
* **Recipe Verification:** Scans candidate pages for Schema.org JSON-LD or common recipe plugins (WP Recipe Maker, Tasty, etc.) to ensure it only imports actual recipes (skipping travel posts, roundups, or generic blog updates).
* **Deep Sitemap Scanning:** Automatically parses XML sitemaps to find the most recent posts.
* **Polite Scraping:** Includes built-in sleep timers and headers to respect the source servers and avoid being blocked.
* **Curated Source List:** Comes pre-loaded with over 100+ high-quality food blogs covering African, Caribbean, East Asian, Latin American, and General Western cuisines.

## 📋 Prerequisites

* A self-hosted instance of [Mealie](https://mealie.io/) (v1.0 or later).
* Python 3.8+
* A Mealie API Token.

## 🛠️ Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/YOUR_USERNAME/mealie-recipe-dredger.git](https://github.com/YOUR_USERNAME/mealie-recipe-dredger.git)
    cd mealie-recipe-dredger
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

Open `mealie_dredger.py` in your text editor. You **must** update the configuration block at the top of the file:

```python
# --- CONFIGURATION ---
MEALIE_URL = "[http://192.168.1.100:9000](http://192.168.1.100:9000)"  # Your local Mealie address
API_TOKEN = "your_api_token_here"        # Found in Mealie: User Settings > Manage API Tokens

Optional Settings

You can tune the behavior of the scraper by modifying these variables:
Variable		Default		Description  
DRY_RUN 		False		Set to True to scan and find recipes without actually importing them (good for testing).
TARGET_RECIPES_PER_SITE 50		The script will stop scanning a specific site once it finds this many new recipes.
SCAN_DEPTH		1000		How many recent posts to look back through in the sitemap.

🏃 Usage
Run the script manually:

python mealie_dredger.py

Automation (Cron)
To keep your recipe book constantly updated with the latest releases from your favorite blogs, you can set this up as a weekly cron job:

0 3 * * 0 /usr/bin/python3 /path/to/mealie_dredger.py >> /path/to/logs/mealie_import.log 2>&1

🌍 The Site List
The script includes a SITES list within the code containing URLs for high-quality food blogs. You can add or remove URLs from this list to customize where your recipes come from.

⚠️ Disclaimer & Ethics
This tool is intended for personal archiving and self-hosting purposes.

Be Polite: The script includes delays (time.sleep) to prevent overloading site servers. Do not remove these delays.

Respect Creators: Please continue to visit the original blogs to support the content creators who make these recipes possible.

🤝 Contributing
Got a great food blog that parses well? Feel free to submit a Pull Request to add it to the curated list!

📜 License
Distributed under the MIT License. See LICENSE for more information.
