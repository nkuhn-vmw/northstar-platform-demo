package com.tanzu.demo.northstar.web;

import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;

import javax.sql.DataSource;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/platform")
public class PlatformApiController {

    private final Instant started = Instant.now();
    private final Environment environment;
    private final DataSource dataSource;

    public PlatformApiController(Environment environment, DataSource dataSource) {
        this.environment = environment;
        this.dataSource = dataSource;
    }

    @GetMapping
    Object platform(HttpServletRequest request) {
        var services = serviceLabels();
        var database = databaseProduct();
        var response = new LinkedHashMap<String, Object>();
        response.put("application", env("VCAP_APPLICATION_NAME", "northstar-market"));
        response.put("instance", "#" + env("CF_INSTANCE_INDEX", "0"));
        response.put("runtime", "Java " + Runtime.version().feature() + " · Spring Boot");
        response.put("route", request.getServerName());
        response.put("deploymentMode", env("NORTHSTAR_DEPLOYMENT_MODE", "local"));
        response.put("database", database);
        response.put("boundServices", services);
        response.put("capabilities", capabilities(database, services));
        response.put("security", List.of("CSRF token", "CSP", "HSTS", "frame denial"));
        response.put("started", started.toString());
        response.put("profiles", List.of(environment.getActiveProfiles()));
        return response;
    }

    private List<ServiceCapability> capabilities(String database, List<String> bindings) {
        var cartStore = environment.getProperty("northstar.cart.store", "memory");
        var eventPublisher = environment.getProperty("northstar.events.publisher", "log");
        var advisorEngine = environment.getProperty("northstar.advisor.engine", "rules");
        return List.of(
                capability("postgresql", "PostgreSQL", "catalog + orders", database,
                        database.toLowerCase(Locale.ROOT).contains("postgres"),
                        bindings.contains("PostgreSQL")),
                capability("valkey", "Valkey", "shared basket + cache", cartStore,
                        cartStore.equalsIgnoreCase("redis"), bindings.contains("Valkey")),
                capability("rabbitmq", "RabbitMQ", "order events", eventPublisher,
                        eventPublisher.equalsIgnoreCase("rabbit"), bindings.contains("RabbitMQ")),
                capability("ai-models", "AI Models", "grounded shopping assistant", advisorEngine,
                        advisorEngine.equalsIgnoreCase("ai"), bindings.contains("AI Models")));
    }

    private ServiceCapability capability(String id, String name, String role, String implementation,
            boolean active, boolean bound) {
        var status = active ? "active" : bound ? "bound" : "local";
        return new ServiceCapability(id, name, role, implementation, status);
    }

    private String databaseProduct() {
        try (var connection = dataSource.getConnection()) {
            var product = connection.getMetaData().getDatabaseProductName();
            return product.toLowerCase(Locale.ROOT).contains("postgres")
                    ? "Tanzu for Postgres" : "Embedded " + product;
        } catch (SQLException error) {
            return "Database unavailable";
        }
    }

    private List<String> serviceLabels() {
        var vcap = System.getenv().getOrDefault("VCAP_SERVICES", "").toLowerCase(Locale.ROOT);
        var labels = new ArrayList<String>();
        addWhenPresent(labels, vcap, "PostgreSQL", "postgres");
        addWhenPresent(labels, vcap, "Valkey", "redis", "valkey");
        addWhenPresent(labels, vcap, "RabbitMQ", "rabbitmq");
        addWhenPresent(labels, vcap, "AI Models", "ai-models", "genai");
        addWhenPresent(labels, vcap, "CredHub", "credhub");
        addWhenPresent(labels, vcap, "Object Storage", "seaweedfs", "object-storage");
        return labels;
    }

    private void addWhenPresent(List<String> labels, String source, String label,
            String... candidates) {
        for (var candidate : candidates) {
            if (source.contains(candidate)) {
                labels.add(label);
                return;
            }
        }
    }

    private String env(String name, String fallback) {
        return System.getenv().getOrDefault(name, fallback);
    }

    record ServiceCapability(String id, String name, String role, String implementation,
            String status) {
    }
}
