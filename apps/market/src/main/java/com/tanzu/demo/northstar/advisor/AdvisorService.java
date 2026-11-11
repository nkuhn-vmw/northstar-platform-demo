package com.tanzu.demo.northstar.advisor;

import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;

import org.springframework.stereotype.Service;

import com.tanzu.demo.northstar.catalog.CatalogService;
import com.tanzu.demo.northstar.catalog.Product;

@Service
public class AdvisorService {

    private final CatalogService catalog;

    public AdvisorService(CatalogService catalog) {
        this.catalog = catalog;
    }

    public Recommendation recommend(AdvisorRequest request) {
        var workload = request.workload() == null ? "weeknight" : request.workload();
        var budget = request.budget() == null ? new BigDecimal("75") : request.budget();
        var all = catalog.search("", "all");
        var candidates = all.stream()
                .filter(product -> product.isFeatured())
                .filter(product -> product.getPrice().compareTo(budget) <= 0)
                .filter(product -> suited(product, workload))
                .limit(3)
                .toList();
        var overBudget = candidates.isEmpty();
        if (candidates.isEmpty()) {
            candidates = all.stream()
                    .filter(product -> suited(product, workload))
                    .sorted(Comparator.comparing(Product::getPrice))
                    .limit(3).toList();
        }
        if (candidates.isEmpty()) {
            candidates = all.stream().sorted(Comparator.comparing(Product::getPrice))
                    .limit(3).toList();
        }
        var lead = candidates.getFirst();
        var rationale = switch (workload) {
            case "family" -> "Prioritizing complete family meals, broad preferences, value, and dependable fulfillment.";
            case "fresh" -> "Prioritizing peak-season produce, short supply chains, and cold-chain availability.";
            case "prepared" -> "Prioritizing quick preparation, nutrition, and ready-to-eat inventory near you.";
            default -> "Prioritizing a balanced weeknight basket with fresh ingredients and a predictable budget.";
        };
        var explanation = overBudget
                ? rationale + " No exact match fits the budget; the closest qualifying option is "
                        + lead.getPrice().subtract(budget) + " over the current ceiling."
                : rationale;
        return new Recommendation("rules-v1", lead.getSku(), lead.getName(), explanation,
                candidates, List.of("Current catalog and inventory", "Declared workload",
                        "Budget ceiling", "Fulfillment and preference rules"),
                "Bind Tanzu AI Services and MCP Gateway to evolve this deterministic planner into a governed, grounded shopping assistant.");
    }

    private boolean suited(Product product, String workload) {
        return switch (workload) {
            case "family" -> product.getCategory().equals("prepared")
                    || product.getName().toLowerCase().contains("family");
            case "fresh" -> product.getCategory().equals("produce");
            case "prepared" -> product.getCategory().equals("prepared")
                    || product.getCategory().equals("bakery");
            default -> product.isFeatured();
        };
    }

    public record AdvisorRequest(String workload, BigDecimal budget, String priority) {
    }

    public record Recommendation(String engine, String primarySku, String title,
            String explanation, List<Product> alternatives, List<String> evidence,
            String platformUpgrade) {
    }
}
