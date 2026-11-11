package com.tanzu.demo.northstar.web;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import com.tanzu.demo.northstar.advisor.AdvisorService;
import com.tanzu.demo.northstar.advisor.AdvisorService.AdvisorRequest;
import com.tanzu.demo.northstar.cart.CartStore;
import com.tanzu.demo.northstar.catalog.CatalogService;
import com.tanzu.demo.northstar.order.OrderService;

@RestController
@RequestMapping("/api")
public class CommerceApiController {

    private final CatalogService catalog;
    private final CartStore carts;
    private final AdvisorService advisor;
    private final OrderService orders;

    public CommerceApiController(CatalogService catalog, CartStore carts,
            AdvisorService advisor, OrderService orders) {
        this.catalog = catalog;
        this.carts = carts;
        this.advisor = advisor;
        this.orders = orders;
    }

    @GetMapping("/catalog/products")
    Object products(@RequestParam(defaultValue = "") String query,
            @RequestParam(defaultValue = "all") String category) {
        return Map.of("items", catalog.search(query, category), "query", query,
                "category", category);
    }

    @GetMapping("/catalog/products/{slug}")
    Object product(@PathVariable String slug) {
        return catalog.bySlug(slug);
    }

    @GetMapping("/cart/{cartId}")
    Object cart(@PathVariable String cartId) {
        return carts.get(cartId);
    }

    @PostMapping("/cart/{cartId}/items")
    Object addToCart(@PathVariable String cartId, @Valid @RequestBody CartItemRequest body) {
        return carts.add(cartId, body.sku(), body.quantity());
    }

    @DeleteMapping("/cart/{cartId}/items/{sku}")
    Object removeFromCart(@PathVariable String cartId, @PathVariable String sku) {
        return carts.remove(cartId, sku);
    }

    @PostMapping("/advisor/recommend")
    Object recommend(@RequestBody AdvisorRequest request) {
        return advisor.recommend(request);
    }

    @PostMapping("/orders")
    @ResponseStatus(HttpStatus.CREATED)
    Object order(@Valid @RequestBody OrderRequest request) {
        return orders.place(request.cartId(), request.email());
    }

    @GetMapping("/orders/{id}")
    Object order(@PathVariable String id) {
        return orders.get(id);
    }

    @GetMapping("/security/csrf")
    Object csrf(CsrfToken token) {
        return Map.of("headerName", token.getHeaderName(), "token", token.getToken());
    }

    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Object badRequest(RuntimeException error) {
        return Map.of("error", error.getMessage());
    }

    public record CartItemRequest(@NotBlank String sku, @Min(1) @Max(10) int quantity) {
    }

    public record OrderRequest(@NotBlank String cartId, @Email @NotBlank String email) {
    }
}
