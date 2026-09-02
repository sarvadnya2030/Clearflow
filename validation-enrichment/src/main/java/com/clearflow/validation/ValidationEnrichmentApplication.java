package com.clearflow.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.clearflow")
public class ValidationEnrichmentApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationEnrichmentApplication.class, args);
    }
}
