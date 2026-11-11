package com.tanzu.demo.northstar.order;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.context.ApplicationEventPublisher;

import com.tanzu.demo.northstar.cart.CartStore;
import com.tanzu.demo.northstar.catalog.ProductRepository;

@Service
public class OrderService {

    private final CartStore carts;
    private final ProductRepository products;
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(CartStore carts, ProductRepository products, OrderRepository orders,
            ApplicationEventPublisher events) {
        this.carts = carts;
        this.products = products;
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public PurchaseOrder place(String cartId, String email) {
        if (email == null || !email.matches("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")) {
            throw new IllegalArgumentException("A valid email address is required");
        }
        var cart = carts.get(cartId);
        if (cart.lines().isEmpty()) {
            throw new IllegalStateException("The cart is empty");
        }
        var order = new PurchaseOrder(email, cart.subtotal());
        cart.lines().forEach(line -> {
            var product = products.findById(line.sku()).orElseThrow();
            product.reserve(line.quantity());
            order.addLine(line.sku(), line.name(), line.unitPrice(), line.quantity());
        });
        var saved = orders.save(order);
        carts.clear(cartId);
        events.publishEvent(OrderPlacedEvent.from(saved));
        return saved;
    }

    public PurchaseOrder get(String id) {
        return orders.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Unknown order: " + id));
    }
}
