package com.tanzu.demo.northstar;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.security.autoconfigure.UserDetailsServiceAutoConfiguration;

@SpringBootApplication(exclude = UserDetailsServiceAutoConfiguration.class)
public class NorthstarMarketApplication {

    public static void main(String[] args) {
        SpringApplication.run(NorthstarMarketApplication.class, args);
    }
}
