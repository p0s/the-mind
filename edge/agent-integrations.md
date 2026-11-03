# Agent integrations

the-mind.xyz is a static, read-only explanatory site. It has no accounts,
API, tools, payments or outbound bots. It publishes agent discovery files only
when they describe something that exists. Decisions below were checked on
3 November 2026 against the linked specifications.

| Area | Status | Reason | What would change it |
| --- | --- | --- | --- |
| Agent Skills ([discovery RFC v0.2.0](https://github.com/cloudflare/agent-skills-discovery-rfc), [skill format](https://agentskills.io/specification)) | Published | Two read-only task skills over the public pages: explain the hypothesis with citations, and trace a claim to the claims ledger and the original locator. | Add a skill only for another real workflow over public pages. |
| API catalog ([RFC 9727](https://www.rfc-editor.org/rfc/rfc9727)) and OpenAPI | Not published | There is no API. `llms.txt`, the Markdown pages, `sitemap.xml` and the client-side search file are documents, not a versioned interface. | A documented, versioned public data interface, such as claims-ledger JSON with a schema and a stability promise. |
| MCP Server Card ([SEP-2127](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2127)) and A2A Agent Card ([discovery](https://a2a-protocol.org/latest/topics/agent-discovery/)) | Not published | No MCP server or A2A agent exists, and a card must describe a working service. Plain HTTPS requests already reach all 18 pages. | A real read-only MCP server, for example for search and claim lookup, that does something plain requests cannot, with its own security and privacy review. |
| OAuth discovery ([RFC 8414](https://www.rfc-editor.org/rfc/rfc8414)), protected resource metadata ([RFC 9728](https://www.rfc-editor.org/rfc/rfc9728)) and [auth.md](https://workos.com/auth-md) | Not applicable | Nothing on the site needs authentication. | A protected API or an account feature. |
| DNS-AID ([draft](https://datatracker.ietf.org/doc/draft-mozleywilliams-dnsop-dnsaid/)), ARD ([specification](https://github.com/ards-project/ard-spec)) and Personal Agent Protocol ([draft](https://sierra.ai/personal-agent-protocol)) | Not published | DNS-AID records point to agent endpoints, and the site has none. ARD can list Agent Skills, but its publishing path changed recently and no registry in use was confirmed. The Personal Agent Protocol connects agents to customer accounts. | DNS-AID: a real agent endpoint. ARD: a stable specification and a registry that agents use; then generate `/.well-known/ard.json` from the same skill files. Personal Agent Protocol: customer accounts. |
| WebMCP ([draft](https://webmachinelearning.github.io/webmcp/)) | Not published | An early community draft whose browser API is still changing. A page script would change every page for little use today. | A stable browser API that agents call; then a read-only site-search tool backed by the existing client-side search. |
| Web Bot Auth ([IETF draft](https://datatracker.ietf.org/doc/draft-ietf-webbotauth-httpsig-protocol/)) | Not applicable | The key directory is for bots that sign their own requests. This project runs no such bot. | The project operates a crawler or agent that sends requests to other sites. |
| Commerce ([x402](https://www.x402.org/), [MPP](https://github.com/tempoxyz/mpp-specs), [UCP](https://ucp.dev/), [ACP](https://www.agenticcommerce.dev/), [AP2](https://ap2-protocol.org/)) | Not applicable | Nothing is for sale. | Paid content or a paid API. |

Unpublished well-known paths keep returning 404.
