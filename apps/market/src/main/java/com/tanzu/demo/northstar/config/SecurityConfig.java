package com.tanzu.demo.northstar.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        var csrf = CookieCsrfTokenRepository.withHttpOnlyFalse();
        csrf.setCookiePath("/");
        return http
                .authorizeHttpRequests(requests -> requests.anyRequest().permitAll())
                .csrf(configurer -> configurer
                        .csrfTokenRepository(csrf)
                        .ignoringRequestMatchers("/mcp"))
                .headers(headers -> headers
                        .contentSecurityPolicy(policy -> policy.policyDirectives(
                                "default-src 'self'; img-src 'self' data:; "
                                        + "style-src 'self' 'unsafe-inline'; "
                                        + "script-src 'self'; connect-src 'self'; "
                                        + "font-src 'self'; object-src 'none'; "
                                        + "base-uri 'self'; frame-ancestors 'none'"))
                        .frameOptions(frame -> frame.deny())
                        .httpStrictTransportSecurity(Customizer.withDefaults())
                        .permissionsPolicyHeader(policy -> policy.policy(
                                "camera=(), microphone=(), geolocation=(), payment=()")))
                .build();
    }
}
