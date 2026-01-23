# Eden AI Documentation

Official documentation repository for [Eden AI](https://edenai.co) - the unified API platform for accessing multiple AI providers through a single interface. [Eden AI Docs](https://docs.edenai.co/).

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
- **Get Started** - Introduction, smart routing, FAQ, and enterprise offerings
- **How-To Guides** - Step-by-step guides for authentication, cost management, user management, smart routing, Universal AI, LLM endpoints, file uploads, and API discovery
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
- `/shared/` - Reusable content snippets
- `/openapi/` - OpenAPI specification files
- `/images/` - Documentation images and assets
- `/logo/` - Eden AI logo files (light/dark mode)
- `docs.json` - Mintlify configuration file
- `index.mdx` - Documentation homepage

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
