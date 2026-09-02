package com.clearflow.compliance.domain;

import java.util.List;

public record SDNEntry(
        String uid,
        String name,
        String type,
        List<String> programs,
        String remarks,
        List<String> nameVariants,
        String country
) {
}
