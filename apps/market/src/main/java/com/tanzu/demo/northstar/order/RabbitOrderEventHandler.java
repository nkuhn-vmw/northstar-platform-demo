package com.tanzu.demo.northstar.order;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
@ConditionalOnProperty(name = "northstar.events.publisher", havingValue = "rabbit")
public class RabbitOrderEventHandler {

    private final RabbitTemplate rabbit;
    private final String exchange;

    public RabbitOrderEventHandler(RabbitTemplate rabbit,
            @Value("${northstar.events.exchange:northstar.events}") String exchange) {
        this.rabbit = rabbit;
        this.exchange = exchange;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void publish(OrderPlacedEvent event) {
        rabbit.convertAndSend(exchange, "orders.placed", event, message -> {
            message.getMessageProperties().setContentType("application/json");
            message.getMessageProperties().setHeader("eventType", "northstar.order.placed.v1");
            return message;
        });
    }
}
