package com.tanzu.demo.northstar.catalog;

import java.util.Comparator;
import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final ProductRepository products;

    public CatalogService(ProductRepository products) {
        this.products = products;
    }

    public List<Product> search(String query, String category) {
        var normalizedQuery = query == null ? "" : query.trim().toLowerCase();
        var normalizedCategory = category == null ? "all" : category.trim().toLowerCase();
        return products.findAll().stream()
                .filter(product -> normalizedCategory.equals("all")
                        || product.getCategory().equalsIgnoreCase(normalizedCategory))
                .filter(product -> normalizedQuery.isBlank()
                        || searchable(product).contains(normalizedQuery))
                .sorted(Comparator.comparing(Product::isFeatured).reversed()
                        .thenComparing(Comparator.comparingInt(Product::getMerchandisingScore).reversed())
                        .thenComparing(Product::getName))
                .toList();
    }

    public Product bySku(String sku) {
        return products.findById(sku)
                .orElseThrow(() -> new IllegalArgumentException("Unknown product SKU: " + sku));
    }

    public Product bySlug(String slug) {
        return products.findBySlug(slug)
                .orElseThrow(() -> new IllegalArgumentException("Unknown product: " + slug));
    }

    private String searchable(Product product) {
        return String.join(" ", product.getName(), product.getMaker(), product.getCategory(),
                product.getSummary(), String.join(" ", product.getTags())).toLowerCase();
    }
}
