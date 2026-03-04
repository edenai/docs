# Eden AI Documentation

Official documentation repository for [Eden AI](https://edenai.co) - the unified API platform for accessing multiple AI providers through a single interface.

## About This Repository

This repository contains the complete documentation for Eden AI's V3 API, built using [Mintlify](https://mintlify.com). The documentation includes guides, tutorials, API references, and integration examples for developers using Eden AI's services.

## What is Eden AI?

Eden AI is a unified API platform that provides:
- **Universal AI Endpoint** - Single endpoint for all AI features (text analysis, OCR, image processing, translation)
- **OpenAI-Compatible LLM** - Drop-in replacement for OpenAI's API with multi-provider support
- **Smart Routing** - Intelligent provider selection based on cost, performance, and reliability
- **Persistent File Storage** - Upload files once, use them across multiple requests
- **Built-in API Discovery** - Explore features and providers programmatically

## Documentation Structure

### V3 Documentation
- **Get Started** - Introduction, smart routing, FAQ, enterprise offerings, and professional services
- **How-To Guides** - Step-by-step guides for authentication, cost management, discovery, user management, smart routing, Universal AI, LLM endpoints, and file uploads
- **Tutorials** - Practical tutorials for optimizing LLM costs, tracking spending, and managing tokens
- **Integrations** - SDKs (Python, TypeScript), AI assistants (Claude Code, Continue.dev), frameworks (LangChain), and chat platforms (LibreChat, Open WebUI)
- **Changelog** - Version history and updates

### V3 API Reference
OpenAPI specifications for:
- AI Features (Universal AI endpoint)
- Cost Management
- User Management

## Local Development

### Prerequisites
Install the [Mintlify CLI](https://www.npmjs.com/package/mint):

```bash
npm i -g mint
```

### Running Locally

Navigate to the documentation root directory and run:

```bash
mint dev
```

View the documentation at `http://localhost:3000`

### Troubleshooting
- If the dev environment isn't running: Run `mint update` to get the latest CLI version
- If pages load as 404: Ensure you're in a directory with a valid `docs.json` file

## Repository Contents

- `/v3/` - V3 API documentation pages
- `/v3/features/` - **Auto-generated** AI feature reference pages (do not edit manually)
- `/scripts/` - Automation scripts (see below)
- `/tests/` - Automated test suite for Python code snippets (see [tests/README.md](tests/README.md))
- `/shared/` - Reusable content snippets
- `/openapi/` - OpenAPI specification files
- `/images/` - Documentation images and assets
- `/logo/` - Eden AI logo files (light/dark mode)
- `docs.json` - Mintlify configuration file
- `index.mdx` - Documentation homepage

## Auto-Generated AI Feature Pages

The `v3/features/` directory contains automatically generated documentation for all Universal AI features. These pages are created by `scripts/generate_features.py`, which fetches live data from the production `/v3/info` API.

### What gets generated

For each AI subfeature (e.g. text/moderation, image/generation, ocr/ocr):
- An individual `.mdx` page with:
  - Input/output schema tables (field name, type, required, description)
  - Available providers and models with pricing
  - **Quick-start code examples** (Python + cURL) — built automatically from the input schema. The script picks the first available model, generates realistic placeholder values for each required field (e.g. `"en"` for language, `"The quick brown fox..."` for text), and renders ready-to-copy snippets inside Mintlify `<CodeGroup>` tabs. Async features get a note about polling the job endpoint.
- An `index.mdx` overview page with cards grouped by feature category
- The `AI Features` navigation group in `docs.json` is updated automatically

When a feature is added or removed from the API, the generator picks it up: new pages are created and stale pages are deleted.

### How to run manually

```bash
python scripts/generate_features.py
```

No dependencies beyond Python stdlib. The script hits the production API at `https://api.edenai.run/v3/info`.

### How to test

1. Run the script and verify the output:
   ```bash
   python3 scripts/generate_features.py
   ```
2. Check that pages were generated under `v3/features/`:
   ```bash
   ls v3/features/*/
   ```
3. Preview locally with Mintlify to verify rendering:
   ```bash
   npx mint dev
   ```
4. Confirm the `AI Features` group appears in the sidebar under V3 Documentation.

### CI/CD automation

A GitHub Actions workflow (`.github/workflows/generate-features.yml`) runs this script daily at 06:00 UTC and on manual dispatch. If any pages changed, it opens a PR on the `auto/update-feature-docs` branch for review.

### Known limitation: missing output field descriptions

Input schema fields include descriptions (e.g. "Text to moderate", "ISO 639-1 language code"), but **output schema fields currently have no descriptions**. This is because the upstream Pydantic output models in `edenai-apis` don't define `Field(description=...)` on their fields. The generator and `/v3/info` API already support descriptions when present — the fix is to add `Field(description="...")` to the output dataclasses in `edenai-apis`.

## Configuration

The documentation is configured via `docs.json`, which includes:
- Navigation structure and tabs
- Theme and branding (colors, logos, favicon)
- Navbar and footer links
- OpenAPI integration
- Contextual features (copy, view, AI assistant integrations)

## Publishing Changes

Changes are automatically deployed to production when pushing to the main branch. The GitHub app integration propagates changes from this repository to the live documentation site.

## Links

- **Live Documentation**: https://docs.edenai.co
- **Eden AI Dashboard**: https://app.edenai.run
- **Website**: https://edenai.co
- **Status Page**: https://app-edenai.instatus.com
- **GitHub**: https://github.com/edenai
- **Discord**: https://discord.gg/VYwTbMQc8u

## Support

For issues or questions about the documentation:
- Visit the [Eden AI website](https://edenai.co)
- Join the [Discord community](https://discord.gg/VYwTbMQc8u)
- Check the [GitHub repositories](https://github.com/edenai)

## Contributing

This is the official documentation repository for Eden AI. For contributions or corrections, please contact the Eden AI team through the official channels.

---

Built with [Mintlify](https://mintlify.com)
