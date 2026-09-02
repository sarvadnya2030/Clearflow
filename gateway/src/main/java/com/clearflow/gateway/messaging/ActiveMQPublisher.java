package com.clearflow.gateway.messaging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jms.JmsException;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

import com.clearflow.common.domain.PaymentInitiatedEvent;
import com.clearflow.common.messaging.MQQueues;
import com.clearflow.common.resilience.CircuitBreakerNames;

import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;

@Component
public class ActiveMQPublisher {

    private static final Logger log = LoggerFactory.getLogger(ActiveMQPublisher.class);
    private final JmsTemplate jmsTemplate;

    public ActiveMQPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @CircuitBreaker(name = CircuitBreakerNames.ACTIVEMQ, fallbackMethod = "publishFallback")
    public void publish(PaymentInitiatedEvent event, String tenantId) {
        try {
            jmsTemplate.send(MQQueues.PAYMENT_INITIATED, session -> {
                Message message = session.createObjectMessage(event);
                message.setJMSCorrelationID(event.paymentId());
                // JMS properties must be valid Java identifiers (no hyphens)
                message.setStringProperty("CorrelationId", event.correlationId());
                message.setStringProperty("TenantId", tenantId);
                message.setJMSDeliveryMode(DeliveryMode.PERSISTENT);
                return message;
            });
        } catch (JmsException ex) {
            log.error("ActiveMQ publish failed for paymentId={}", event.paymentId(), ex);
            jmsTemplate.convertAndSend(MQQueues.PAYMENT_DLQ, event);
        }
    }

    @SuppressWarnings("unused")
    void publishFallback(PaymentInitiatedEvent event, String tenantId, Exception ex) {
        log.warn("ActiveMQ circuit open/fallback for paymentId={} tenantId={} reason={}",
                event.paymentId(), tenantId, ex.getMessage());
        try {
            jmsTemplate.convertAndSend(MQQueues.PAYMENT_DLQ, event);
        } catch (JmsException ignored) {
            log.error("DLQ publish failed for paymentId={}", event.paymentId());
        }
    }
}
