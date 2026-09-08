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

## Preview locally

```bash
cd docs && python3 -m http.server 4000
```

Then open http://localhost:4000

## Email capture

The homepage form is static and not yet wired up. To connect Mailchimp: set the
`<form action>` to your Mailchimp POST URL and keep the input `name="EMAIL"`. No JS needed.
