package com.clearflow.routing.controller;

import com.clearflow.routing.service.LiquidityReservationService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/liquidity")
public class LiquidityController {

    private final LiquidityReservationService liquidityReservationService;

    public LiquidityController(LiquidityReservationService liquidityReservationService) {
        this.liquidityReservationService = liquidityReservationService;
    }

    @GetMapping("/{paymentId}")
    public ResponseEntity<Map<String, Object>> getReservation(@PathVariable String paymentId) {
        Map<String, Object> row = liquidityReservationService.findByPaymentId(paymentId);
        if (row == null) return ResponseEntity.notFound().build();
        return ResponseEntity.ok(row);
    }
}
