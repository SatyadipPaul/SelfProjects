package com.yourpackage.security;

import com.vaadin.flow.server.VaadinSession;
import jakarta.servlet.http.HttpSession;
import lombok.extern.slf4j.Slf4j;

import java.util.Optional;

@Slf4j
public final class UserSessionHelper {
    
    private UserSessionHelper() {
        // Utility class, no instantiation
    }
    
    public static String getCurrentUser() {
        return getCurrentUserOptional().orElse("Anonymous");
    }
    
    public static Optional<String> getCurrentUserOptional() {
        try {
            return Optional.ofNullable(VaadinSession.getCurrent())
                .flatMap(session -> {
                    // Try to get from Vaadin session first
                    var user = session.getAttribute("currentUser", String.class);
                    if (user != null) {
                        return Optional.of(user);
                    }
                    
                    // If not in Vaadin session, check underlying HTTP session
                    return Optional.ofNullable(session.getSession())
                        .map(httpSession -> httpSession.getAttribute("currentUser"))
                        .filter(String.class::isInstance)
                        .map(String.class::cast)
                        .map(username -> {
                            // Store in Vaadin session for future use
                            session.setAttribute("currentUser", username);
                            return username;
                        });
                });
        } catch (Exception e) {
            log.error("Error getting current user", e);
            return Optional.empty();
        }
    }
    
    public static void setCurrentUser(String username) {
        try {
            Optional.ofNullable(VaadinSession.getCurrent())
                .ifPresent(session -> {
                    session.setAttribute("currentUser", username);
                    log.info("Set user '{}' in Vaadin session", username);
                });
        } catch (Exception e) {
            log.error("Error setting current user", e);
        }
    }
}
