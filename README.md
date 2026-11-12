# OSO Organised — marketing website

Static HTML/CSS marketing site for **OSO Organised**, hosted on GitHub Pages from the `/docs` folder.
Live at **https://osoorganised.co.uk** (custom domain set via `docs/CNAME`).

## What's here

| Page | Path |
| --- | --- |
| Homepage | `docs/index.html` |
| Features overview | `docs/features/index.html` |
| Feature: Manage clients & bookings | `docs/features/manage-clients-and-bookings/index.html` |
| Feature: Get paid | `docs/features/get-paid/index.html` |
| Feature: Understand your business | `docs/features/understand-your-business/index.html` |
| Pricing | `docs/pricing/index.html` |
| About & Contact | `docs/about/index.html` |
| Content Hub index | `docs/content-hub/index.html` |
| Blog: How to organise a cleaning business | `docs/content-hub/how-to-organise-a-cleaning-business/index.html` |
| Blog: Chasing late payments | `docs/content-hub/chase-late-payments-without-the-awkwardness/index.html` |

Shared: `docs/style.css` (design system + all styles), `docs/script.js` (mobile nav only),
`docs/assets/` (SVG logo + illustrations), `docs/sitemap.xml`, `docs/robots.txt`, `docs/404.html`.

## Design system

All colours and type live as CSS custom properties at the top of `docs/style.css`.
Font: **Outfit** (Google Fonts). Brand colours: `#101585` dark purple, `#FEB555` orange,
`#CA90AF` pink, `#a0a1ce` light purple, `#E0E0E0` / `#F9F9F9` greys. Don't introduce new
colours or fonts — reuse the tokens.

## Editing content

Pages are plain HTML — edit the text directly. Each page has its own `<title>`,
meta description, canonical URL and JSON-LD near the top of the file. If you add a page,
also add it to `docs/sitemap.xml`.

Placeholder content (testimonials, pricing, stats, contact email) is marked in the page
with a "Placeholder" tag or a note — swap for real content when it's available.

## Legal documents

The Privacy Policy, Terms of Service and DPA (`docs/privacy/`, `docs/terms/`, `docs/dpa/`) are the
single source of truth: the OSO app links to these pages rather than keeping its own copy. The
cookie section of the Privacy Policy has a stable `#cookies` anchor that the app's consent banner
links to, so don't rename it.

Each document shows its version date (`Version dd/mm/yyyy`), which changes only for material
changes:

- **Minor change** (typo, formatting, clearer wording that doesn't change meaning): edit the page
  and leave the version alone. No notice is needed.
- **Material change** (anything that changes users' rights or what we do with their data): update
  the version date on the page **and** the matching entry in `docs/legal/versions.json` (ISO
  format, `yyyy-mm-dd`). Then email active subscribers before the change takes effect, and keep a
  copy of the email and the date it was sent. The app README has the full steps.

The app checks `versions.json` in CI and fails until its own copy of the versions is updated, so a
change can't go unnoticed. The app records which Terms and Privacy Policy versions each user
accepted when they subscribed. When the Privacy Policy version changes, the app also asks users
for analytics consent again.

## Preview locally

```bash
cd docs && python3 -m http.server 4000
```

Then open http://localhost:4000

## Email capture

The homepage form is static and not yet wired up. To connect Mailchimp: set the
`<form action>` to your Mailchimp POST URL and keep the input `name="EMAIL"`. No JS needed.
