package com.clearflow.gateway.domain;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import org.iban4j.IbanUtil;

public class IbanValidator implements ConstraintValidator<Iban, String> {

    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        if (value == null || value.isBlank()) {
            return false;
        }
        try {
            IbanUtil.validate(value.replaceAll("\\s+", ""));
            return true;
        } catch (RuntimeException ex) {
            return false;
        }
    }
}
