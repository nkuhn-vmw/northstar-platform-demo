package com.tanzu.demo.northstar.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
@ConditionalOnProperty(name = "northstar.events.publisher", havingValue = "log", matchIfMissing = true)
public class LoggingOrderEventHandler {

    private static final Logger log = LoggerFactory.getLogger(LoggingOrderEventHandler.class);

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void publish(OrderPlacedEvent event) {
        log.info("Northstar order placed: orderId={}, lineCount={}, total={}",
                event.orderId(), event.lineCount(), event.total());
    }
}
