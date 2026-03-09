# Changelog

All notable changes to Productivity Monitor are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [1.4.0] — 2026-03-09

### Added

#### Settings Panel — General tab
- **Restart Monitor button** — one-click restart of the background monitor daemon directly from the dashboard. Uses `launchctl kickstart -k` on macOS; falls back to `bootout` + `bootstrap` if the service is in an unexpected state. Shows live feedback (restarting → restarted / error) and auto-resets after 8 seconds. Eliminates the need to use the terminal when a new category entry isn't being picked up by the running process.

#### API
- `POST /api/restart-monitor` — triggers a clean restart of `com.chad.productivity-monitor` LaunchAgent. Returns `{"ok": true, "msg": "Monitor restarted."}` on success, `{"ok": false, "msg": "..."}` on failure.

### Fixed
- **Score Killers showing uncategorized apps** — the `/api/score-killers` query excluded productive categories but not `'uncategorized'`. Any record with `category = 'uncategorized'` (e.g. from a brief monitor state issue) would surface as a score killer even if the app was correctly configured. Fixed by adding `'uncategorized'` to the NOT IN exclusion list.
- **Monitor stale-state categorization bug** — the background monitor process, when running continuously across a categories.json change, could fail to pick up new app entries correctly despite reloading the file each poll. Restart Monitor button and `POST /api/restart-monitor` endpoint provide the clean fix. Retroactive SQL patch applied for affected records.

---

## [1.3.0] — 2026-03-09

### Added

#### Dashboard
- **Browser Breakdown row** — second row below Today's Breakdown showing browser-app activity only: Browser Score card, Browser Breakdown donut chart, and Browser Time by Category bars. Answers "what am I actually doing in the browser?" with a dedicated score and breakdown.
- **Live score recalculation on legend clicks** — clicking any legend item on the Today's Breakdown or Browser Breakdown donut charts toggles that category and instantly recalculates the corresponding productivity score, score label, and score colour. Clicking again restores it.
- **Score Killers panel** — shows the top 5 apps by time in non-productive categories. Appears below Top Categories Today. (moved from v1.2.0 — was accidentally omitted from previous release)

#### Settings Panel — Browser Rules tab
- **+ button** on each rule card — clicking the green `+` to the left of a category pill pre-selects that category in the Add New Rule form and focuses the keywords input. Eliminates the need to manually select the category from the dropdown when adding to an existing rule group.

#### App Categories — save now retroactively recategorizes
- `POST /api/categories` now runs a retroactive recategorization pass over the last 7 days of activity records after saving. Any app whose category has changed is updated immediately in the database — no need to wait for new activity to be logged. Returns `{"ok": true, "recategorized": N}` with count of updated rows.
- `categorize()` helper added to `dashboard/app.py` — mirrors `monitor.py` logic; used for retroactive DB updates on categories save.

#### API
- `GET /api/browser-breakdown` — returns today's category breakdown filtered to browser apps only (apps listed in `categories['browsing']['apps']`), plus a separate productivity score and total browser minutes. Same chart data format as `/api/today`.
- `GET /favicon.ico` → 204 — silences browser 404 noise.

### Fixed
- **Donut chart legend toggle broken** — `ci.hide(datasetIndex, dataIndex)` is the dataset-level API for bar/line charts and has no effect on doughnut slice visibility. Fixed by replacing with `chart.toggleDataVisibility(index)` + `chart.update()`, which is the correct Chart.js 4 API for per-slice doughnut visibility.

### Changed
- Backup version string in `api_backup()` updated to `"1.3.0"`

---

## [1.2.0] — 2026-03-08

### Added

#### Dashboard
- **Score Killers panel** — shows the top 5 apps by time in non-productive categories (everything outside Deep Work, Terminal, Documentation, Planning, AI Tools, Idle). Appears below the Today category breakdown. Answers "why is my score low" without any digging.
- New API endpoint: `GET /api/score-killers` — returns top 5 apps with category and minutes

#### Settings Panel — Logs tab (new)
- View any service log file directly in the dashboard (no terminal required)
- Dropdown to select log: Monitor log, monitor stdout/stderr, dashboard stdout/stderr
- Refresh button to reload; auto-scrolls to most recent entries (last 200 lines)
- **Download button** (⬇) — downloads the full raw log file for offline analysis
- New API endpoint: `GET /api/logs?log=<name>` — returns last 200 lines + metadata
- New API endpoint: `GET /api/logs/download?log=<name>` — streams full file as attachment

#### Settings Panel — Backup tab (new)
- **Download Backup** — exports `config.json` + `categories.json` as a single timestamped JSON file
- **Restore from Backup** — file picker accepts a previously downloaded backup; validates before enabling restore; writes both config and categories atomically
- New API endpoint: `GET /api/backup` — returns version-stamped backup bundle
- New API endpoint: `POST /api/restore` — accepts backup bundle, writes config and categories

#### Settings Panel — General tab
- **Dashboard port** field — change the listening port from within the UI. Saved to `config.json`; requires dashboard restart to rebind the socket (monitor keeps running uninterrupted)
- `dashboard_port` added to safe-key whitelist for `POST /api/config`

#### App Categories — drag and drop
- App tags in the App Categories editor are now draggable — drag any tag and drop it onto a different category pill to move it
- State tracked client-side; committed on **Save Categories**

#### Monitor
- **48-hour log rotation** — log files are truncated (not rotated to dated backups) every 48 hours via a custom `_OverwriteRotatingHandler` subclass. Logs never grow without bound; old files are never left on disk.

#### Installer (`install.py`)
- **Interactive port prompt** with validation — rejects non-integers and out-of-range values (must be 1024–65535), re-prompts until valid. `--defaults` mode skips interaction and uses 5555.
- `ask_port()` helper function replaces the previous bare `ask("Dashboard port", "5555")` call

#### Categories
- `"goose"` added to `deep_work` app list — Goose sessions now count as productive time

### Changed
- `POST /api/config` safe-key whitelist expanded to include `dashboard_port`
- Backup version string in `api_backup()` updated to `"1.2.0"`

---

## [1.1.0] — 2026-03-08

### Added

#### Settings Panel (new — all 4 tabs)
- **Appearance tab** — Dark / Light / System theme toggle. CSS custom properties (`--bg`, `--card-bg`, etc.) with `.light-theme` class on `<html>`; Bootstrap uses `data-bs-theme`; Chart.js destroys and redraws on theme change. Theme persisted in `localStorage`.
- **General tab** — Auto-categorize toggle. Saved to `config.json`; takes effect on next poll with no restart.
- **App Categories tab** — Live editor for `categories.json`. Select a category pill, add/remove app name tags, save. Changes picked up within one 30-second poll.
- **Browser Rules tab** — Manage `window_overrides` for browser categories. Add rules (comma-separated keywords → target category), delete rules, reorder with ↑↓ buttons. First-match-wins ordering.

#### API endpoints
- `GET /api/categories` — returns current `categories.json`
- `POST /api/categories` — writes updated categories, returns `{ok: true}`
- `GET /api/config` — returns dashboard-editable config keys
- `POST /api/config` — writes whitelisted keys only (`auto_categorize`, `poll_interval_seconds`, `idle_threshold_seconds`)

### Changed
- `monitor.py` — moved `load_categories()` and `config_loader.load()` inside the main poll loop so live edits apply within one cycle, no daemon restart required
- `config_loader.py` — added `auto_categorize: True` to defaults; fixed Python 3.9 incompatibility (`Path | None` union syntax → bare return annotation)
- `config.json` — added `auto_categorize: true`; fixed `data_dir: ""` which resolved to wrong OS default path
- `install.py` — added `auto_categorize` to generated config; bumped banner to v1.1.0
- `install.sh` — header updated to v1.1.0

### Fixed
- **Python 3.9 crash** — `def sync_dir() -> Path | None:` is 3.10+ union syntax. Changed to bare `def sync_dir():`. Was causing silent startup failure on 3.9.
- **SQLite "no such table"** — `data_dir: ""` in `config.json` resolved (via `config_loader` defaults) to the OS application support path instead of the project `data/` folder. Fixed by writing an explicit `data_dir` path during install.

---

## [1.0.0] — 2026-03-08

### Added

#### Core monitoring
- Background daemon (`monitor.py`) — polls active app and window title every 30 seconds using platform-native APIs; writes to SQLite
- macOS: `osascript` → System Events for app name + window title; `ioreg` for idle time
- Linux: `xdotool` for active window; `xprintidle` for idle time
- Windows: `pywin32` / `ctypes` for foreground window; `ctypes` for idle time
- Idle detection — any period exceeding `idle_threshold_seconds` (default 300s) logged as `"idle"` rather than inflating category totals
- Automatic app categorisation via `categories.json` — partial, case-insensitive app name matching; browser window title keyword overrides (first-match-wins)
- SQLite schema — `activity` table (timestamp, app, window_title, category, idle_seconds, duration_seconds) and `recommendations` table

#### Dashboard (`dashboard/app.py` + `index.html`)
- Flask web server on configurable port (default 5555), served at `http://localhost:5555`
- Dark theme, Bootstrap 5.3, Chart.js
- **Productivity Score** (0–100): `(productive_time / total_active) * 100 − (distraction / total_active) * 35`
  - Productive: Deep Work, Terminal, Documentation, Planning, AI Tools
  - Distraction subtracts at 35% weight
- **Today panel** — donut chart of time by category, active/idle/total minutes, first-seen time
- **7-day trend** — stacked bar chart (Productive / Communication / Distraction / Other) with daily score
- **Hourly timeline** — dominant category per hour, 6am–midnight, skips empty hours
- **Top Windows** — top 20 app+window combinations by time today
- **Recommendations panel** — dismissable cards with priority ordering
- Auto-refresh: fast data every 60s, charts and recommendations every 5 minutes

#### API endpoints (v1.0.0)
- `GET /api/status` — monitor heartbeat (last seen, current app/category)
- `GET /api/today` — today's score, category breakdown, chart data
- `GET /api/weekly` — 7-day breakdown with per-day scores
- `GET /api/timeline` — hourly dominant-category breakdown for today
- `GET /api/top-windows` — top 20 app+window pairs by time today
- `GET /api/recommendations` — undismissed recommendations ordered by priority
- `POST /api/dismiss/<id>` — mark a recommendation dismissed
- `GET /api/weekly-scores` — 7-day score history for sparkline

#### Seeded recommendations (written to DB on first run)
1. Build a ServiceNow MCP Server (high)
2. Daily Lab Brief Agent — morning script (high)
3. Network Baseline + Drift Detection Agent (high)
4. Policy Compliance Checker Agent (high)
5. Script Template Library MCP (medium)
6. Batch communication windows workflow (medium)
7. End-of-day review + tomorrow's priorities ritual (medium)
8. Goose Agent: Lab Onboarding Automation (medium)
9. Build a Jira MCP Server (medium)

#### Cross-platform support
- `platform_utils.py` — OS abstraction layer for app detection and idle time (macOS / Linux / Windows)
- `config_loader.py` — reads `config.json`, provides OS-appropriate path defaults
- `config.json` — user-editable settings: `data_dir`, `dashboard_port`, `poll_interval_seconds`, `idle_threshold_seconds`, `sync_enabled`, `sync_path`, `auto_categorize`

#### Installers
- `install.py` — cross-platform interactive installer; sets up macOS LaunchAgents, Linux systemd user services, or Windows Task Scheduler entries; writes `config.json`
- `install.sh` — legacy macOS-only bash installer (kept for reference; prefer `install.py`)
- `uninstall.py` — cross-platform service removal
- `uninstall.sh` — legacy macOS-only bash uninstaller

#### Multi-machine support
- `sync.py` — export/import recommendations via any shared folder (`export`, `import`, `status`, `path` subcommands)
- `deploy.sh` — rsync code to remote Mac + SSH to run `install.py --defaults`; never touches `data/`
- `vault-sync.sh` — legacy bash version of sync (macOS only; use `sync.py` instead)
- `.deployrc` — stores `REMOTE_HOST`, `REMOTE_PATH`, `VAULT_PATH` (gitignored)

#### Documentation
- `README.md` — full documentation: system requirements, installation, configuration, dashboard guide, scoring breakdown, multi-machine sync, troubleshooting, file reference
- `DEPLOY.md` — beginner-friendly step-by-step multi-Mac deployment guide
