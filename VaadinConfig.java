package com.yourpackage.config;

import com.vaadin.flow.spring.annotation.EnableVaadin;
import com.vaadin.flow.server.ServiceInitEvent;
import com.vaadin.flow.server.VaadinServiceInitListener;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableVaadin
@RequiredArgsConstructor
public class VaadinConfig {

    private final VaadinSessionInitListener sessionInitListener;

    @Bean
    public VaadinServiceInitListener vaadinServiceInitListener() {
        return (ServiceInitEvent event) -> 
            event.getSource().addSessionInitListener(sessionInitListener);
    }
}
