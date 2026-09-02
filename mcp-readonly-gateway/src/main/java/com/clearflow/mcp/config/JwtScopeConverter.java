package com.clearflow.mcp.config;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Converts JWT {@code scope} claim to Spring Security GrantedAuthority objects
 * using the {@code SCOPE_} prefix convention.
 *
 * Expected scopes:
 * - {@code mcp:read}  — access to timeline, fraud score, compliance tools
 * - {@code mcp:admin} — also allows metrics and systemic failure endpoints
 */
public class JwtScopeConverter implements Converter<Jwt, Collection<GrantedAuthority>> {

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Object scopeClaim = jwt.getClaim("scope");
        if (scopeClaim == null) return Collections.emptyList();

        List<String> scopes;
        if (scopeClaim instanceof String s) {
            scopes = List.of(s.split(" "));
        } else if (scopeClaim instanceof List<?> list) {
            scopes = list.stream().map(Object::toString).collect(Collectors.toList());
        } else {
            return Collections.emptyList();
        }

        return scopes.stream()
                .map(scope -> new SimpleGrantedAuthority("SCOPE_" + scope))
                .collect(Collectors.toList());
    }
}
