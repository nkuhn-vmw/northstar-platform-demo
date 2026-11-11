package com.tanzu.demo.northstar.mcp;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import com.tanzu.demo.northstar.advisor.AdvisorService;
import com.tanzu.demo.northstar.advisor.AdvisorService.AdvisorRequest;
import com.tanzu.demo.northstar.catalog.CatalogService;

/**
 * A stateless Streamable HTTP MCP adapter for the read-only Northstar domain.
 *
 * <p>The endpoint deliberately exposes no cart, inventory mutation, or order placement tools.
 * It is designed to sit behind Tanzu MCP Gateway while preserving the storefront REST API.
 */
@RestController
public class NorthstarMcpController {

    private static final String PROTOCOL_VERSION = "2025-03-26";

    private final CatalogService catalog;
    private final AdvisorService advisor;
    private final ObjectMapper json;

    public NorthstarMcpController(CatalogService catalog, AdvisorService advisor,
            ObjectMapper json) {
        this.catalog = catalog;
        this.advisor = advisor;
        this.json = json;
    }

    @PostMapping(path = "/mcp", consumes = "application/json", produces = "application/json")
    ResponseEntity<?> handle(@RequestBody JsonNode request) {
        var method = request.path("method").asText();
        if (!request.has("id")) {
            return ResponseEntity.accepted().build();
        }

        var id = request.get("id");
        return switch (method) {
            case "initialize" -> ResponseEntity.ok(success(id, Map.of(
                    "protocolVersion", PROTOCOL_VERSION,
                    "capabilities", Map.of("tools", Map.of("listChanged", false)),
                    "serverInfo", Map.of("name", "northstar-market", "version", "1.0.0"))));
            case "ping" -> ResponseEntity.ok(success(id, Map.of()));
            case "tools/list" -> ResponseEntity.ok(success(id, Map.of("tools", tools())));
            case "tools/call" -> ResponseEntity.ok(callTool(id, request.path("params")));
            default -> ResponseEntity.ok(error(id, -32601, "Method not found: " + method));
        };
    }

    private Map<String, Object> callTool(JsonNode id, JsonNode params) {
        var name = params.path("name").asText();
        var arguments = params.path("arguments");
        try {
            Object result = switch (name) {
                case "northstar_search_products" -> Map.of(
                        "items", catalog.search(text(arguments, "query", ""),
                                text(arguments, "category", "all")));
                case "northstar_get_product" -> catalog.bySlug(requiredText(arguments, "slug"));
                case "northstar_recommend" -> advisor.recommend(new AdvisorRequest(
                        text(arguments, "workload", "weeknight"),
                        decimal(arguments, "budget", new BigDecimal("75")),
                        text(arguments, "priority", "balanced")));
                default -> throw new IllegalArgumentException("Unknown tool: " + name);
            };
            return success(id, Map.of(
                    "content", List.of(Map.of("type", "text", "text", encode(result))),
                    "isError", false));
        } catch (IllegalArgumentException | IllegalStateException error) {
            return success(id, Map.of(
                    "content", List.of(Map.of("type", "text", "text", error.getMessage())),
                    "isError", true));
        }
    }

    private List<Map<String, Object>> tools() {
        return List.of(
                tool("northstar_search_products",
                        "Search the live Northstar Market catalog by free text and category. "
                                + "Returns current prices and inventory.",
                        schema(Map.of(
                                "query", property("string", "Product, maker, tag, or use case"),
                                "category", property("string",
                                        "Category such as produce, prepared, bakery, or all")),
                                List.of())),
                tool("northstar_get_product",
                        "Look up one Northstar Market product by its URL slug.",
                        schema(Map.of(
                                "slug", property("string", "Exact product slug")),
                                List.of("slug"))),
                tool("northstar_recommend",
                        "Build a grounded shopping recommendation from the current catalog, "
                                + "inventory, workload, and budget.",
                        schema(Map.of(
                                "workload", property("string",
                                        "Shopping intent: weeknight, family, fresh, or prepared"),
                                "budget", property("number", "Maximum budget in US dollars"),
                                "priority", property("string", "Optional shopping priority")),
                                List.of())));
    }

    private Map<String, Object> tool(String name, String description,
            Map<String, Object> inputSchema) {
        return Map.of("name", name, "description", description, "inputSchema", inputSchema);
    }

    private Map<String, Object> schema(Map<String, Object> properties, List<String> required) {
        var schema = new LinkedHashMap<String, Object>();
        schema.put("type", "object");
        schema.put("properties", properties);
        schema.put("required", required);
        schema.put("additionalProperties", false);
        return schema;
    }

    private Map<String, Object> property(String type, String description) {
        return Map.of("type", type, "description", description);
    }

    private String text(JsonNode arguments, String name, String fallback) {
        var value = arguments.path(name).asText("").trim();
        return value.isEmpty() ? fallback : value;
    }

    private String requiredText(JsonNode arguments, String name) {
        var value = text(arguments, name, "");
        if (value.isEmpty()) {
            throw new IllegalArgumentException(name + " is required");
        }
        return value;
    }

    private BigDecimal decimal(JsonNode arguments, String name, BigDecimal fallback) {
        var value = arguments.get(name);
        return value == null || value.isNull() ? fallback : value.decimalValue();
    }

    private String encode(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JacksonException error) {
            throw new IllegalStateException("Unable to encode tool result", error);
        }
    }

    private Map<String, Object> success(JsonNode id, Object result) {
        return Map.of("jsonrpc", "2.0", "id", id, "result", result);
    }

    private Map<String, Object> error(JsonNode id, int code, String message) {
        return Map.of("jsonrpc", "2.0", "id", id,
                "error", Map.of("code", code, "message", message));
    }
}
