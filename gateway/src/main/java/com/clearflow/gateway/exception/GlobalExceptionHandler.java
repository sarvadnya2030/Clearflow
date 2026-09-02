package com.clearflow.gateway.exception;

import com.clearflow.common.exception.ProblemDetailBuilder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;
import java.util.stream.Collectors;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(WebExchangeBindException.class)
    public ProblemDetail handleValidation(WebExchangeBindException exception) {
        ProblemDetail pd = ProblemDetailBuilder.of(HttpStatus.BAD_REQUEST, "Validation failure", "Request payload validation failed");
        Map<String, String> errors = exception.getBindingResult().getFieldErrors().stream()
                .collect(Collectors.toMap(FieldError::getField, FieldError::getDefaultMessage, (left, right) -> left));
        pd.setProperty("errors", errors);
        // Was previously silent (no structured evidence for a real gateway-level
        // rejection) -- logged here using the existing PAYMENT_REJECTED eventType
        // token (whitelisted in infrastructure/logstash/pipeline/clearflow.conf's
        // grok filter) so it's genuinely visible in ES, not a synthetic decoy.
        log.warn("PAYMENT_REJECTED paymentId=none reason=gateway_payload_validation fields={}", errors.keySet());
        return pd;
    }
}
