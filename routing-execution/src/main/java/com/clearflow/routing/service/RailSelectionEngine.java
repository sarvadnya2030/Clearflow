package com.clearflow.routing.service;

import com.clearflow.routing.domain.PaymentRail;
import com.clearflow.routing.domain.RoutingContext;
import org.springframework.stereotype.Service;

import java.util.Comparator;
import java.util.List;

@Service
public class RailSelectionEngine {

    private final List<PaymentRailRule> rules;

    public RailSelectionEngine(List<PaymentRailRule> rules) {
        this.rules = rules.stream().sorted(Comparator.comparingInt(PaymentRailRule::priority)).toList();
    }

    public PaymentRail selectRail(RoutingContext ctx) {
        return rules.stream()
                .filter(rule -> rule.matches(ctx))
                .findFirst()
                .map(rule -> rule.select(ctx))
                .orElse(PaymentRail.SWIFT_MT103);
    }
}
