# Why the docs are not indexed by Google

The documentation is served by Mintlify at `https://www.edenai.co/docs`, behind Cloudflare. Google shows almost none of its pages.

These notes were written on 2026-09-29 from checks run against the live site. Nobody has looked at Search Console yet, so every cause below is a strong lead, not a confirmed diagnosis. The first step is to confirm them there.

## The problem in short

The pages themselves are fine: Google can fetch them and is allowed to index them. What seems to be missing is everything that leads Google to them:

1. **Google is never told where the docs sitemap is.** The only `robots.txt` Google reads is the main website's, and it lists only the main website's sitemap, which contains no docs URLs.
2. **The move from `docs.edenai.co` is not finished, and part of it dead-ends.** The search index still holds the old `docs.edenai.co` addresses. The oldest ones redirect to a 404, so their ranking goes nowhere.
3. **Two Mintlify hosts serve a full copy of the docs.** Their canonical tags point at the right place, but Google treats canonical tags as a hint, not a rule.
4. **Minor: the main website links to the docs through redirects.**

## What has been ruled out

| Check | Result |
|-------|--------|
| Page status | 200 |
| `noindex` meta tag or `X-Robots-Tag` header | None |
| Canonical tag | Each page points to its own URL on `www.edenai.co/docs` |
| Rendering | The page content is in the HTML the server sends, not only built by JavaScript |
| Docs sitemap | `https://www.edenai.co/docs/sitemap.xml` lists 172 URLs; every one sampled returns 200 |
| Missing page | Returns a real 404, not a 200 "not found" page |
| Request with a Googlebot user agent | 200. This only proves requests pretending to be Googlebot pass; real Googlebot comes from Google's IPs (see Cloudflare below) |
| Global `canonical` in `docs.json` | Harmless. Mintlify adds each page's path to it, as the rendered tags show |

## Likely causes, with evidence

### 1. Google never learns where the docs sitemap is

Google reads `robots.txt` only at the root of a host. A `robots.txt` in a subfolder is ignored.

- `https://www.edenai.co/robots.txt` belongs to the main website. Its only sitemap line is `Sitemap: https://www.edenai.co/sitemap.xml`.
- That sitemap has 1,876 URLs and **none** of them is under `/docs`.
- The file that does list the docs sitemap is `https://www.edenai.co/docs/robots.txt`, which Mintlify generates. Because it sits in a subfolder, Google ignores it.

So unless someone submitted the docs sitemap in Search Console, Google finds docs pages only by following links, and few links point there.

### 2. The move from `docs.edenai.co`

The docs used to live at `docs.edenai.co`. It now sends a permanent (301) redirect, keeping the path, to `www.edenai.co/docs`:

| Old URL | Where it ends up | Result |
|---------|------------------|--------|
| `docs.edenai.co/v3/llms/chat-completions` | `www.edenai.co/docs/v3/llms/chat-completions` | 200, correct |
| `docs.edenai.co/docs/webhooks` | `www.edenai.co/docs/docs/webhooks` | **404** |
| `docs.edenai.co/docs/monitoring` | `www.edenai.co/docs/docs/monitoring` | **404** |
| `docs.edenai.co/docs/rag-pricing` | `www.edenai.co/docs/docs/rag-pricing` | **404** |
| `docs.edenai.co/docs/additional-parameters` | `www.edenai.co/docs/docs/additional-parameters` | **404** |

A web search for `site:edenai.co/docs` still returns those `docs.edenai.co/docs/...` pages. The only new-location result is `www.edenai.co/docs`. That search did not run on Google, so confirm it in Search Console. It does suggest the index still holds the old host.

Google says a move like this takes "a few weeks or more" for a site this size. It also warns against sending many old URLs to one unrelated page, such as a homepage: it treats those as soft 404s.

### 3. Duplicate copies on Mintlify hosts

`https://edenai.mintlify.app/...` and `https://edenai.mintlify.dev/docs/...` both return 200 with the full site. Their canonical tags point at `www.edenai.co/docs`, which helps. Mintlify's own help center still notes that Google can index these copies, and sometimes ranks them above the custom domain.

### 4. How the main website links to the docs

The homepage has 7 links into the docs:

- 4 go to `https://edenai.co/docs/`, which takes two redirects before reaching `https://www.edenai.co/docs`.
- 2 go to `https://www.edenai.co/docs`, which is correct.
- 1 goes to `/docs/v3/llms/smart-routing`, which redirects (308) to `/docs/v3/llms/provider-routing`.

## Where to look

| Place | What to look at | Who has access |
|-------|-----------------|----------------|
| Google Search Console | Whether a property covers `www.edenai.co/docs`, submitted sitemaps, the Pages report, URL Inspection, Crawl stats | Whoever owns SEO or the `edenai.co` domain |
| Main website | The `robots.txt` and `sitemap.xml` served at `www.edenai.co`, and the homepage links | Main website owner |
| Cloudflare | The redirect rule from `docs.edenai.co`, the rule or Worker that forwards `/docs` to Mintlify, and Security events for Googlebot | Whoever runs the `edenai.co` zone |
| Mintlify | Which Mintlify host the `/docs` proxy forwards to; a request to switch off the spare copies | Mintlify dashboard admin, support@mintlify.com |
| This repo, `docs.json` | The `redirects` list, which is where to fix the 404s for old URLs | Docs team |
| Google Analytics | Old `docs.edenai.co` landing pages that now reach a 404 | Analytics owner |

## How to investigate

### Step 1. Search Console (most of the answer is here)

1. **Check a property covers the docs.** A Domain property for `edenai.co`, verified through DNS, covers every subdomain and path, including `docs.edenai.co`. With only a URL-prefix property for `https://www.edenai.co/`, the old host has no view.
2. **Sitemaps.** Is `https://www.edenai.co/docs/sitemap.xml` submitted? If yes, check its status, when Google last read it, and how many URLs it discovered.
3. **Pages report, filtered to the docs sitemap.** Note how many pages are indexed versus not, and why. What each reason points to:
   - *Discovered, currently not indexed*: Google knows the URL but has not fetched it. This points to causes 1 and 4.
   - *Crawled, currently not indexed*: Google fetched the page and chose not to index it. This points to content quality or duplication.
   - *Duplicate, Google chose different canonical than user*: points to cause 3. Check which URL Google chose.
   - *Page with redirect* or *Not found (404)*: points to cause 2.
4. **URL Inspection** on three pages: `https://www.edenai.co/docs`, `https://www.edenai.co/docs/v3/llms/chat-completions` and `https://www.edenai.co/docs/v3/expert-models/features/web/search`. For each, read "Google-selected canonical", "Crawl allowed?" and "Page fetch", then run **Test live URL**.
5. **Crawl stats** (Settings > Crawl stats) for `www.edenai.co`. Look for 403 or 5xx responses on `/docs` URLs. Those would mean something is blocking real Googlebot.
6. **The old host.** If `docs.edenai.co` has its own property, open its Pages report and its Performance report to see which old URLs still get impressions.

### Step 2. Repeat the checks from a terminal

Anyone can run these; no access is needed. Each comment gives the result on 2026-09-29.

```bash
# The robots.txt Google reads, and the sitemap it lists
curl -s https://www.edenai.co/robots.txt | grep -i sitemap
# -> Sitemap: https://www.edenai.co/sitemap.xml   (no docs sitemap)

# Docs URLs in the main sitemap
curl -s https://www.edenai.co/sitemap.xml | grep -o '<loc>[^<]*/docs[^<]*</loc>' | wc -l
# -> 0

# URLs in the docs sitemap
curl -s https://www.edenai.co/docs/sitemap.xml | grep -o '<loc>' | wc -l
# -> 172

# Canonical and robots tags on a docs page
curl -s https://www.edenai.co/docs/v3/llms/chat-completions | grep -oE '<link rel="canonical"[^>]*>|<meta name="robots"[^>]*>'
# -> canonical to itself, no robots meta tag

# X-Robots-Tag header on a docs page
curl -sI https://www.edenai.co/docs/v3/llms/chat-completions | grep -ciE '^x-robots-tag'
# -> 0

# An old URL: where it redirects, and what is there
curl -s -o /dev/null -w '%{http_code} -> %{redirect_url}\n' https://docs.edenai.co/docs/webhooks
curl -s -o /dev/null -w '%{http_code}\n' https://www.edenai.co/docs/docs/webhooks
# -> 301 -> https://www.edenai.co/docs/docs/webhooks, then 404

# A Mintlify copy of the site
curl -s -o /dev/null -w '%{http_code}\n' https://edenai.mintlify.app/v3/llms/chat-completions
# -> 200

# Homepage links into the docs
curl -s https://www.edenai.co | grep -oE 'href="https?://(www\.)?edenai\.co/docs[^"]*"' | sort | uniq -c
```

### Step 3. Cloudflare

1. **Security > Events**, filtered to user agents containing `Googlebot` and to paths starting with `/docs`. Any block or challenge means real Googlebot is being turned away. Check Bot Fight Mode and any WAF rules too.
2. **The redirect rule for `docs.edenai.co`.** Confirm it is a 301 and see how it maps paths. It currently keeps the path as is, so `/docs/x` becomes `/docs/docs/x`.
3. **The `/docs` proxy.** Write down which host it forwards to (`edenai.mintlify.app`, `edenai.mintlify.dev` or `<subdomain>.mintlify.site`). That host must not be switched off in step 5 of the fixes.

### Step 4. List the old URLs worth redirecting

Use Search Console on the old host (Performance > Pages) or Google Analytics (landing pages on `docs.edenai.co`). List the old URLs that still get impressions or visits and now end at a 404, and pair each with its closest v3 page.

## Fixes, in order

| # | Fix | Where | Effort |
|---|-----|-------|--------|
| 1 | Submit `https://www.edenai.co/docs/sitemap.xml` in Search Console, then Request indexing on the key pages | Search Console | Minutes |
| 2 | Add `Sitemap: https://www.edenai.co/docs/sitemap.xml` to `https://www.edenai.co/robots.txt`. Several `Sitemap:` lines are allowed | Main website | Minutes |
| 3 | Redirect each old `/docs/...` URL to its closest v3 page, never to the homepage. A `redirects` entry in `docs.json` with source `/docs/webhooks` catches `docs.edenai.co/docs/webhooks` after the Cloudflare hop | This repo | An hour, once step 4 above gives the list |
| 4 | Point homepage links at `https://www.edenai.co/docs` and `/docs/v3/llms/provider-routing` directly | Main website | Minutes |
| 5 | Ask Mintlify support to make the unused Mintlify host return 404. Verify it in Search Console first, and never switch off the host the proxy uses | Mintlify support | A support ticket |

## How to tell it worked

- The Sitemaps report shows the docs sitemap read successfully, with 172 URLs discovered.
- In the Pages report, the indexed count for the docs sitemap rises week over week.
- URL Inspection on a docs page says "URL is on Google", and the Google-selected canonical is its `www.edenai.co/docs/...` address.
- A `site:www.edenai.co/docs` search on Google returns new-location pages. Expect this to take several weeks.

## Sources

- [Mintlify: Reverse proxy](https://www.mintlify.com/docs/deploy/reverse-proxy)
- [Mintlify: SEO](https://www.mintlify.com/docs/optimize/seo)
- [Mintlify: Default subdomain indexed alongside custom domain](https://www.mintlify.com/docs/help-center/default-subdomain-indexed-alongside-custom-domain)
- [Mintlify discussion #2626: noindex for .mintlify.app subdomains](https://github.com/orgs/mintlify/discussions/2626)
- [Google: Site moves with URL changes](https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes)
- [Google: Create and submit a robots.txt file](https://developers.google.com/crawling/docs/robots-txt/create-robots-txt)
- [Search Console Help: robots.txt report](https://support.google.com/webmasters/answer/6062598?hl=en)
