package com.clearflow.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.clearflow")
public class RoutingExecutionApplication {

    public static void main(String[] args) {
        SpringApplication.run(RoutingExecutionApplication.class, args);
    }
}
