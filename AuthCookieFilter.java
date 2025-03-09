package com.yourpackage.filter;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.util.Collections;
import java.util.Enumeration;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class AuthCookieFilter implements Filter {

    private static final Pattern AUTH_COOKIE_PATTERN = Pattern.compile("dxd-ct-auth=([^;]+)");
    private static final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {
        
        var httpRequest = (HttpServletRequest) request;
        
        // Extract display name using modern Optional pattern
        extractDisplayNameFromCookie(httpRequest)
            .ifPresent(displayName -> {
                httpRequest.getSession().setAttribute("currentUser", displayName);
                log.info("Set user '{}' in session", displayName);
            });
        
        chain.doFilter(request, response);
    }

    private Optional<String> extractDisplayNameFromCookie(HttpServletRequest request) {
        try {
            var cookieHeaders = request.getHeaders("Cookie");
            return parseDisplayNameFromHeaders(cookieHeaders);
        } catch (Exception e) {
            log.error("Error extracting display name from cookie", e);
            return Optional.empty();
        }
    }
    
    private Optional<String> parseDisplayNameFromHeaders(Enumeration<String> cookieHeaders) {
        if (cookieHeaders == null) {
            return Optional.empty();
        }
        
        return Collections.list(cookieHeaders).stream()
            .map(AUTH_COOKIE_PATTERN::matcher)
            .filter(Matcher::find)
            .map(matcher -> matcher.group(1))
            .peek(cookieValue -> log.debug("Found dxd-ct-auth cookie: {}", cookieValue))
            .map(this::extractDisplayNameFromJson)
            .filter(Optional::isPresent)
            .map(Optional::get)
            .findFirst();
    }
    
    private Optional<String> extractDisplayNameFromJson(String jsonValue) {
        try {
            JsonNode authData = objectMapper.readTree(jsonValue);
            if (authData.has("displayName")) {
                String displayName = authData.get("displayName").asText();
                log.info("Extracted display name from auth cookie: {}", displayName);
                return Optional.of(displayName);
            }
        } catch (Exception e) {
            log.warn("Failed to parse JSON from cookie: {}", jsonValue, e);
        }
        return Optional.empty();
    }
}
