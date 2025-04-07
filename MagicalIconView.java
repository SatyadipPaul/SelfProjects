package com.example.application.views;

import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.dependency.CssImport;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.icon.Icon;
import com.vaadin.flow.component.icon.VaadinIcon;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;

@Route("magical-icon")
@PageTitle("Magical Icon")
@CssImport("./styles/magical-icon.css")
public class MagicalIconView extends VerticalLayout {

    public MagicalIconView() {
        addClassName("magical-icon-view");
        setSizeFull();
        setJustifyContentMode(JustifyContentMode.CENTER);
        setAlignItems(Alignment.CENTER);

        // Create the container for the icon and animation
        Div iconContainer = new Div();
        iconContainer.addClassName("icon-container");

        // Add the glowing background element
        Div glow = new Div();
        glow.addClassName("glow");
        iconContainer.add(glow);

        // Add the paper plane icon
        Icon paperPlane = new Icon(VaadinIcon.PAPERPLANE);
        paperPlane.addClassName("paper-plane");
        iconContainer.add(paperPlane);

        // Create container for glitter particles
        Div glitterContainer = new Div();
        glitterContainer.setId("glitter-container");
        iconContainer.add(glitterContainer);

        add(iconContainer);

        // Add JavaScript to create and animate the glitter particles
        UI.getCurrent().getPage().executeJs(
                "const glitterContainer = document.getElementById('glitter-container');" +

                        "// Array of magical colors\n" +
                        "const magicColors = [\n" +
                        "    '#FF73FA', // pink\n" +
                        "    '#73FDFF', // cyan\n" +
                        "    '#FFF973', // yellow\n" +
                        "    '#73FF8B', // green\n" +
                        "    '#FFA573', // orange\n" +
                        "    '#BE73FF'  // purple\n" +
                        "];\n" +

                        "// Create 30 glitter particles\n" +
                        "for (let i = 0; i < 30; i++) {\n" +
                        "    const particle = document.createElement('div');\n" +
                        "    particle.classList.add('glitter-particle');\n" +
                        "    glitterContainer.appendChild(particle);\n" +
                        "    \n" +
                        "    // Position randomly around the icon\n" +
                        "    const radius = 50; // Max distance from center\n" +
                        "    const angle = Math.random() * Math.PI * 2; // Random angle\n" +
                        "    const distance = Math.random() * radius; // Random distance within radius\n" +
                        "    \n" +
                        "    const x = Math.cos(angle) * distance;\n" +
                        "    const y = Math.sin(angle) * distance;\n" +
                        "    \n" +
                        "    particle.style.left = `calc(50% + ${x}px)`;\n" +
                        "    particle.style.top = `calc(50% + ${y}px)`;\n" +
                        "    \n" +
                        "    // Randomize animation\n" +
                        "    const duration = 0.8 + Math.random() * 1.5; // Between 0.8 and 2.3 seconds\n" +
                        "    const delay = Math.random() * 3; // Random delay up to 3 seconds\n" +
                        "    \n" +
                        "    // Assign random color from magic colors\n" +
                        "    const colorIndex = Math.floor(Math.random() * magicColors.length);\n" +
                        "    const color = magicColors[colorIndex];\n" +
                        "    \n" +
                        "    // Create a multi-layered shadow for a more magical glow\n" +
                        "    particle.style.boxShadow = `0 0 5px ${color}, 0 0 10px ${color}, 0 0 15px ${color}`;\n" +
                        "    particle.style.backgroundColor = color;\n" +
                        "    \n" +
                        "    // Add animation\n" +
                        "    particle.style.animation = `glitter ${duration}s ease-in-out ${delay}s infinite`;\n" +
                        "    \n" +
                        "    // Randomize particle size\n" +
                        "    const size = 3 + Math.random() * 5;\n" +
                        "    particle.style.width = `${size}px`;\n" +
                        "    particle.style.height = `${size}px`;\n" +
                        "    \n" +
                        "    // Some particles will have a star shape\n" +
                        "    if (Math.random() > 0.7) {\n" +
                        "        particle.style.clipPath = \"polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%)\";\n" +
                        "        particle.style.width = `${size * 2}px`;\n" +
                        "        particle.style.height = `${size * 2}px`;\n" +
                        "    }\n" +
                        "}"
        );
    }
}
