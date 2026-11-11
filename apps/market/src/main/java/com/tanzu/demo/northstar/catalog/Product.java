package com.tanzu.demo.northstar.catalog;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapKeyColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    private String sku;
    @Column(nullable = false, unique = true)
    private String slug;
    @Column(nullable = false)
    private String name;
    private String maker;
    @Column(nullable = false)
    private String category;
    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;
    @Column(precision = 12, scale = 2)
    private BigDecimal compareAtPrice;
    private int stock;
    private int merchandisingScore;
    private boolean featured;
    private String badge;
    private String accent;
    private String image;
    @Column(length = 500)
    private String summary;
    @Column(length = 2000)
    private String description;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "product_tags", joinColumns = @JoinColumn(name = "product_sku"))
    @Column(name = "tag")
    private Set<String> tags = new LinkedHashSet<>();

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "product_specs", joinColumns = @JoinColumn(name = "product_sku"))
    @MapKeyColumn(name = "spec_name")
    @Column(name = "spec_value")
    private Map<String, String> specs = new LinkedHashMap<>();

    protected Product() {
    }

    public Product(String sku, String slug, String name, String maker, String category,
            BigDecimal price, BigDecimal compareAtPrice, int stock, int merchandisingScore,
            boolean featured, String badge,
            String accent, String image, String summary, String description,
            Set<String> tags, Map<String, String> specs) {
        this.sku = sku;
        this.slug = slug;
        this.name = name;
        this.maker = maker;
        this.category = category;
        this.price = price;
        this.compareAtPrice = compareAtPrice;
        this.stock = stock;
        this.merchandisingScore = merchandisingScore;
        this.featured = featured;
        this.badge = badge;
        this.accent = accent;
        this.image = image;
        this.summary = summary;
        this.description = description;
        this.tags = new LinkedHashSet<>(tags);
        this.specs = new LinkedHashMap<>(specs);
    }

    public String getSku() { return sku; }
    public String getSlug() { return slug; }
    public String getName() { return name; }
    public String getMaker() { return maker; }
    public String getCategory() { return category; }
    public BigDecimal getPrice() { return price; }
    public BigDecimal getCompareAtPrice() { return compareAtPrice; }
    public int getStock() { return stock; }
    public int getMerchandisingScore() { return merchandisingScore; }
    public boolean isFeatured() { return featured; }
    public String getBadge() { return badge; }
    public String getAccent() { return accent; }
    public String getImage() { return image; }
    public String getSummary() { return summary; }
    public String getDescription() { return description; }
    public Set<String> getTags() { return Set.copyOf(tags); }
    public Map<String, String> getSpecs() { return Map.copyOf(specs); }

    public void reserve(int quantity) {
        if (quantity < 1 || stock < quantity) {
            throw new IllegalStateException("Insufficient inventory for " + sku);
        }
        stock -= quantity;
    }
}
