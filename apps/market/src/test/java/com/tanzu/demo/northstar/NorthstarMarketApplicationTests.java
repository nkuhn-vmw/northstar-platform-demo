package com.tanzu.demo.northstar;

import static org.hamcrest.Matchers.greaterThan;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class NorthstarMarketApplicationTests {

    @Autowired
    private MockMvc http;

    @Test
    void catalogAndPlatformEvidenceAreAvailable() throws Exception {
        http.perform(get("/api/catalog/products"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()", greaterThan(10)))
                .andExpect(jsonPath("$.items[0].sku").isNotEmpty());

        http.perform(get("/api/platform"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.application").value("northstar-market"))
                .andExpect(jsonPath("$.runtime").value("Java 21 · Spring Boot"))
                .andExpect(jsonPath("$.capabilities.length()").value(4))
                .andExpect(jsonPath("$.capabilities[0].id").value("postgresql"))
                .andExpect(jsonPath("$.capabilities[1].implementation").value("memory"))
                .andExpect(jsonPath("$.capabilities[2].implementation").value("log"));
    }

    @Test
    void cartAndAdvisorRequireAndAcceptCsrf() throws Exception {
        http.perform(post("/api/cart/recording-cart/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sku\":\"NS-PRO-101\",\"quantity\":1}"))
                .andExpect(status().isForbidden());

        http.perform(post("/api/cart/recording-cart/items")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sku\":\"NS-PRO-101\",\"quantity\":1}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.itemCount").value(1));

        http.perform(post("/api/advisor/recommend")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"workload\":\"weeknight\",\"budget\":75}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.engine").value("rules-v1"))
                .andExpect(jsonPath("$.primarySku").isNotEmpty());
    }

    @Test
    void anOrderUsesTheNorthstarContract() throws Exception {
        http.perform(post("/api/cart/order-cart/items")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sku\":\"NS-MEAL-301\",\"quantity\":1}"))
                .andExpect(status().isOk());

        http.perform(post("/api/orders")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"cartId\":\"order-cart\",\"email\":\"shopper@example.com\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(org.hamcrest.Matchers.startsWith("NS-")))
                .andExpect(jsonPath("$.status").value("RESERVED"));
    }

    @Test
    void agentBuildPackCanDiscoverAndCallReadOnlyMcpToolsWithoutBrowserCsrf()
            throws Exception {
        http.perform(post("/mcp")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
                                  "protocolVersion":"2025-03-26","capabilities":{},
                                  "clientInfo":{"name":"test","version":"1"}}}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result.protocolVersion").value("2025-03-26"))
                .andExpect(jsonPath("$.result.serverInfo.name").value("northstar-market"));

        http.perform(post("/mcp")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result.tools.length()").value(3))
                .andExpect(jsonPath("$.result.tools[0].name")
                        .value("northstar_search_products"))
                .andExpect(jsonPath("$.result.tools[1].name").value("northstar_get_product"))
                .andExpect(jsonPath("$.result.tools[2].name").value("northstar_recommend"));

        http.perform(post("/mcp")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{
                                  "name":"northstar_search_products",
                                  "arguments":{"query":"produce","category":"all"}}}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result.isError").value(false))
                .andExpect(jsonPath("$.result.content[0].type").value("text"))
                .andExpect(jsonPath("$.result.content[0].text").isNotEmpty());
    }
}
