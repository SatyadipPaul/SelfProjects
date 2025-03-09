package com.yourpackage.filter;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.vaadin.flow.server.VaadinSession;
import com.vaadin.flow.server.WrappedSession;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

import javax.servlet.*;
import javax.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.util.Enumeration;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class AuthCookieFilter implements Filter {

    private static final Logger log = LoggerFactory.getLogger(AuthCookieFilter.class);
    private static final Pattern AUTH_COOKIE_PATTERN = Pattern.compile("dxd-ct-auth=([^;]+)");
    private static final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {
        
        HttpServletRequest httpRequest = (HttpServletRequest) request;
        
        // Try to extract the auth cookie
        String displayName = extractDisplayNameFromCookie(httpRequest);
        
        if (displayName != null && !displayName.isEmpty()) {
            // Store in HTTP session for later access by Vaadin
            httpRequest.getSession().setAttribute("currentUser", displayName);
            log.info("Set user '{}' in session", displayName);
        }
        
        chain.doFilter(request, response);
    }

    private String extractDisplayNameFromCookie(HttpServletRequest request) {
        try {
            Enumeration<String> cookieHeaders = request.getHeaders("Cookie");
            if (cookieHeaders != null) {
                while (cookieHeaders.hasMoreElements()) {
                    String cookieHeader = cookieHeaders.nextElement();
                    Matcher matcher = AUTH_COOKIE_PATTERN.matcher(cookieHeader);
                    if (matcher.find()) {
                        String cookieValue = matcher.group(1);
                        log.debug("Found dxd-ct-auth cookie: {}", cookieValue);
                        
                        // Parse the JSON
                        JsonNode authData = objectMapper.readTree(cookieValue);
                        if (authData.has("displayName")) {
                            String displayName = authData.get("displayName").asText();
                            log.info("Extracted display name from auth cookie: {}", displayName);
                            return displayName;
                        }
                    }
                }
            }
        } catch (Exception e) {
            log.error("Error extracting display name from cookie", e);
        }
        return null;
    }
}
