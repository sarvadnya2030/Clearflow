package com.clearflow.gateway.controller;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.clearflow.common.domain.PaymentInitiatedEvent;
import com.clearflow.common.security.MaskedIbanSerializer;
import com.clearflow.gateway.domain.PaymentRequest;
import com.clearflow.gateway.domain.PaymentResponse;
import com.clearflow.gateway.domain.PaymentStatus;
import com.clearflow.gateway.domain.PaymentStatusResponse;
import com.clearflow.gateway.messaging.ActiveMQPublisher;
import com.clearflow.gateway.messaging.KafkaEventPublisher;
import com.clearflow.gateway.messaging.SolacePublisher;
import com.clearflow.gateway.service.IdempotencyService;
import com.clearflow.gateway.service.RateLimitingFilter;
import com.clearflow.gateway.status.PaymentStatusService;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/api/v1/payments")
@SecurityRequirement(name = "bearerAuth")
@Tag(name = "Payment Ingestion")
public class PaymentController {

    private static final Logger log = LoggerFactory.getLogger(PaymentController.class);
    private static final int MAX_INFLIGHT = 1_000;

    private final AtomicInteger inflight = new AtomicInteger(0);
    private final IdempotencyService idempotencyService;
    private final RateLimitingFilter rateLimitingFilter;
    private final ActiveMQPublisher activeMQPublisher;
    private final SolacePublisher solacePublisher;
    private final KafkaEventPublisher kafkaEventPublisher;
    private final PaymentStatusService paymentStatusService;
    private final MeterRegistry meterRegistry;

    public PaymentController(IdempotencyService idempotencyService,
                             RateLimitingFilter rateLimitingFilter,
                             ActiveMQPublisher activeMQPublisher,
                             SolacePublisher solacePublisher,
                             KafkaEventPublisher kafkaEventPublisher,
                             PaymentStatusService paymentStatusService,
                             MeterRegistry meterRegistry) {
        this.idempotencyService = idempotencyService;
        this.rateLimitingFilter = rateLimitingFilter;
        this.activeMQPublisher = activeMQPublisher;
        this.solacePublisher = solacePublisher;
        this.kafkaEventPublisher = kafkaEventPublisher;
        this.paymentStatusService = paymentStatusService;
        this.meterRegistry = meterRegistry;
        Gauge.builder("clearflow_gateway_inflight", inflight, AtomicInteger::get)
                .description("In-flight payment submissions at the gateway")
                .register(meterRegistry);
    }

    @PostMapping
    @Operation(summary = "Ingest ISO 20022 pacs.008 credit transfer request into ClearFlow hub")
    @ApiResponse(responseCode = "202", description = "Payment accepted for orchestration")
    @ApiResponse(responseCode = "400", description = "Validation failed for payload fields")
    @ApiResponse(responseCode = "409", description = "Duplicate payment detected by idempotency signature")
    @ApiResponse(responseCode = "429", description = "Client exceeds per-second rate limit")
    @ApiResponse(responseCode = "401", description = "JWT missing, invalid, or expired")
    public Mono<ResponseEntity<PaymentResponse>> submitPayment(@Valid @RequestBody PaymentRequest request,
                                                               @AuthenticationPrincipal Jwt jwt,
                                                               @RequestHeader(value = "X-Correlation-Id", required = false) String incomingCorrelationId,
                                                               @RequestHeader(value = "X-Client-Tier", required = false) String clientTier) {
        // Bulkhead: shed load when too many requests are in-flight
        if (inflight.get() >= MAX_INFLIGHT) {
            return Mono.just(ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                    .header("Retry-After", "1")
                    .body(new PaymentResponse(null, null, PaymentStatus.REJECTED,
                            Instant.now(), null, "Service overloaded — retry in 1 second", Map.of())));
        }
        inflight.incrementAndGet();

        String clientId = jwt != null && jwt.getSubject() != null ? jwt.getSubject() : "anonymous";
        String paymentId = UUID.randomUUID().toString();
        String correlationId = incomingCorrelationId != null ? incomingCorrelationId : UUID.randomUUID().toString();

        MDC.put("clientId", clientId);
        MDC.put("paymentId", paymentId);
        MDC.put("correlationId", correlationId);
        MDC.put("debtorCountry", request.debtor().country());
        MDC.put("creditorCountry", request.creditor().country());
        MDC.put("amount", request.amount().toPlainString());
        MDC.put("currency", request.currency());

        return idempotencyService.checkAndStore(request, paymentId, correlationId)
                .flatMap(idempotencyResult -> {
                    if (idempotencyResult.duplicate()) {
                        return Mono.just(ResponseEntity.status(HttpStatus.CONFLICT).body(idempotencyResult.cachedResponse()));
                    }

                    return rateLimitingFilter.checkLimit(clientId, clientTier)
                            .flatMap(rate -> {
                                if (!rate.allowed()) {
                                    return Mono.just(ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                                            .header("X-RateLimit-Remaining", String.valueOf(rate.remaining()))
                                            .body(new PaymentResponse(
                                                    paymentId,
                                                    correlationId,
                                                    PaymentStatus.REJECTED,
                                                    Instant.now(),
                                                    "N/A",
                                                    "Rate limit exceeded",
                                                    Map.of("self", "/api/v1/payments/" + paymentId)
                                            )));
                                }

                                PaymentInitiatedEvent event = buildEvent(paymentId, correlationId, request);

                                PaymentResponse response = new PaymentResponse(
                                        paymentId,
                                        correlationId,
                                        PaymentStatus.ACCEPTED,
                                        Instant.now(),
                                        "PT2H",
                                        "Payment accepted and queued for processing",
                                        Map.of(
                                                "self", "/api/v1/payments/" + paymentId,
                                                "status", "/api/v1/payments/" + paymentId + "/status",
                                                "audit", "/api/v1/audit/" + paymentId
                                        )
                                );

                                Mono.fromRunnable(() -> {
                                    // activeMQPublisher.publish() call REMOVED from this hot path
                                    // 2026-09-02 -- CLEARFLOW.PAYMENT.INITIATED has zero consumers
                                    // anywhere in the codebase (verified: no @JmsListener, no
                                    // consumer service, confirmed via `artemis queue stat` showing
                                    // CONSUMER_COUNT=0 with 22,570+ messages backed up). Artemis's
                                    // producer-side flow control means jmsTemplate.send() BLOCKS
                                    // the calling thread (does not throw) once the destination hits
                                    // globalMaxSize -- this was silently stalling this entire
                                    // Mono.fromRunnable block for EVERY real payment, so Solace,
                                    // Kafka, the status update, and the PAYMENT_SUBMITTED log below
                                    // never ran. Found via full end-to-end infra recovery after a
                                    // machine reboot; the try/catch here never helped because a
                                    // blocked send doesn't throw. Solace + Kafka (below) are the
                                    // real, working, consumed event-distribution paths -- this JMS
                                    // publish was pure dead weight with an active failure mode.
                                    try {
                                        solacePublisher.publish(event);
                                    } catch (Exception ex) {
                                        log.debug("Solace publish failed for paymentId={}", paymentId);
                                    }
                                    try {
                                        kafkaEventPublisher.publish(event, "00-" + paymentId.replace("-", "") + "-0000000000000000-01", "");
                                    } catch (Exception ex) {
                                        log.debug("Kafka publish failed for paymentId={}", paymentId);
                                    }
                                    paymentStatusService.updateStatus(paymentId, PaymentStatus.INITIATED,
                                            "gateway", "Payment accepted and queued").subscribe();
                                    paymentStatusService.storeUetrMapping(request.uetr(), paymentId).subscribe();
                                    log.info("PAYMENT_SUBMITTED paymentId={} debtorCountry={} creditorCountry={} amount={} currency={} channel={}",
                                            paymentId, request.debtor().country(), request.creditor().country(),
                                            request.amount(), request.currency(), request.channel());
                                    Counter.builder("clearflow_payments_total")
                                            .tag("service", "gateway")
                                            .tag("status", "INITIATED")
                                            .tag("currency", request.currency())
                                            .description("Total payments submitted to ClearFlow")
                                            .register(meterRegistry)
                                            .increment();
                                }).subscribeOn(Schedulers.boundedElastic()).subscribe();

                                return idempotencyService.cacheResponse(response)
                                        .thenReturn(ResponseEntity.accepted()
                                                .header("X-RateLimit-Remaining", String.valueOf(rate.remaining()))
                                                .body(response));
                            });
                })
                .doFinally(signal -> {
                    inflight.decrementAndGet();
                    MDC.remove("clientId");
                    MDC.remove("paymentId");
                    MDC.remove("correlationId");
                    MDC.remove("debtorCountry");
                    MDC.remove("creditorCountry");
                    MDC.remove("amount");
                    MDC.remove("currency");
                });
    }

    @GetMapping("/{paymentId}/status")
    @Operation(summary = "Retrieve current orchestration state for a payment")
    public Mono<ResponseEntity<PaymentStatusResponse>> status(@PathVariable String paymentId) {
        return paymentStatusService.getStatus(paymentId).map(ResponseEntity::ok);
    }

    private PaymentInitiatedEvent buildEvent(String paymentId, String correlationId, PaymentRequest request) {
        return new PaymentInitiatedEvent(
                paymentId,
                correlationId,
                request.instructionId(),
                request.endToEndId(),
                request.uetr(),
                MaskedIbanSerializer.mask(request.debtor().iban()),
                MaskedIbanSerializer.mask(request.creditor().iban()),
                request.debtor().name(),
                request.creditor().name(),
                request.debtor().bic(),
                request.creditor().bic(),
                request.amount(),
                request.currency(),
                request.debtor().country(),
                request.creditor().country(),
                request.channel().name(),
                Instant.now(),
                "gateway"
        );
    }
}
