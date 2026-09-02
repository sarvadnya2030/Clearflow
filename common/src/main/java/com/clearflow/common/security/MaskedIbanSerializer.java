package com.clearflow.common.security;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import java.io.IOException;

public class MaskedIbanSerializer extends JsonSerializer<String> {

    @Override
    public void serialize(String value, JsonGenerator gen, SerializerProvider serializers) throws IOException {
        gen.writeString(mask(value));
    }

    public static String mask(String iban) {
        if (iban == null || iban.isBlank()) {
            return iban;
        }
        String normalized = iban.replaceAll("\\s+", "");
        if (normalized.length() <= 8) {
            return "****";
        }
        return normalized.substring(0, 4) + "****" + normalized.substring(normalized.length() - 4);
    }
}
