package com.clearflow.compliance.processor;

import com.clearflow.compliance.domain.AmlState;
import com.clearflow.compliance.domain.ScreeningRecord;
import com.clearflow.compliance.domain.ScreeningResult;
import com.clearflow.compliance.repository.ScreeningRecordRepository;
import com.clearflow.compliance.service.FuzzyScreeningEngine;
import com.clearflow.compliance.service.SDNLoader;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.camel.Exchange;
import org.apache.camel.Processor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class AMLScreeningProcessor implements Processor {

    private static final Logger log = LoggerFactory.getLogger(AMLScreeningProcessor.class);

    private final FuzzyScreeningEngine engine;
    private final SDNLoader sdnLoader;
    private final ScreeningRecordRepository repository;
    private final ObjectMapper objectMapper;

    @Value("${aml.fuzzy-threshold:0.85}")
    private double threshold;

    public AMLScreeningProcessor(FuzzyScreeningEngine engine,
                                 SDNLoader sdnLoader,
                                 ScreeningRecordRepository repository,
                                 ObjectMapper objectMapper) {
        this.engine = engine;
        this.sdnLoader = sdnLoader;
        this.repository = repository;
        this.objectMapper = objectMapper;
    }

    /**
     * EXACT match -> ESCALATED (highest-confidence hit, priority review).
     * FUZZY/SOUNDEX match -> HOLD (needs review, not a confirmed hit).
     * NONE -> CLEAR (proceeds immediately).
     * This is the formal decision the routing/retry path now actually gates
     * on -- previously "HIT" was just a log line with nothing downstream
     * enforcing that it blocked further processing.
     */
    private static AmlState decide(ScreeningResult debtor, ScreeningResult creditor) {
        boolean anyExact = debtor.matchType() == ScreeningResult.MatchType.EXACT
                || creditor.matchType() == ScreeningResult.MatchType.EXACT;
        boolean anyMatch = debtor.matchType() != ScreeningResult.MatchType.NONE
                || creditor.matchType() != ScreeningResult.MatchType.NONE;
        if (anyExact) return AmlState.ESCALATED;
        if (anyMatch) return AmlState.HOLD;
        return AmlState.CLEAR;
    }

    @Override
    public void process(Exchange exchange) {
        long start = System.currentTimeMillis();
        String debtorName = exchange.getIn().getHeader("debtorName", String.class);
        String creditorName = exchange.getIn().getHeader("creditorName", String.class);

        ScreeningResult debtor = engine.screenName(debtorName, sdnLoader.getAllNames(), threshold);
        ScreeningResult creditor = engine.screenName(creditorName, sdnLoader.getAllNames(), threshold);

        boolean hit = debtor.matchType() != ScreeningResult.MatchType.NONE || creditor.matchType() != ScreeningResult.MatchType.NONE;
        AmlState amlState = decide(debtor, creditor);

        ScreeningRecord record = new ScreeningRecord();
        record.setPaymentId(exchange.getIn().getHeader("paymentId", String.class));
        record.setCorrelationId(exchange.getIn().getHeader("correlationId", String.class));
        record.setDebtorName(debtorName);
        record.setCreditorName(creditorName);
        record.setDebtorMatchType(debtor.matchType().name());
        record.setDebtorMatchScore(debtor.matchScore());
        record.setDebtorMatchedEntity(debtor.matchedEntity());
        record.setDebtorListName(debtor.listName());
        record.setCreditorMatchType(creditor.matchType().name());
        record.setCreditorMatchScore(creditor.matchScore());
        record.setCreditorMatchedEntity(creditor.matchedEntity());
        record.setCreditorListName(creditor.listName());
        record.setOverallResult(hit ? "HIT" : "CLEAR");
        record.setReviewRequired(hit ? "Y" : "N");
        record.setAmlState(amlState);
        try {
            record.setOriginalPayload(objectMapper.writeValueAsString(exchange.getIn().getBody()));
        } catch (Exception ex) {
            log.warn("Failed to serialize payload for hold-replay, paymentId={}: {}",
                    exchange.getIn().getHeader("paymentId", String.class), ex.getMessage());
        }
        repository.save(record);

        exchange.getIn().setHeader("aml.result", hit ? "HIT" : "CLEAR");
        exchange.getIn().setHeader("aml.state", amlState.name());
        exchange.getIn().setHeader("aml.match.score", Math.max(debtor.matchScore(), creditor.matchScore()));
        exchange.getIn().setHeader("aml.match.type", hit ? "MATCH" : "NONE");
        exchange.getIn().setHeader("aml.matched.entity", hit ? (debtor.matchScore() >= creditor.matchScore() ? debtor.matchedEntity() : creditor.matchedEntity()) : "");

        long durationMs = System.currentTimeMillis() - start;
        String paymentId = record.getPaymentId();
        double topScore = Math.max(debtor.matchScore(), creditor.matchScore());
        String hitEntity = hit ? (debtor.matchScore() >= creditor.matchScore() ? debtor.matchedEntity() : creditor.matchedEntity()) : "";

        MDC.put("paymentId", paymentId != null ? paymentId : "");
        MDC.put("screeningResult", hit ? "HIT" : "CLEAR");
        MDC.put("matchScore", String.valueOf(topScore));
        MDC.put("listHit", hitEntity);
        MDC.put("durationMs", String.valueOf(durationMs));
        try {
            if (hit) {
                log.warn("AML_SANCTIONS_HIT paymentId={} matchedEntity={} matchScore={} durationMs={}",
                        paymentId, hitEntity, topScore, durationMs);
            } else {
                log.info("AML_SCREENING_COMPLETE paymentId={} result=CLEAR listsChecked=SDN+PEP durationMs={}",
                        paymentId, durationMs);
            }
        } finally {
            MDC.remove("screeningResult");
            MDC.remove("matchScore");
            MDC.remove("listHit");
            MDC.remove("durationMs");
        }
    }
}
