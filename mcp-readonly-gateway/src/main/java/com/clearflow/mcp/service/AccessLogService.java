package com.clearflow.mcp.service;

import com.clearflow.common.messaging.KafkaTopics;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.lang.Nullable;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.Map;

@Service
public class AccessLogService {

    private static final Logger log = LoggerFactory.getLogger(AccessLogService.class);

    @Nullable
    private final KafkaTemplate<String, Object> kafkaTemplate;

    public AccessLogService(@Autowired(required = false) KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void log(String paymentId, String subject, String path) {
        if (kafkaTemplate != null) {
            kafkaTemplate.send(KafkaTopics.MCP_ACCESS_LOG, paymentId, Map.of(
                    "paymentId", paymentId,
                    "subject", subject,
                    "path", path,
                    "timestamp", Instant.now().toString()
            ));
        } else {
            log.debug("access-log paymentId={} subject={} path={}", paymentId, subject, path);
        }
    }
}
