package com.clearflow.mcp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.clearflow")
public class McpReadonlyGatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(McpReadonlyGatewayApplication.class, args);
    }
}
