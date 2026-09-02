package com.clearflow.gateway.domain;

import com.clearflow.common.security.MaskedIbanSerializer;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.time.LocalDate;

@Schema(description = "ISO 20022 pacs.008 payment submission payload")
public record PaymentRequest(
        @NotNull
        @Schema(example = "8b1f8f5f-3139-4cd7-abcb-a179f8f5f97a")
        String instructionId,

        @NotNull
        @Size(max = 35)
        @Schema(example = "E2E-20260223-00012345")
        String endToEndId,

        @NotNull
        @Schema(example = "f3d3b8ee-3daf-4c44-8a62-2dbece2ba67c")
        String uetr,

        @NotNull @Valid
        DebtorInfo debtor,

        @NotNull @Valid
        CreditorInfo creditor,

        @NotNull
        @DecimalMin("0.01")
        @DecimalMax("999999999.99")
        @Schema(example = "1250.55")
        BigDecimal amount,

        @NotNull
        @Pattern(regexp = "[A-Z]{3}")
        @Schema(example = "EUR")
        String currency,

        @Schema(example = "2026-02-24")
        LocalDate valueDate,

        @Schema(example = "SUPP")
        String purpose,

        @Size(max = 140)
        @Schema(example = "Invoice 456 settlement")
        String remittanceInfo,

        @NotNull
        PaymentChannel channel
) {

    public record DebtorInfo(
            @NotNull @Schema(example = "ALPINE LOGISTICS GMBH") String name,
            @NotNull @Iban @JsonSerialize(using = MaskedIbanSerializer.class) @Schema(example = "DE89370400440532013000") String iban,
            @NotNull @Schema(example = "DEUTDEDBXXX") String bic,
            @Schema(example = "Berlin") String address,
            @NotNull @Size(min = 2, max = 2) @Schema(example = "DE") String country
    ) {
    }

    public record CreditorInfo(
            @NotNull @Schema(example = "EURO TRADE SARL") String name,
            @NotNull @Iban @JsonSerialize(using = MaskedIbanSerializer.class) @Schema(example = "FR1420041010050500013M02606") String iban,
            @NotNull @Schema(example = "BNPAFRPP") String bic,
            @Schema(example = "Paris") String address,
            @NotNull @Size(min = 2, max = 2) @Schema(example = "FR") String country
    ) {
    }
}
