package com.tanzu.demo.northstar.order;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderPlacedEvent(String orderId, String customerEmail, BigDecimal total,
        int lineCount, Instant occurredAt) {

    static OrderPlacedEvent from(PurchaseOrder order) {
        return new OrderPlacedEvent(order.getId(), order.getEmail(), order.getTotal(),
                order.getLines().size(), Instant.now());
    }
}
