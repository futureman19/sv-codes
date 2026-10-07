# Static site navigation

Every `docs/**/*.html` page has exactly one `nav.svc-site-nav[aria-label="Primary"]` immediately after the opening body (before any page content). Load `/site-navigation.css` **after** page-local styles. Do not inject navigation with JavaScript.

Copy this block and change only the active marker. Keep the brand SVG and the four destinations identical:

```html
<nav class="svc-site-nav" aria-label="Primary">
  <div class="svc-site-nav__inner">
    <a class="svc-site-nav__brand" href="/" aria-label="SV Codes home"><svg width="22" height="22" viewBox="0 0 8 8"><rect width="8" height="8" fill="white"/><rect width="2" height="2" fill="#00ffff"/><rect x="6" width="2" height="2" fill="#ff00ff"/><rect y="6" width="2" height="2" fill="#ffff00"/><rect x="6" y="6" width="2" height="2" fill="#ff0000"/><rect x="3" y="3" width="1" height="1" fill="black"/><rect x="4" y="2" width="1" height="1" fill="black"/><rect x="2" y="5" width="1" height="1" fill="black"/></svg><span>SV·CODES</span></a>
    <div class="svc-site-nav__links">
      <a href="/" aria-current="page">Home</a>
      <a href="/#scan">Scan</a>
      <a href="/nft/">NFT</a>
      <a href="/experimental/">Experimental</a>
    </div>
  </div>
</nav>
```

## Section and breadcrumb rules

- `/` and `/index.html`: Home is current. Scan is a same-page shortcut to `/#scan`, not a separate page; static markup does not pretend to track hash changes.
- Everything under `/nft/`: NFT is current.
- Experimental hub, `/market-preview/` (including wallet and chain), `/ble/`, `/verify/`, `/j/`: Experimental is current.
- Exactly one primary link carries `aria-current="page"` (the current section's landing page). No active marker on the logo.
- Nested tools/artwork follow the primary nav with `.svc-breadcrumbs`, `role="navigation"`, `aria-label="Breadcrumb"`. Link the section, then intermediate parents such as Atomic trade lab or SV-GENESIS, then a non-link current-page label. Do not restore the old competing global nav.
- Contextual series links, source links, downloads and cross-links belong in page content or footers. Specs and GitHub remain in the home footer and Experimental footer.

## Direct links and scope

Keep all original page paths, query parameters, IDs and runtime scripts. The original Alley #12 detail stays at `/nft/` below the new hub, with `/nft/#alley` as its direct anchor. Existing scanner links now use `/#scan`; the legacy `/#broadcast` anchor is retained beside the scanner. Encoder is `/#demo`.

All navigation and hub styles use `svc-` names. The nav explicitly overrides old generic `nav` styles without changing tool layouts. At mobile widths the brand and tabs occupy separate rows; below 360px the tabs form two rows. Primary links and breadcrumbs have at least 44px height and visible keyboard focus. Artwork previews use existing files, with no cropping of their seals.

When adding a page, add it to the appropriate hub and reuse this markup. When updating cached shell markup/styles, bump `SHELL` in `sw.js`. `CORE` includes both hub URLs, their index aliases and the shared CSS; artwork remains network-first/on-demand rather than expanding the mandatory install download. Do not change POST/share handling or the mint-service cache bypass.

## Checks

From repository root, run `python poc/test_site_navigation.py` and `git diff --check`. The static test checks common tabs/current sections, destination coverage, local href/src and fragments, duplicate IDs, and unchanged existing scripts. Also check navigation visually at 320px, 390px and desktop widths with keyboard focus. These checks do not substitute for independent decoder or mint-flow regression checks.
