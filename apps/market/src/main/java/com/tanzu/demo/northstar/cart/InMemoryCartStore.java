package com.tanzu.demo.northstar.cart;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

import com.tanzu.demo.northstar.catalog.CatalogService;

@Service
@ConditionalOnProperty(name = "northstar.cart.store", havingValue = "memory", matchIfMissing = true)
public class InMemoryCartStore implements CartStore {

    private final CatalogService catalog;
    private final Map<String, Map<String, Integer>> carts = new ConcurrentHashMap<>();

    public InMemoryCartStore(CatalogService catalog) {
        this.catalog = catalog;
    }

    @Override
    public CartSnapshot get(String cartId) {
        var quantities = carts.getOrDefault(normalize(cartId), Map.of());
        var lines = quantities.entrySet().stream().map(entry -> {
            var product = catalog.bySku(entry.getKey());
            return new CartLine(product.getSku(), product.getName(), product.getPrice(),
                    entry.getValue(), product.getImage(), product.getAccent());
        }).toList();
        var count = lines.stream().mapToInt(CartLine::quantity).sum();
        var subtotal = lines.stream().map(CartLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        return new CartSnapshot(normalize(cartId), lines, count, subtotal);
    }

    @Override
    public CartSnapshot add(String cartId, String sku, int quantity) {
        if (quantity < 1 || quantity > 10) {
            throw new IllegalArgumentException("Quantity must be between 1 and 10");
        }
        var product = catalog.bySku(sku);
        var cart = carts.computeIfAbsent(normalize(cartId), ignored -> new LinkedHashMap<>());
        synchronized (cart) {
            var next = cart.getOrDefault(sku, 0) + quantity;
            if (next > product.getStock()) {
                throw new IllegalStateException("Only " + product.getStock() + " units are available");
            }
            cart.put(sku, next);
        }
        return get(cartId);
    }

    @Override
    public CartSnapshot remove(String cartId, String sku) {
        var cart = carts.get(normalize(cartId));
        if (cart != null) {
            cart.remove(sku);
        }
        return get(cartId);
    }

    @Override
    public void clear(String cartId) {
        carts.remove(normalize(cartId));
    }

    private String normalize(String cartId) {
        if (cartId == null || !cartId.matches("[a-zA-Z0-9-]{8,64}")) {
            throw new IllegalArgumentException("Invalid cart identifier");
        }
        return cartId;
    }
}
