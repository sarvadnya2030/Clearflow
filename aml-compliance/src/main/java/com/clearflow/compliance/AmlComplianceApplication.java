package com.clearflow.compliance;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication(scanBasePackages = "com.clearflow")
@EnableScheduling
public class AmlComplianceApplication {

    public static void main(String[] args) {
        SpringApplication.run(AmlComplianceApplication.class, args);
    }
}
