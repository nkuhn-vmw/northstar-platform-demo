package com.tanzu.demo.northstar.cart;

import java.math.BigDecimal;
import java.util.List;

public interface CartStore {

    CartSnapshot get(String cartId);

    CartSnapshot add(String cartId, String sku, int quantity);

    CartSnapshot remove(String cartId, String sku);

    void clear(String cartId);

    record CartLine(String sku, String name, BigDecimal unitPrice, int quantity,
            String image, String accent) {
        public BigDecimal lineTotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record CartSnapshot(String id, List<CartLine> lines, int itemCount, BigDecimal subtotal) {
    }
}
