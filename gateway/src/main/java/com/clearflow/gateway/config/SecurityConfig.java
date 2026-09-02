package com.clearflow.gateway.config;

import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.TrustManagerFactory;
import java.io.FileInputStream;
import java.security.KeyStore;
import java.util.List;

@Configuration
@EnableWebFluxSecurity
@EnableMethodSecurity
@Profile("!dev")
public class SecurityConfig {

    @Value("${security.cors.allowed-origins:http://localhost:3000}")
    private List<String> allowedOrigins;

    @Bean
    public SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .authorizeExchange(auth -> auth
                        .pathMatchers("/actuator/health", "/v3/api-docs/**", "/swagger-ui/**", "/swagger-ui.html").permitAll()
                        .pathMatchers("/api/v1/**").authenticated()
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(allowedOrigins);
        config.setAllowedMethods(List.of(HttpMethod.GET.name(), HttpMethod.POST.name(), HttpMethod.OPTIONS.name()));
        config.setAllowedHeaders(List.of("*"));
        config.setAllowCredentials(true);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }

    // TODO-PROD: Enforce mutual TLS with X509 client certificate trust chain from enterprise PKI.
    // Production setup should terminate TLS at service mesh / ingress and forward verified SPIFFE identity.

    /**
     * mTLS-aware WebClient for outbound calls from gateway to downstream services.
     * Active only when the "ssl" Spring profile is enabled (SPRING_PROFILES_ACTIVE=dev,ssl).
     *
     * Uses the gateway keystore as the client identity and the shared ClearFlow truststore
     * to verify downstream service certificates.
     *
     * Configuration is driven by the same CLEARFLOW_CERTS_DIR env var and
     * server.ssl.* properties from application-ssl.yml, kept consistent via
     * @Value injection rather than duplicating paths.
     */
    @Bean
    @Profile("ssl")
    public WebClient mtlsWebClient(
            @Value("${server.ssl.key-store}") String keyStorePath,
            @Value("${server.ssl.key-store-password}") String keyStorePassword,
            @Value("${server.ssl.trust-store}") String trustStorePath,
            @Value("${server.ssl.trust-store-password}") String trustStorePassword
    ) throws Exception {

        // Load gateway keystore (client identity presented to downstream services)
        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        try (FileInputStream ksIn = new FileInputStream(keyStorePath)) {
            keyStore.load(ksIn, keyStorePassword.toCharArray());
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keyStore, keyStorePassword.toCharArray());

        // Load shared truststore (contains ClearFlow CA; validates downstream certs)
        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        try (FileInputStream tsIn = new FileInputStream(trustStorePath)) {
            trustStore.load(tsIn, trustStorePassword.toCharArray());
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trustStore);

        // Build Netty SslContext with both key material and trust material
        SslContext sslContext = SslContextBuilder.forClient()
                .keyManager(kmf)
                .trustManager(tmf)
                .build();

        HttpClient httpClient = HttpClient.create()
                .secure(spec -> spec.sslContext(sslContext));

        return WebClient.builder()
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
