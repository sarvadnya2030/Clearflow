package com.clearflow.common.security;

import ch.qos.logback.classic.pattern.ClassicConverter;
import ch.qos.logback.classic.spi.ILoggingEvent;

import java.util.regex.Pattern;

/**
 * Logback conversion rule that masks PII in log messages before they are written.
 *
 * Usage in logback-spring.xml:
 * <pre>
 *   &lt;conversionRule conversionWord="msg" converterClass="com.clearflow.common.security.PiiMaskingConverter"/&gt;
 * </pre>
 *
 * Patterns masked:
 * - IBAN:     DE89370400440532013000 → DE89****3000
 * - Card PAN: 4111111111111111       → 411111******1111
 * - Email:    user@example.com       → us**@example.com
 */
public class PiiMaskingConverter extends ClassicConverter {

    // IBAN: 2 letter country code + 2 digits + 11–28 alphanum chars
    private static final Pattern IBAN = Pattern.compile(
            "\\b([A-Z]{2}[0-9]{2})[A-Z0-9]{6,24}([A-Z0-9]{4})\\b");

    // 13–19 digit card PAN (Luhn-shaped)
    private static final Pattern CARD_PAN = Pattern.compile(
            "\\b([0-9]{6})[0-9]{6,9}([0-9]{4})\\b");

    // Email address
    private static final Pattern EMAIL = Pattern.compile(
            "\\b([a-zA-Z0-9]{2})[a-zA-Z0-9._%+\\-]*@([a-zA-Z0-9.\\-]+\\.[a-zA-Z]{2,})\\b");

    @Override
    public String convert(ILoggingEvent event) {
        String msg = event.getFormattedMessage();
        if (msg == null) return "";
        msg = IBAN.matcher(msg).replaceAll("$1****$2");
        msg = CARD_PAN.matcher(msg).replaceAll("$1******$2");
        msg = EMAIL.matcher(msg).replaceAll("$1**@$2");
        return msg;
    }
}
