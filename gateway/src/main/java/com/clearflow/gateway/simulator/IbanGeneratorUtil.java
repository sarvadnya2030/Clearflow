package com.clearflow.gateway.simulator;

import java.util.Random;

/**
 * Generates syntactically valid (MOD-97 checksum) IBANs for simulation purposes.
 * Uses country-specific BBAN formats.
 */
public final class IbanGeneratorUtil {

    private static final String DIGITS = "0123456789";

    private IbanGeneratorUtil() {}

    public static String generate(String countryCode, Random rng) {
        String bban = switch (countryCode) {
            case "DE" -> digits(rng, 18);
            case "GB" -> "MOCK" + digits(rng, 14);
            case "FR" -> digits(rng, 23);
            case "NL" -> "MOCK" + digits(rng, 10);
            case "ES" -> digits(rng, 20);
            case "IT" -> "A" + digits(rng, 23);
            case "AT" -> digits(rng, 16);
            case "BE" -> digits(rng, 12);
            case "SE" -> digits(rng, 20);
            case "FI" -> digits(rng, 16);
            case "PL" -> digits(rng, 24);
            case "US" -> "USBN" + digits(rng, 13);
            case "AU" -> "AUBN" + digits(rng, 12);
            case "CA" -> "CABN" + digits(rng, 12);
            case "HK" -> "HKBN" + digits(rng, 12);
            case "JP" -> "JPBN" + digits(rng, 12);
            case "SG" -> "SGBN" + digits(rng, 12);
            case "ZA" -> "ZABN" + digits(rng, 12);
            case "AE" -> digits(rng, 19);
            case "BR" -> digits(rng, 25) + "P1";
            case "CH" -> digits(rng, 17);
            case "RU" -> digits(rng, 20);
            case "NG" -> digits(rng, 20);
            case "BO" -> digits(rng, 20);
            case "MM" -> digits(rng, 20);
            case "CU" -> digits(rng, 20);
            case "SY" -> digits(rng, 20);
            case "IR" -> digits(rng, 22);
            case "KP" -> digits(rng, 20);
            default  -> digits(rng, 18);
        };

        return buildIban(countryCode, bban);
    }

    private static String buildIban(String cc, String bban) {
        // Compute check digits using MOD-97
        String rearranged = bban + cc + "00";
        long mod = mod97(rearranged);
        int checkDigits = 98 - (int) mod;
        return cc + String.format("%02d", checkDigits) + bban;
    }

    private static long mod97(String s) {
        StringBuilder numeric = new StringBuilder();
        for (char c : s.toCharArray()) {
            if (Character.isLetter(c)) {
                numeric.append(Character.toUpperCase(c) - 'A' + 10);
            } else {
                numeric.append(c);
            }
        }
        long remainder = 0;
        for (char c : numeric.toString().toCharArray()) {
            remainder = (remainder * 10 + (c - '0')) % 97;
        }
        return remainder;
    }

    private static String digits(Random rng, int length) {
        StringBuilder sb = new StringBuilder(length);
        // First digit cannot be 0 for BBAN-style
        sb.append((char) ('1' + rng.nextInt(9)));
        for (int i = 1; i < length; i++) {
            sb.append(DIGITS.charAt(rng.nextInt(10)));
        }
        return sb.toString();
    }
}
