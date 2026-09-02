package com.clearflow.gateway.status;

import com.clearflow.common.messaging.KafkaTopics;
import com.clearflow.gateway.domain.PaymentStatus;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentStatusKafkaConsumer {

    private static final Logger log = LoggerFactory.getLogger(PaymentStatusKafkaConsumer.class);

    private final PaymentStatusService statusService;

    public PaymentStatusKafkaConsumer(PaymentStatusService statusService) {
        this.statusService = statusService;
    }

    @KafkaListener(topics = KafkaTopics.PAYMENT_INITIATED,
                   containerFactory = "statusKafkaListenerContainerFactory")
    public void onPaymentInitiated(ConsumerRecord<String, String> record) {
        log.debug("Status update: INITIATED for paymentId={}", record.key());
        statusService.updateStatus(record.key(), PaymentStatus.INITIATED,
                "gateway", "Payment accepted and queued").subscribe();
    }

    @KafkaListener(topics = KafkaTopics.PAYMENT_VALIDATED,
                   containerFactory = "statusKafkaListenerContainerFactory")
    public void onPaymentValidated(ConsumerRecord<String, String> record) {
        log.debug("Status update: VALIDATED for paymentId={}", record.key());
        statusService.updateStatus(record.key(), PaymentStatus.VALIDATED,
                "validation-enrichment", "IBAN/BIC validated, embargo checks passed").subscribe();
    }

    @KafkaListener(topics = KafkaTopics.PAYMENT_REJECTED,
                   containerFactory = "statusKafkaListenerContainerFactory")
    public void onPaymentRejected(ConsumerRecord<String, String> record) {
        log.debug("Status update: REJECTED for paymentId={}", record.key());
        statusService.updateStatus(record.key(), PaymentStatus.REJECTED,
                "validation-enrichment", "Payment rejected during validation").subscribe();
    }

    @KafkaListener(topics = KafkaTopics.PAYMENT_BLOCKED,
                   containerFactory = "statusKafkaListenerContainerFactory")
    public void onPaymentBlocked(ConsumerRecord<String, String> record) {
        log.debug("Status update: BLOCKED (fraud) for paymentId={}", record.key());
        statusService.updateStatus(record.key(), PaymentStatus.BLOCKED,
                "fraud-scoring", "Payment blocked by fraud scoring engine").subscribe();
    }

    @KafkaListener(topics = KafkaTopics.AML_SANCTIONS_CLEAR,
                   containerFactory = "statusKafkaListenerContainerFactory")
    public void onAmlSanctionsClear(ConsumerRecord<String, String> record) {
        log.debug("Status update: AML_SCREENED for paymentId={}", record.key());
        statusService.updateStatus(record.key(), PaymentStatus.AML_SCREENED,
                "aml-compliance", "AML and sanctions screening passed").subscribe();
    }

    @KafkaListener(topics = KafkaTopics.AML_SANCTIONS_HIT,
                   containerFactory = "statusKafkaListenerContainerFactory")
    public void onAmlSanctionsHit(ConsumerRecord<String, String> record) {
        log.debug("Status update: BLOCKED (AML) for paymentId={}", record.key());
        statusService.updateStatus(record.key(), PaymentStatus.BLOCKED,
                "aml-compliance", "Payment blocked — sanctions or AML hit").subscribe();
    }

    @KafkaListener(topics = KafkaTopics.PAYMENT_ROUTED,
                   containerFactory = "statusKafkaListenerContainerFactory")
    public void onPaymentRouted(ConsumerRecord<String, String> record) {
        log.debug("Status update: ROUTED for paymentId={}", record.key());
        statusService.updateStatus(record.key(), PaymentStatus.ROUTED,
                "routing-execution", "Payment routed to payment rail").subscribe();
    }

    @KafkaListener(topics = KafkaTopics.PAYMENT_FAILED,
                   containerFactory = "statusKafkaListenerContainerFactory")
    public void onPaymentFailed(ConsumerRecord<String, String> record) {
        log.debug("Status update: FAILED for paymentId={}", record.key());
        statusService.updateStatus(record.key(), PaymentStatus.FAILED,
                "routing-execution", "Payment failed during routing or execution").subscribe();
    }

    @KafkaListener(topics = KafkaTopics.PAYMENT_SETTLED,
                   containerFactory = "statusKafkaListenerContainerFactory")
    public void onPaymentSettled(ConsumerRecord<String, String> record) {
        log.debug("Status update: SETTLED for paymentId={}", record.key());
        statusService.updateStatus(record.key(), PaymentStatus.SETTLED,
                "settlement", "Payment settled and ledger posted").subscribe();
    }
}
