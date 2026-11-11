package com.tanzu.demo.northstar.order;

import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConditionalOnProperty(name = "northstar.events.publisher", havingValue = "rabbit")
public class RabbitEventConfiguration {

    @Bean
    Declarables northstarOrderExchange(
            @Value("${northstar.events.exchange:northstar.events}") String exchange) {
        return new Declarables(new TopicExchange(exchange, true, false));
    }

    @Bean
    MessageConverter northstarEventMessageConverter() {
        return new JacksonJsonMessageConverter();
    }
}
