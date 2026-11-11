# Presenter checklist

Sign into the guide and Copilot using an allowed Platform SSO identity. Keep the Market open in a second tab. Ask the operator to verify a denied identity separately; an allowed login alone does not establish the admission policy.

1. **Model:** ask a simple question and confirm an actual model response.
2. **Market:** ask: “Use northstar_search_products to list Produce products with their names and SKUs.” Inspect the tool result and compare it with the storefront. The baseline catalog has three Produce items.
3. **Memory:** choose a fresh marker, such as `NORTHSTAR-REHEARSAL-042`. Ask the memory tool to save its fictional color as sage. Start a blank new conversation under the same identity and ask the memory tool to retrieve it. Require a retrieval result; repetition inside one chat is not proof.
4. **Optional Hub:** after [connection setup](hub-oauth.md), request application names and states in your exact org and space. Ask for read-only operations and no changes. Record the tool name and successful result. Hub still follows your existing permissions; the prompt does not remove write permissions from your account.

The Hub scene demonstrates a user-scoped grant in native Credential Store. This release does not include separate protected-MCP, web-search, GitHub or headless-worker scenes.

Before sharing, record the source commit, platform/runtime version, date and which scenes actually passed. Keep environment identifiers and screenshots containing personal information in your private deployment records. The guide is instructional, not a live certification dashboard.

If an optional connection cannot authenticate, disable it in the current Copilot session while diagnosing it. Check the exact client callback and the user's inventory permissions. Do not put tokens in prompts or reuse another presenter's grant.
