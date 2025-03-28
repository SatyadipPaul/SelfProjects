package com.example.application.views;
import com.vaadin.flow.component.Key;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.button.ButtonVariant;
import com.vaadin.flow.component.dependency.CssImport;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.H3;
import com.vaadin.flow.component.icon.Icon;
import com.vaadin.flow.component.icon.VaadinIcon;
import com.vaadin.flow.component.messages.MessageList;
import com.vaadin.flow.component.messages.MessageListItem;
import com.vaadin.flow.component.orderedlayout.FlexComponent;
import com.vaadin.flow.component.orderedlayout.FlexLayout;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.textfield.TextField;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.server.Command;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

@Route("modern-chat")
// Optional: Define custom CSS if needed, e.g., for message bubble styling
 @CssImport(value = "./styles/modern-chat-styles.css", themeFor = "vaadin-message-list")
public class ChatView extends VerticalLayout {

    private final MessageList messageList;
    private TextField messageInput;
    private Button sendButton;
    private final FlexLayout followUpContainer;
    private final H3 headerTitle;
    private final Div chatContainer;
    private final HorizontalLayout inputLayout;


    // Store messages in memory for this example
    private final List<MessageListItem> messages = new ArrayList<>();

    public ChatView() {
        // --- Basic View Setup ---
        setSizeFull();
        setPadding(false);
        setSpacing(false);
        addClassName(LumoUtility.Background.CONTRAST_5); // Give body slight background color
        setAlignItems(Alignment.CENTER); // Center chat container horizontally
        setJustifyContentMode(JustifyContentMode.CENTER); // Center chat container vertically

        // --- Create Components ---
        chatContainer = createChatContainer();
        headerTitle = createHeaderTitle(); // Create title separately
        Div header = createHeader(headerTitle);
        messageList = createMessageList();
        followUpContainer = createFollowUpContainer();
        inputLayout = createInputArea(); // Assigns to messageInput and sendButton

        // --- Assemble Layout ---
        chatContainer.add(header, messageList, followUpContainer, inputLayout);
        add(chatContainer);

        // --- Initial State & Events ---
        setupEventHandlers();
        addInitialMessage(); // Add the first greeting
    }

    // --- Component Creation Methods ---

    private Div createChatContainer() {
        Div container = new Div();
        container.addClassNames(
                LumoUtility.Display.FLEX,
                LumoUtility.FlexDirection.COLUMN,
                LumoUtility.Background.BASE, // White background
                LumoUtility.BorderRadius.LARGE,
                LumoUtility.BoxShadow.MEDIUM,
                LumoUtility.Width.FULL, // Take full width within parent alignment constraints
                LumoUtility.Margin.Vertical.MEDIUM // Add some space top/bottom if viewport is large
        );
        container.setMaxWidth("750px");
        container.setHeight("90vh"); // Use viewport height
        container.setMaxHeight("800px"); // Cap the height
        container.getStyle().set("overflow", "hidden"); // Ensure children are contained
        return container;
    }

    private H3 createHeaderTitle() {
        H3 title = new H3("AI Assistant");
        title.addClassNames(
                LumoUtility.TextColor.PRIMARY_CONTRAST, // White text
                LumoUtility.FontSize.LARGE,
                LumoUtility.Margin.NONE // Remove default margins
        );
        return title;
    }

    private Div createHeader(H3 title) {
        Div header = new Div(title);
        header.addClassNames(
                LumoUtility.Display.FLEX, // Use flex for alignment if needed later
                LumoUtility.AlignItems.CENTER,
                LumoUtility.JustifyContent.CENTER,
                LumoUtility.Padding.MEDIUM,
                LumoUtility.BorderRadius.LARGE // Match container radius only at top
        );
        // Apply a more explicit gradient
        header.getStyle()
                .set("background", "linear-gradient(135deg, hsl(214, 90%, 52%), hsl(250, 69%, 61%))") // Explicit blue/purple gradient
                .set("color", "var(--lumo-primary-contrast-color)");
        header.setWidthFull();
        return header;
    }


    private MessageList createMessageList() {
        MessageList list = new MessageList();
        // Make the list grow and scroll
        list.getStyle()
                .set("flexGrow", "1") // Allow growing
                .set("overflowY", "auto") // Enable vertical scroll
                .set("padding", "var(--lumo-space-m)"); // Add padding around messages
        // Optional: subtle background for the message area
        // .set("background", "var(--lumo-contrast-5pct)");
        return list;
    }

    private FlexLayout createFollowUpContainer() {
        FlexLayout container = new FlexLayout();
        container.getStyle()
                .set("flexWrap", "wrap") // Enable wrapping
                .set("padding", "var(--lumo-space-s) var(--lumo-space-m)") // Padding top/bottom(S) left/right(M)
                .set("gap", "var(--lumo-space-s)") // Space between buttons
                .set("borderTop", "1px solid var(--lumo-contrast-10pct)") // Separator line
                .set("background", "var(--lumo-contrast-5pct)") // Subtle background
                .set("minHeight", "44px") // Ensure minimum height for visibility
                .set("alignItems", "center") // Align items vertically if they wrap weirdly
                .set("boxSizing", "border-box"); // Include padding/border in height
        container.setWidthFull();
        container.setVisible(false); // Hide initially until there are questions
        return container;
    }

    private HorizontalLayout createInputArea() {
        messageInput = new TextField();
        messageInput.setPlaceholder("Type your message...");
        messageInput.setWidthFull();
        messageInput.setClearButtonVisible(true);
        // Add border radius for a more modern look (using utility class)
        messageInput.addClassName(LumoUtility.BorderRadius.MEDIUM);


        Icon sendIcon = VaadinIcon.PAPERPLANE_O.create();
        // Adjust icon color for better contrast on primary button
        sendIcon.getStyle().set("color", "var(--lumo-primary-contrast-color)");

        sendButton = new Button(sendIcon);
        sendButton.addThemeVariants(ButtonVariant.LUMO_PRIMARY); // Use primary color
        sendButton.setTooltipText("Send message");
        sendButton.setEnabled(false); // Initially disabled
        // Make button round
        sendButton.addThemeVariants(ButtonVariant.LUMO_ICON);


        HorizontalLayout layout = new HorizontalLayout(messageInput, sendButton);
        layout.setWidthFull();
        layout.setPadding(true);
        layout.setAlignItems(FlexComponent.Alignment.CENTER);
        layout.expand(messageInput);
        layout.getStyle()
                .set("borderTop", "1px solid var(--lumo-contrast-10pct)") // Separator line
                .set("background", "var(--lumo-base-color)"); // Match container bg or contrast slightly

        return layout;
    }

    // --- Event Handling & Logic ---

    private void setupEventHandlers() {
        messageInput.addValueChangeListener(event -> {
            if (sendButton != null) {
                boolean hasText = !event.getValue().trim().isEmpty();
                sendButton.setEnabled(hasText);
                // Change button style when enabled/disabled
                if (hasText) {
                    sendButton.addThemeVariants(ButtonVariant.LUMO_PRIMARY);
                } else {
                    sendButton.removeThemeVariants(ButtonVariant.LUMO_PRIMARY);
                }
            }
        });

        sendButton.addClickListener(event -> sendMessage());
        messageInput.addKeyPressListener(Key.ENTER, event -> sendMessage());
    }

    private void addInitialMessage() {
        // Add the first message after the UI is attached and visible
        UI.getCurrent().getPage().executeJs("return document.readyState").then(String.class, readyState -> {
            if ("complete".equals(readyState)) {
                addAiMessage("Hello! How can I assist you today?");
            }
        });
    }


    private void sendMessage() {
        if (messageInput == null) return;
        String text = messageInput.getValue().trim();

        if (!text.isEmpty()) {
            addUserMessage(text);
            messageInput.clear();
            messageInput.focus();
            clearFollowUpQuestions();
            simulateLLMInteraction(text);
        }
    }

    public void addUserMessage(String text) {
        MessageListItem userMessage = new MessageListItem(
                text, Instant.now(), "You");
        // Make user messages visually distinct (e.g., different color)
        // This requires CSS - see note below
        userMessage.addThemeNames("user-message");
        updateMessageList(userMessage);
    }

    public void addAiMessage(String text) {
        MessageListItem aiMessage = new MessageListItem(
                text, Instant.now(), "AI Assistant");
        aiMessage.setUserAbbreviation("AI");
        // Add theme name for potential CSS styling
        aiMessage.addThemeNames("ai-message");
        updateMessageList(aiMessage);
    }

    private void updateMessageList(MessageListItem item) {
        messages.add(item);
        // Create a copy to ensure MessageList detects the change
        messageList.setItems(new ArrayList<>(messages));

        // Scroll to bottom after adding message
        // Execute JS to scroll the message list's internal scrollable element
        // This requires knowing the internal structure or using a more robust scrolling utility
        // Simple approach (might need adjustment based on exact MessageList DOM):
        UI.getCurrent().getPage().executeJs("$0.shadowRoot.querySelector('div[part=\"list\"]').scrollTop = $0.shadowRoot.querySelector('div[part=\"list\"]').scrollHeight", messageList.getElement());
    }

    public void showFollowUpQuestions(List<String> questions) {
        clearFollowUpQuestions();
        if (questions != null && !questions.isEmpty() && followUpContainer != null) {
            questions.forEach(question -> {
                Button followUpButton = new Button(question);
                followUpButton.addThemeVariants(ButtonVariant.LUMO_CONTRAST, ButtonVariant.LUMO_SMALL);
                followUpButton.getStyle().set("cursor", "pointer");
                followUpButton.addClickListener(e -> {
                    if (messageInput != null) {
                        messageInput.setValue(question);
                        messageInput.focus();
                    }
                    // Consider auto-sending: sendMessage();
                });
                followUpContainer.add(followUpButton);
            });
            followUpContainer.setVisible(true); // Show the container
        }
    }

    public void clearFollowUpQuestions() {
        if (followUpContainer != null) {
            followUpContainer.removeAll();
            followUpContainer.setVisible(false); // Hide container when empty
        }
    }

    private void showTypingIndicator(boolean show) {
        // For a proper typing indicator, you'd add/remove a specific
        // component or MessageListItem styled as typing...
        if (show) {
            headerTitle.setText("AI is thinking..."); // Simple header update
        } else {
            headerTitle.setText("AI Assistant"); // Restore header
        }
    }

    private void simulateLLMInteraction(String userMessage) {
        UI currentUI = UI.getCurrent(); // Get UI reference *before* background thread
        showTypingIndicator(true);

        // Simulate async backend call
        CompletableFuture.runAsync(() -> {
            try {
                // Simulate processing time
                Thread.sleep(1500 + (long)(Math.random() * 1000));

                // Generate response (Replace with actual LLM call)
                String aiResponse = "Simulated response to: '" + userMessage + "'";
                List<String> followUps = List.of("Tell me more", "Can you explain that?", "New topic please");

                // Update UI using ui.access()
                currentUI.access((Command) () -> {
                    addAiMessage(aiResponse);
                    showFollowUpQuestions(followUps);
                    showTypingIndicator(false); // Hide typing indicator
                });

            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                // Handle interruption if necessary
                currentUI.access((Command) () -> showTypingIndicator(false)); // Ensure indicator is hidden
            }
        });
    }
}