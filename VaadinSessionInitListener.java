package com.yourpackage.config;

import com.vaadin.flow.server.SessionInitEvent;
import com.vaadin.flow.server.SessionInitListener;
import com.vaadin.flow.server.VaadinSession;
import com.vaadin.flow.server.WrappedSession;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.Optional;

@Slf4j
@Component
public class VaadinSessionInitListener implements SessionInitListener {

    @Override
    public void sessionInit(SessionInitEvent event) {
        VaadinSession session = event.getSession();
        WrappedSession wrappedSession = session.getSession();
        
        // Transfer user from HTTP session to Vaadin session using modern optional approach
        Optional.ofNullable(wrappedSession.getAttribute("currentUser"))
            .filter(String.class::isInstance)
            .map(String.class::cast)
            .ifPresent(username -> {
                session.setAttribute("currentUser", username);
                log.info("Transferred user '{}' from HTTP session to Vaadin session", username);
            });
    }
}
