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

**All content lives in one file:** `data/content.yml`. Sections (hero, about, experience, skill, funfacts, portfolio) are toggled via `enable: true/false` in that file. The main site is a single-page portfolio; the only separate page is `/contact/` (see below).

**Layout override pattern:** `layouts/` overrides theme defaults. Custom partials in `layouts/partials/` take precedence over `themes/port-hugo/layouts/partials/`. The main page template is `layouts/index.html`.

**Config:** `hugo.toml` controls nav menu, plugins (CSS/JS CDN links appended in `<head>`/`<body>`), social links, and site params. The `contentDir` key in `hugo.toml` is vestigial — no `content/english/` directory exists.

**Portfolio section is disabled** (`enable: false` in `data/content.yml`) because portfolio images must be in `assets/images/portfolio/` (not `static/`) and processed via Hugo's `.Fill` image pipeline — static images won't work. Required sizes: `780x500` (large) and `395x250` (thumbnail).

**Deploy:** `./deploy` script builds with `hugo` then `rsync`s `public/` to a VPS. Requires `.env` with `VPS_USER`, `VPS_HOST`, `VPS_DIR`. Netlify is also configured (`netlify.toml`) targeting Hugo 0.85.0 — local Hugo version may differ.

## Key files

| File | Purpose |
|------|---------|
| `data/content.yml` | All site content — edit this to update text/sections |
| `hugo.toml` | Site config, nav, social links, CDN plugins |
| `layouts/index.html` | Main page template |
| `static/resume/` | PDF resume served directly |
| `assets/images/` | Images processed by Hugo pipelines (use for portfolio) |
| `static/images/` | Images served as-is (use for bg, profile, icons) |
| `content/contact.md` | Minimal front-matter stub that activates the contact page |
| `server/` | VPS contact-form backend (Python, systemd service, env example) |

## Contact form infrastructure

`/contact/` is a real Hugo page (`content/contact.md`, type `contact`) rendered by `layouts/contact/single.html`. The form POSTs JSON to `/contact-submit`, which nginx must proxy to the VPS backend at `127.0.0.1:5001`.

**Backend:** `server/contact_handler.py` — Python stdlib HTTP server, no deps. Handles `POST /contact-submit`, rate-limits (5/IP/hour), sends ProtonMail SMTP emails to both submitter and owner.

**VPS setup:**
- Copy `server/contact_handler.py` → `/home/toufic/contact-handler/`
- Copy `server/contact-handler.service` → `/etc/systemd/system/` and `systemctl enable --now contact-handler`
- Create `/etc/contact-handler.env` from `server/contact-handler.env.example` (never commit real file)
- nginx: `proxy_pass http://127.0.0.1:5001;` for `location /contact-submit`

**Nav split:** Home/About links use `/#home` / `/#about` (anchors on the homepage); Contact uses `/contact/` (separate page). This is intentional — keep consistent when adding menu items.

## Gotchas

- `hugo.toml` has placeholder values: `author = "Jack Davis"` and `google_analytics = "G-ABCDEFG123"` — update before real deployment.
- Individual `experience_list` entries support `enable: false` to hide without deleting (template skips them).
- FontAwesome Pro CDN link in `hugo.toml` — icons may not render if the CDN token/URL changes.
