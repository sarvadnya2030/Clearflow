package com.clearflow.mcp.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class MCPSecurityConfig {

    @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri:#{null}}")
    private String issuerUri;

    @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri:#{null}}")
    private String jwkSetUri;

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                // Actuator health/info always open
                .requestMatchers("/actuator/health", "/actuator/info").permitAll()
                // Admin endpoints can kill/restart live services -- mcp:admin only.
                // (Previously permitAll "for demo cascade control" -- an unauthenticated
                // process-kill switch is not acceptable once this is real infrastructure.)
                .requestMatchers("/mcp/admin/**").hasAuthority("SCOPE_mcp:admin")
                // Metrics/systemic endpoints require mcp:admin scope.
                // Fixed prefix: the controller is mapped at /mcp/**, not /api/mcp/** --
                // the old /api/mcp/** rules never matched a real request and silently
                // fell through to the generic authenticated() rule below.
                .requestMatchers("/mcp/metrics/**", "/mcp/diagnostics/systemic/**").hasAuthority("SCOPE_mcp:admin")
                // All other MCP endpoints require at least mcp:read
                .requestMatchers("/mcp/**").hasAnyAuthority("SCOPE_mcp:read", "SCOPE_mcp:admin")
                // Everything else also requires auth
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter()))
            );
        return http.build();
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(new JwtScopeConverter());
        return converter;
    }

    @Bean
    JwtDecoder jwtDecoder() {
        if (jwkSetUri != null && !jwkSetUri.isBlank()) {
            return NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();
        }
        if (issuerUri != null && !issuerUri.isBlank()) {
            return JwtDecoders.fromIssuerLocation(issuerUri);
        }
        // Dev fallback: symmetric HS256 secret from env (never use in prod)
        String secret = System.getenv().getOrDefault("MCP_JWT_SECRET",
                "clearflow-dev-secret-min-32-chars-long!!");
        javax.crypto.SecretKey key = new javax.crypto.spec.SecretKeySpec(
                secret.getBytes(java.nio.charset.StandardCharsets.UTF_8),
                "HmacSHA256");
        return NimbusJwtDecoder.withSecretKey(key).build();
    }
}
