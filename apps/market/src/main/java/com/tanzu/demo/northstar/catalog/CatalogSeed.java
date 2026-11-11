package com.tanzu.demo.northstar.catalog;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class CatalogSeed implements CommandLineRunner {

    private final ProductRepository products;

    public CatalogSeed(ProductRepository products) {
        this.products = products;
    }

    @Override
    public void run(String... args) {
        if (products.count() > 0) {
            return;
        }
        products.saveAll(List.of(
                product("NS-PRO-101", "harvest-market-box", "Harvest Market Box",
                        "Northstar Farms", "produce", "34.00", "39.00", 84, 99,
                        true, "Picked this morning", "green",
                        "/assets/products/fresh-produce.png",
                        "A rotating collection of peak-season produce from regional farms.",
                        "Chef-selected greens, tomatoes, citrus, berries, herbs, and avocados packed for a full week of fresh meals.",
                        Set.of("local", "seasonal", "organic", "fresh"),
                        Map.of("Serves", "4–6", "Source", "Regional farms",
                                "Fulfillment", "Chilled", "Substitutions", "Preference aware")),
                product("NS-BAK-210", "bakery-weekend-set", "Weekend Bakery Set",
                        "Northstar Bakehouse", "bakery", "21.50", "25.00", 46, 96,
                        true, "Baked today", "gold",
                        "/assets/products/bakery-meals.png",
                        "Sourdough, butter croissants, and seeded rolls from our in-store bakery.",
                        "A family bakery bundle prepared overnight and released in timed inventory batches for pickup or delivery.",
                        Set.of("bakery", "sourdough", "breakfast", "fresh"),
                        Map.of("Items", "8", "Baked", "Today",
                                "Allergens", "Wheat · Dairy", "Best by", "3 days")),
                product("NS-MEAL-301", "sesame-ginger-meal-kit", "Sesame Ginger Meal Kit",
                        "Northstar Kitchen", "prepared", "28.00", "32.00", 62, 98,
                        true, "20-minute dinner", "coral",
                        "/assets/products/bakery-meals.png",
                        "A ready-to-cook dinner with crisp vegetables and a house sesame sauce.",
                        "Pre-portioned ingredients, flexible protein choices, and step-by-step preparation for a dependable weeknight meal.",
                        Set.of("meal kit", "dinner", "quick", "family"),
                        Map.of("Serves", "4", "Prep time", "20 minutes",
                                "Diet", "Vegetarian option", "Pickup zone", "Chilled")),
                product("NS-PRO-115", "citrus-berry-crate", "Citrus & Berry Crate",
                        "Northstar Farms", "produce", "18.75", "22.00", 105, 94,
                        true, "Peak season", "berry",
                        "/assets/products/fresh-produce.png",
                        "Sweet citrus, strawberries, blueberries, and blackberries.",
                        "A hand-checked fruit assortment with ripeness scoring and cold-chain fulfillment from store to door.",
                        Set.of("fruit", "berries", "breakfast", "seasonal"),
                        Map.of("Weight", "4.5 lb", "Source", "Domestic",
                                "Storage", "Refrigerated", "Quality check", "At fulfillment")),
                product("NS-PAN-410", "everyday-pantry-set", "Everyday Pantry Set",
                        "Northstar Select", "pantry", "42.00", "48.00", 138, 91,
                        false, "Member value", "navy",
                        "/assets/products/northstar-hero.png",
                        "The grains, beans, pasta, oils, and spices behind a week of meals.",
                        "A curated pantry reset with traceable sourcing, clear allergen data, and member pricing.",
                        Set.of("pantry", "staples", "family", "value"),
                        Map.of("Items", "14", "Shelf life", "6+ months",
                                "Diet", "Plant-forward", "Packaging", "Recyclable")),
                product("NS-DAI-520", "farmstead-dairy-set", "Farmstead Dairy Set",
                        "Meadow Cooperative", "dairy", "17.25", "20.00", 73, 90,
                        false, "Co-op sourced", "sky",
                        "/assets/products/northstar-hero.png",
                        "Milk, cultured butter, eggs, and two seasonal cheeses.",
                        "A refrigerated essentials set sourced through a regional producer cooperative with end-to-end lot traceability.",
                        Set.of("dairy", "eggs", "local", "refrigerated"),
                        Map.of("Items", "5", "Source", "Regional cooperative",
                                "Delivery", "Cold chain", "Traceability", "Lot level")),
                product("NS-MEA-610", "family-grill-box", "Family Grill Box",
                        "Northstar Butcher", "meat", "56.00", "64.00", 39, 89,
                        false, "Butcher selected", "red",
                        "/assets/products/bakery-meals.png",
                        "Responsibly sourced proteins portioned for four complete meals.",
                        "Chicken, salmon, and grass-fed beef prepared in-store with safe-handling guidance and insulated fulfillment.",
                        Set.of("protein", "grill", "family", "responsible"),
                        Map.of("Serves", "8–10", "Prepared", "In store",
                                "Delivery", "Insulated", "Substitutions", "Approval required")),
                product("NS-MEAL-325", "grain-bowl-four-pack", "Harvest Grain Bowls",
                        "Northstar Kitchen", "prepared", "31.00", "36.00", 57, 93,
                        false, "Lunch solved", "green",
                        "/assets/products/bakery-meals.png",
                        "Four colorful grain bowls with seasonal vegetables and dressings.",
                        "Ready-to-eat lunches prepared daily with ingredient-level nutrition and allergen information.",
                        Set.of("prepared", "lunch", "vegetarian", "quick"),
                        Map.of("Quantity", "4 bowls", "Prepared", "Today",
                                "Diet", "Vegetarian", "Pickup zone", "Chilled")),
                product("NS-PRO-128", "salad-garden-set", "Salad Garden Set",
                        "City Greenhouse", "produce", "14.50", "17.00", 91, 92,
                        false, "Hydroponic local", "green",
                        "/assets/products/fresh-produce.png",
                        "Living lettuces, herbs, cucumber, and tomatoes grown nearby.",
                        "A crisp salad bundle harvested from a controlled-environment greenhouse within fifty miles of the store.",
                        Set.of("salad", "local", "greens", "hydroponic"),
                        Map.of("Harvest", "Within 24 hours", "Miles", "Under 50",
                                "Growing", "Hydroponic", "Packaging", "Compostable")),
                product("NS-BAK-230", "artisan-bread-flight", "Artisan Bread Flight",
                        "Northstar Bakehouse", "bakery", "16.00", "19.00", 34, 88,
                        false, "Small batch", "gold",
                        "/assets/products/bakery-meals.png",
                        "Three small loaves showcasing our bakery's daily fermentation.",
                        "Country sourdough, seeded rye, and olive bread packaged at peak freshness.",
                        Set.of("bread", "artisan", "sourdough", "bakery"),
                        Map.of("Loaves", "3", "Fermentation", "24–48 hours",
                                "Baked", "Today", "Freezing", "Recommended")),
                product("NS-HOM-710", "low-waste-home-refill", "Low-Waste Home Refill",
                        "Northstar Home", "household", "29.00", "34.00", 66, 86,
                        false, "Less packaging", "teal",
                        "/assets/products/northstar-hero.png",
                        "Concentrated home essentials in returnable and recyclable packaging.",
                        "Kitchen and laundry refills designed for scheduled replenishment through the Northstar loyalty program.",
                        Set.of("household", "refill", "sustainable", "subscription"),
                        Map.of("Items", "6", "Packaging", "Returnable",
                                "Delivery", "Ambient", "Reorder", "Smart replenishment")),
                product("NS-PAN-440", "global-flavors-set", "Global Flavors Set",
                        "Northstar Select", "pantry", "38.00", "44.00", 49, 87,
                        false, "Chef curated", "plum",
                        "/assets/products/northstar-hero.png",
                        "Sauces, spices, grains, and condiments for globally inspired meals.",
                        "A pantry discovery set supported by recipe recommendations and ingredient substitution guidance.",
                        Set.of("pantry", "spices", "global", "recipes"),
                        Map.of("Items", "12", "Regions", "5",
                                "Recipe cards", "Digital", "Allergens", "Clearly marked"))
        ));
    }

    private Product product(String sku, String slug, String name, String maker,
            String category, String price, String compareAt, int stock,
            int merchandisingScore, boolean featured, String badge,
            String accent, String image, String summary, String description,
            Set<String> tags, Map<String, String> specs) {
        return new Product(sku, slug, name, maker, category, new BigDecimal(price),
                new BigDecimal(compareAt), stock, merchandisingScore,
                featured, badge, accent, image, summary, description, tags, specs);
    }
}
