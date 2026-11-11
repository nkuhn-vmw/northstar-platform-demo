package com.tanzu.demo.northstar.cart;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.Collections;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

import com.tanzu.demo.northstar.catalog.CatalogService;

@Service
@ConditionalOnProperty(name = "northstar.cart.store", havingValue = "redis")
public class RedisCartStore implements CartStore {

    private static final DefaultRedisScript<Long> ADD_ITEM = new DefaultRedisScript<>("""
            local quantity = redis.call('HINCRBY', KEYS[1], ARGV[1], ARGV[2])
            if quantity > tonumber(ARGV[3]) then
              local restored = redis.call('HINCRBY', KEYS[1], ARGV[1], -tonumber(ARGV[2]))
              if restored == 0 then redis.call('HDEL', KEYS[1], ARGV[1]) end
              return -1
            end
            redis.call('PEXPIRE', KEYS[1], ARGV[4])
            return quantity
            """, Long.class);

    private final CatalogService catalog;
    private final StringRedisTemplate redis;
    private final Duration ttl;

    public RedisCartStore(CatalogService catalog, StringRedisTemplate redis,
            @Value("${northstar.cart.ttl:7d}") Duration ttl) {
        this.catalog = catalog;
        this.redis = redis;
        this.ttl = ttl;
    }

    @Override
    public CartSnapshot get(String cartId) {
        var id = normalize(cartId);
        var quantities = redis.<String, String>opsForHash().entries(key(id));
        var lines = quantities.entrySet().stream().map(entry -> {
            var product = catalog.bySku(entry.getKey());
            return new CartLine(product.getSku(), product.getName(), product.getPrice(),
                    Integer.parseInt(entry.getValue()), product.getImage(), product.getAccent());
        }).toList();
        var count = lines.stream().mapToInt(CartLine::quantity).sum();
        var subtotal = lines.stream().map(CartLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        return new CartSnapshot(id, lines, count, subtotal);
    }

    @Override
    public CartSnapshot add(String cartId, String sku, int quantity) {
        if (quantity < 1 || quantity > 10) {
            throw new IllegalArgumentException("Quantity must be between 1 and 10");
        }
        var id = normalize(cartId);
        var product = catalog.bySku(sku);
        var next = redis.execute(ADD_ITEM, Collections.singletonList(key(id)), sku,
                String.valueOf(quantity), String.valueOf(product.getStock()),
                String.valueOf(ttl.toMillis()));
        if (next == null) {
            throw new IllegalStateException("The basket cache did not acknowledge the update");
        }
        if (next < 0) {
            throw new IllegalStateException("Only " + product.getStock() + " units are available");
        }
        return get(id);
    }

    @Override
    public CartSnapshot remove(String cartId, String sku) {
        var id = normalize(cartId);
        redis.opsForHash().delete(key(id), sku);
        return get(id);
    }

    @Override
    public void clear(String cartId) {
        redis.delete(key(normalize(cartId)));
    }

    private String key(String cartId) {
        return "northstar:cart:" + cartId;
    }

    private String normalize(String cartId) {
        if (cartId == null || !cartId.matches("[a-zA-Z0-9-]{8,64}")) {
            throw new IllegalArgumentException("Invalid cart identifier");
        }
        return cartId;
    }
}
