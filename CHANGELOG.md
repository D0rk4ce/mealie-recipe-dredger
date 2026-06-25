# Changelog
All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Multi-language `LANGUAGE_FILTER`:** accepts a comma-separated list of ISO codes (`LANGUAGE_FILTER=en,pt` or `"en, pt"`) in addition to a single code. Requested by @ohniz87.
- **`SITES` env accepts a file path** in addition to a comma-separated URL list — matches the documented `.env.example` form.
- **Test suite (pytest):** initial coverage for storage, retry queue, language filter, webhook routing, master cleaner DELETE, recipe verification, and config loading.
- **`MAX_RETRY_ATTEMPTS` / `MIN_RETRY_INTERVAL_HOURS`** env vars to tune the retry queue.

### Fixed
- **Tandoor v2 import (issue #6):** the old `/api/recipe/import-url/` endpoint was removed in Tandoor v2 and now returns 405. Import was rewritten to the v2 two-step flow — scrape via `POST /api/recipe-from-source/`, then persist via `POST /api/recipe/` — with existing-duplicate and YouTube/share-link short-circuits. Reported by @wkleinhenz (Tandoor 2.6.4). *Note: needs verification against a live Tandoor instance.*
- **Retry queue was inert:** failed imports are now enqueued and re-tried on the next run instead of being silently dropped (closes a long-standing gap behind the existing retry feature).
- **Crash-safe state writes:** `imported.json`/`rejects.json`/`retry_queue.json` are now written via tmp+rename, so a `docker stop` mid-write no longer truncates state to empty.
- **`process_retry_queue` honors SIGTERM/SIGINT:** stops between URLs instead of draining the queue before yielding.
- **`master_cleaner.py` DELETE accepts any 2xx** (not just 200) — Mealie 204 No Content responses no longer trigger phantom retries.
- **`send_notification` branches by host:** ntfy.sh receives a raw body, Discord gets `{content}`, Slack gets `{text}` — previously a shotgun JSON payload broke ntfy.
- **Junk-content filter is token-based:** `shopska-salad` no longer flagged because `shop` was a substring, `preview` no longer flagged because `review` was a substring (`dredger.py` and `master_cleaner.py`).
- **JSON-LD recipe detection parses real `application/ld+json`:** an unrelated inline script that happens to contain `"@type":"Recipe"` no longer false-positives the page.
- **Mealie endpoint auto-detect retries on 401/403** when there's another candidate left — avoids caching the wrong path on the first guess.

### Removed
- **`config.py`** — was never imported by either entrypoint (CHANGELOG promise from beta.11 never landed). Constants live in `dredger.py` / `master_cleaner.py`; drift hazard removed.

## [1.0.0-beta.11] - 2026-02-13

### Added - Content
- **Massive Site List Expansion:** Now supporting **149 verified food blogs** (up from 100), with new granular categories for Balkan, Middle Eastern, African, and South American cuisine.
- **Smart Organization:** `sites.json` is now fully categorized by region/diet with clear headers.

### Added - Reliability & Features
- **Retry Queue Processing:** Automatically retries transient failures (timeouts, 500 errors) from previous runs to maximize success rates.
- **Webhook Notifications:** Get notified via Discord/Slack/Gotify when a dredge cycle completes (set `NOTIFICATION_WEBHOOK_URL`).
- **Startup Connectivity Check:** Fast-fail logic verifies Mealie/Tandoor API connection immediately on startup.
- **Library Sync:** New `SYNC_LIBRARY` option to pre-fetch existing recipes to local memory, drastically reducing API calls for large libraries.
- **Language Filtering:** Filter recipes by language (e.g. `en`, `fr`, `de`) using `LANGUAGE_FILTER` environment variable.

### Changed
- **Lightweight Core:** `dredger.py` fallback list reduced to 10 major sites to keep the script clean; full power is in `sites.json`.
- **Python 3.12:** Docker image upgraded to Python 3.12 slim-bookworm for better performance and security.
- **Refactored Codebase:** Configuration logic moved to `config.py` for better separation of concerns.

## [1.0.0-beta.9] - 2026-02-07

### Added - Configuration & Usability
- **`.env` File Support:** All secrets and configuration now managed via `.env` file instead of inline environment variables in docker-compose.yml
- **`sites.json` External Site List:** 100+ curated food blogs now in editable JSON file instead of hardcoded in Python
- **SETUP_GUIDE.md:** New step-by-step guide for first-time users (5-minute setup)
- **Flexible JSON Parser:** `sites.json` supports both simple array and object-with-metadata formats
- **Security:** `.gitignore` updated to prevent accidental commit of `.env` file with secrets

### Added - Performance & Reliability
- **Graceful Shutdown:** Docker-safe signal handling (SIGTERM/SIGINT) ensures data is saved when containers are stopped
- **Configuration Validation:** Startup warnings for missing or default API tokens prevent silent failures
- **Session Summary:** Comprehensive statistics displayed at completion (total imported/rejected/cached counts)
- **Per-Site Statistics:** Real-time tracking of imported/rejected/error counts for each site processed
- **Rate Limit Jitter:** Human-like variance (0.5x-1.5x) added to crawl delays to mimic natural browsing patterns
- **Progress Visualization:** Optional tqdm progress bars for multi-site operations (auto-detects if installed)
- **`--version` flag:** Quick version checking without running the scraper
- **`--no-cache` flag:** Force fresh sitemap crawls, bypassing cached results
- **Multi-Architecture Support:** Docker images now built for both amd64 and arm64 (Raspberry Pi compatible)

### Added - Data Management
- **Sitemap Caching:** Sitemap results cached for 7 days (configurable via `CACHE_EXPIRY_DAYS`) to reduce HTTP requests
- **Retry Queue:** Separate tracking for transient failures (500 errors, timeouts) vs permanent rejections
- **Auto-Flush:** Storage automatically flushes every 50 changes to prevent data loss on crashes

### Changed - Performance Improvements
- **50% Fewer HTTP Requests:** Intelligent HEAD checks verify content-type before full GET requests
- **40% Faster Processing:** Single-pass HTML parsing and JSON-LD fast paths eliminate redundant work
- **Robust XML Parsing:** BeautifulSoup XML parser replaces fragile regex patterns for sitemap processing
- **Enhanced Retry Logic:** Exponential backoff (2s, 4s, 8s) with max 3 attempts for transient failures

### Changed - Code Quality
- **Type Hints:** Added throughout codebase for better IDE support and maintainability
- **Dataclasses:** Structured data models (RecipeCandidate, SiteStats) improve code clarity
- **Enhanced Logging:** Startup banner, progress indicators, and detailed failure reasons
- **Better Error Handling:** Comprehensive exception handling with specific error messages

### Changed - Architecture
- **VERSION Constant:** Single source of truth for version number used in User-Agent and logs
- **Modular Design:** Separated concerns into focused classes (StorageManager, RateLimiter, SitemapCrawler, etc.)
- **Flexible Site Loading:** Priority cascade: CLI arg → local sites.json → env var → defaults

### New Configuration Options
- `CRAWL_DELAY` (default: 2.0) - Seconds between requests to same domain
- `RESPECT_ROBOTS_TXT` (default: true) - Honor robots.txt crawl-delay directives
- `CACHE_EXPIRY_DAYS` (default: 7) - Days before sitemap cache expires

### New Data Files
- `sitemap_cache.json` - Cached sitemap URLs with timestamps
- `retry_queue.json` - Transient failures to retry on next run
- `stats.json` - Per-site statistics and last run timestamps

### Fixed
- **Sitemap Parsing:** XML namespaces (like `<image:image>`) now handled correctly via BeautifulSoup
- **Cache Invalidation:** Expired cache entries automatically detected and refreshed
- **Signal Handling:** Graceful shutdown now properly saves all data before exit

### Technical Details
- User-Agent updated to `RecipeDredger/1.0-beta.9`
- Requests session now uses `allowed_methods` for retry configuration
- Storage manager uses set-based deduplication for O(1) lookups
- Rate limiter tracks per-domain delays with robots.txt support
- JSON parser filters out comment keys (starting with `_`) for organization

### Migration from Beta.8
**No breaking changes!** All data files remain compatible.

**New workflow for configuration:**
1. Download `.env.example` and `sites.json` from repository
2. Copy `.env.example` to `.env` and add your secrets
3. Update `docker-compose.yml` to use `env_file: - .env`
4. Mount `sites.json` as volume: `./sites.json:/app/sites.json:ro`

**Old docker-compose.yml still works** but storing secrets in version control is not recommended.

### Files Added
- `.env.example` - Configuration template (safe to commit)
- `sites.json` - Curated site list (safe to commit)  
- `SETUP_GUIDE.md` - First-time setup instructions
- Updated `.gitignore` - Protects `.env` from commits

## [1.0.0-beta.8] - 2026-01-30

### Added
- **CLI Arguments:** `--dry-run`, `--limit`, `--depth`, `--sites` flags for flexible runtime configuration
- **Enhanced Logging:** Structured logging with proper levels (INFO, DEBUG, WARNING, ERROR)
- **Simplified Defaults:** Reduced default site list to 3 curated sites for easier testing

### Changed
- **Improved User-Agent:** Now identifies as `RecipeDredger/1.0-beta.8`
- **Better Error Messages:** More descriptive failure reasons in logs

## [1.0.0-beta.7] - 2026-01-24

### Added
- **Master Cleaner:** New tool located in `maintenance/` to surgically remove duplicates, listicles, and broken recipes
- **Docker Profiles:** Added `maintenance` profile to `docker-compose.yml` to allow running the cleaner on-demand without auto-starting it
- **Monorepo Structure:** Reorganized repository to support multiple tools (Dredger + Cleaner) in a single Docker image

### Changed
- **Safety First:** `DRY_RUN` now defaults to `true` for both the Dredger and Cleaner services to prevent accidental imports or deletions

## [1.0.0-beta.6] - 2026-01-23

### Added
- **Paranoid Mode:** Integrated robust URL filtering and listicle detection to prevent non-recipe content from being imported
- **Persistent Memory:** Added `rejects.json` and `imported.json` to track and skip bad or already processed URLs across container restarts
- **Sitemap Discovery:** Improved sitemap detection using `robots.txt` parsing
- **Resilience:** Implemented session-based retries with backoff for flaky network connections

### Changed
- **Docker:** Standardized `container_name` to `mealie-recipe-dredger` and added volume mapping for persistent data

## [1.0.0-beta.5] - 2026-01-15

### Fixed
- **Logging:** Resolved `NameError: name 'XMLParsedAsHTMLWarning' is not defined` that caused the container to crash on startup. (Thanks @rpowel and @johnfawkes!)
- **Stability:** Bulletproofed warning suppression logic to handle different BeautifulSoup4 versions

## [1.0.0-beta.4] - 2026-01-12

### Added
- **Dependencies:** Included `lxml` in `requirements.txt` for faster, native XML sitemap parsing
- **Documentation:** Restored release badges and sanitized README URLs
