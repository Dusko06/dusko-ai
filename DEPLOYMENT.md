# Deployment notes

1. Set `SGAI_API_KEY` as a secret in the host. Never commit `.env` or expose API keys.
2. Verify the endpoint, request payload and authentication header against the current ScrapeGraphAI API documentation before production deployment; the starter uses `/v1/smartscraper` with `SGAI-APIKEY`.
3. Keep batch sizes small until you understand pricing and rate limits.
4. Deploying this API does not automatically connect it to ChatGPT as a custom MCP tool. That requires an MCP-compatible adapter and a ChatGPT interface/plan that supports custom MCP connections.
5. Respect website terms, robots directives, privacy requirements, and applicable law. Verify extracted data before contacting prospects.
