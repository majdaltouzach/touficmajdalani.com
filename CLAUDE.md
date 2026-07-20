# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev server (live reload)
hugo server

# Production build → output in public/
hugo

# Deploy to VPS (requires .env — see env.example)
./deploy

# Format templates/code
yarn prettier
```

## Architecture

Hugo static site using the `port-hugo` theme (vendored in `themes/port-hugo/` as a git subtree).

**All content lives in one file:** `data/content.yml`. Sections (hero, about, experience, skill, funfacts, portfolio) are toggled via `enable: true/false` in that file. No Markdown content pages exist for the main portfolio — this is a single-page portfolio.

**Two pages exist:**
- `/` — main portfolio (single-page, `layouts/index.html`)
- `/contact/` — contact form page (`content/contact.md` with `type: contact`, rendered by `layouts/contact/single.html`)

**Layout override pattern:** `layouts/` overrides theme defaults. Custom partials in `layouts/partials/` take precedence over `themes/port-hugo/layouts/partials/`. 

**Config:** `hugo.toml` controls nav menu, plugins (CSS/JS CDN links appended in `<head>`/`<body>`), social links, and site params. The `contentDir` key in `hugo.toml` is vestigial — no `content/english/` directory exists.

**Portfolio section is disabled** (`enable: false` in `data/content.yml`) because portfolio images must be in `assets/images/portfolio/` (not `static/`) and processed via Hugo's `.Fill` image pipeline — static images won't work. Required sizes: `780x500` (large) and `395x250` (thumbnail).

**Deploy:** `./deploy` script does two things: builds with `hugo` then `rsync`s `public/` to VPS, AND deploys `server/contact_handler.py` + `server/contact-handler.service` to `~/contact-handler/` on the VPS and (re)starts the systemd service.

## Contact Handler (`server/`)

The contact form at `/contact/` POSTs JSON to `/contact-submit`. This requires:

1. **Python service** (`server/contact_handler.py`) — stdlib HTTP server listening on `127.0.0.1:5001`. Handles rate limiting (5 req/IP/hour), validates fields, sends confirmation email to submitter + copy to owner via ProtonMail SMTP. Config from env vars — fails fast if `SMTP_USER`/`SMTP_PASS` missing.

2. **Systemd service** (`server/contact-handler.service`) — runs as user `toufic`, reads `/etc/contact-handler.env` (not tracked in git; create from `server/contact-handler.env.example`). `./deploy` installs/reloads this automatically.

3. **Nginx reverse proxy** (manual VPS setup, not in repo) — must proxy `/contact-submit` → `127.0.0.1:5001`. Without this, contact form submissions return network errors in production.

## Key files

| File | Purpose |
|------|---------|
| `data/content.yml` | All site content — edit this to update text/sections |
| `hugo.toml` | Site config, nav, social links, CDN plugins |
| `layouts/index.html` | Main page template |
| `layouts/contact/single.html` | Contact page (form + inline CSS/JS) |
| `server/contact_handler.py` | Contact form backend (Python stdlib HTTP server) |
| `server/contact-handler.env.example` | Template for VPS env file (`/etc/contact-handler.env`) |
| `static/resume/` | PDF resume served directly |
| `assets/images/` | Images processed by Hugo pipelines (use for portfolio) |
| `static/images/` | Images served as-is (use for bg, profile, icons) |

## Gotchas

- `hugo.toml` has `google_analytics = "G-ABCDEFG123"` placeholder — update before real deployment.
- Individual `experience_list` entries support `enable: false` to hide without deleting (template skips them).
- FontAwesome Pro CDN link in `hugo.toml` — icons may not render if the CDN token/URL changes.
- Nav links use absolute anchors (`/#home`, `/#about`) so they work from the `/contact/` page too.
- Netlify is also configured (`netlify.toml`) targeting Hugo 0.85.0 — local Hugo version may differ.
