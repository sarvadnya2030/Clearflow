package com.clearflow.routing.service;

import com.clearflow.routing.domain.PaymentRail;
import com.clearflow.routing.domain.RoutingContext;

public interface PaymentRailRule {
    boolean matches(RoutingContext ctx);
    PaymentRail select(RoutingContext ctx);
    int priority();
}
