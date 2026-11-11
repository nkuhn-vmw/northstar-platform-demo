package com.tanzu.demo.northstar.order;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private String id;
    @Column(nullable = false)
    private String email;
    @Column(nullable = false)
    private String status;
    @Column(nullable = false)
    private Instant createdAt;
    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal total;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true,
            fetch = FetchType.EAGER)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String email, BigDecimal total) {
        this.id = "NS-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        this.email = email;
        this.status = "RESERVED";
        this.createdAt = Instant.now();
        this.total = total;
    }

    public void addLine(String sku, String name, BigDecimal unitPrice, int quantity) {
        lines.add(new OrderLine(this, sku, name, unitPrice, quantity));
    }

    public String getId() { return id; }
    public String getEmail() { return email; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public BigDecimal getTotal() { return total; }
    public List<OrderLine> getLines() { return List.copyOf(lines); }
}
