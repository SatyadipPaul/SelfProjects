# Spring Boot Code Explorer 🚀

**Navigate and Understand Your Spring Boot Projects with Ease!**

<!-- Optional: Add a screenshot or GIF here! -->
<!-- ![Spring Boot Explorer Demo](link/to/your/demo.gif) -->

Tired of getting lost in large Spring Boot codebases? Need a quick way to visualize dependencies, find specific components, or trace method calls without firing up your full IDE?

**Spring Boot Code Explorer** is a powerful command-line tool designed to statically analyze your Spring Boot projects, providing an interactive interface to browse code structure, identify Spring components, search through code, analyze method flows, and more!

## ✨ Why Use Spring Boot Code Explorer?

*   **Rapid Code Understanding:** Quickly grasp the structure and key components of unfamiliar Spring Boot projects.
*   **Dependency Tracing:** Visualize method call chains (who calls what, and what is called by whom).
*   **Component Discovery:** Easily list Controllers, Services, Repositories, Entities, Configurations, etc.
*   **Targeted Search:** Find specific methods or code snippets (identifiers, string literals) across the project.
*   **Offline Analysis:** Analyze code without needing a running application or heavy IDE indexing.
*   **Developer Productivity:** Speed up debugging, onboarding, and refactoring tasks.
*   **Git Integration:** Create patch files directly from your uncommitted changes.
*   **Text Conversion:** Easily export selected files or directories to `.txt` format for further processing or documentation.

## 🌟 Key Features

*   **Interactive CLI:** A user-friendly, menu-driven interface for exploring your project.
*   **Project Structure View:** Display the project's file tree or browse it interactively.
*   **Spring Component Identification:** Detects and lists common Spring stereotypes (`@Controller`, `@Service`, `@Repository`, `@Component`, `@Configuration`, `@Entity`, etc.).
*   **Component Details:** View annotations, fields, methods, inheritance, and implementation details for specific components.
*   **Method Analysis:**
    *   View method source code snippets.
    *   Trace outgoing method calls (limited depth).
    *   Trace incoming method calls (limited depth).
*   **Code Search:**
    *   Search for methods by name (case-insensitive).
    *   Search for string literals or identifiers within the codebase.
*   **Git Patch Creation:** Generate a `.patch` file from your current `git diff HEAD` (uncommitted changes). Supports binary diffs.
*   **File Conversion:** Convert specific files or entire directories to plain text (`.txt`) format, optionally preserving directory structure.
*   **Caching:** Caches analysis results (`.explorer_cache/`) for significantly faster startup on subsequent runs. Cache automatically invalidates if source files change.
*   **Colorized Output:** Enhances readability in supported terminals.

## ⚙️ Requirements

*   **Python 3.7+**
*   **Git:** Required for the "Create Git Patch" feature. Ensure it's installed and in your system's PATH.
*   **Libraries:**
    *   `javalang`: For parsing Java source code.
    *   `networkx`: For building and analyzing the method call graph.

## 🛠️ Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/your-username/spring-boot-code-explorer.git # Replace with your repo URL
    cd spring-boot-code-explorer
    ```

2.  **Install Dependencies:**
    ```bash
    pip install javalang networkx
    ```
    *(Consider creating a `requirements.txt` file for easier dependency management)*

## 🚀 Usage

Run the explorer from your terminal using Python's `-m` flag, pointing it to the package directory (`spring_explorer`).

**General Syntax:**

```bash
python -m spring_explorer [PROJECT_PATH] [OPTIONS]
```

**Arguments & Options:**

*   `PROJECT_PATH`: (Optional) The path to the root directory of the Spring Boot project you want to analyze. Defaults to the current directory (`.`).
*   `--no-cache`: (Optional) Ignores any existing analysis cache and forces a full re-analysis. Also clears the existing cache if found.
*   `--force-color`: (Optional) Forces colored terminal output, even if the terminal doesn't report support.
*   `--clear-cache-only`: (Optional) Clears the cache for the specified `PROJECT_PATH` and exits immediately. Does not run the analysis or interactive mode.

**Examples:**

```bash
# Analyze the project in the current directory
python -m spring_explorer

# Analyze a project at a specific path
python -m spring_explorer /path/to/my-spring-app

# Analyze the current project, ignoring the cache
python -m spring_explorer --no-cache

# Clear the cache for a specific project and exit
python -m spring_explorer /path/to/my-spring-app --clear-cache-only
```

## 🧭 Interactive Mode Guide

Upon running, the tool performs an initial analysis (or loads from cache) and presents the main menu:

```
=== Spring Boot Code Explorer ===
Project: /path/to/my-spring-app
Components: 123, Methods: 4567
Parsing Errors: 2  <-- (Only shown if errors occurred)

Main Menu:
1 - Project Structure
2 - Spring Components
3 - Search
4 - Method Analysis
5 - File / Git Operations
6 - Settings & Debug
0 - Exit

Enter choice:
```

Here's a breakdown of the menus:

---

### 1. Project Structure

*   Explore the file and directory layout of your project.

    ```
    === Project Structure Menu ===
    1 - View Full Tree (ASCII)
    2 - Browse Interactively
    0 - Back to Main Menu

    Enter choice:
    ```

    *   **View Full Tree:** Prints an ASCII representation of the project structure.
        ```
        My-Spring-App
        ├─ .git
        ├─ .explorer_cache
        ├─ src
        │  ├─ main
        │  │  ├─ java
        │  │  │  └─ com
        │  │  │     └─ example
        │  │  │        ├─ controller
        │  │  │        │  └─ 1.1.1.1.1 MyController.java
        │  │  │        ├─ service
        │  │  │        │  └─ 1.1.1.2.1 MyService.java
        │  │  │        ├─ repository
        │  │  │        │  └─ 1.1.1.3.1 MyRepository.java
        │  │  │        └─ 1.1.1.4 Application.java
        │  │  └─ resources
        │  │     └─ 1.1.2.1 application.properties
        │  └─ test
        │     └─ ...
        ├─ target
        └─ 2 pom.xml

        Press Enter to return...
        ```
    *   **Browse Interactively:** Opens a file browser within the terminal. Navigate using indices, go up (`..`), view files (`v INDEX`), or convert files/dirs (`c INDEX [-o DIR]`).

---

### 2. Spring Components

*   List and inspect detected Spring components.

    ```
    === Spring Components Menu ===
    1 - View All Spring Components
    2 - Filter by Type
    3 - View Component Details by Name
    0 - Back to Main Menu

    Enter choice:
    ```
    *   **View All:** Shows a list of all components found (e.g., Controllers, Services).
        ```
        === All Detected Spring Components ===
        Found 5 Spring components:

          - com.example.controller.MyController (RestController)
          - com.example.service.MyServiceImpl (Service)
          - com.example.repository.MyRepository (Repository)
          - com.example.config.AppConfig (Configuration)
          - com.example.model.User (Entity)

        Press Enter to return...
        ```
    *   **Filter by Type:** Lets you choose a specific type (e.g., `Service`) to list only those components.
    *   **View Component Details:** Enter a partial or full component name to see its details. If multiple match, you'll be asked to select.
        ```
        === Component Details: MyServiceImpl ===
        Full Name:    com.example.service.MyServiceImpl
        Type:         Service
        File:         src/main/java/com/example/service/MyServiceImpl.java
        Package:      com.example.service

        Annotations:  @Service, @Transactional
        Implements:   com.example.service.MyService

        --- Fields (2) ---
          - @Autowired private com.example.repository.MyRepository userRepository
              Annotations: @Autowired
          - private static final org.slf4j.Logger log

        --- Methods (5) ---
        1 - MyServiceImpl()
        2 - createUser(com.example.model.User)
        3 - findUserById(java.lang.Long)
        4 - getAllUsers()
        5 - updateUser(com.example.model.User)

        --- Actions ---
        v - View Full Source Code
        m - Analyze a Method (Enter Number)
        0 - Back to Previous Menu

        Enter action or method number:
        ```

---

### 3. Search

*   Find methods or code snippets.

    ```
    === Search Menu ===
    1 - Search Methods by Name
    2 - Search Code (Strings/Identifiers)
    0 - Back to Main Menu

    Enter choice:
    ```
    *   **Search Methods:** Enter a method name (case-insensitive). If found, you can select one to analyze directly.
        ```
        === Method Search Results for 'createUser' ===
        Found 1 matching method(s):

        1 - MyServiceImpl.createUser(com.example.model.User) in com.example.service.MyServiceImpl

        0 - Back to Search Menu

        Select number to analyze (0=Back): 1
        ```
    *   **Search Code:** Enter any text (identifier, string literal). Shows files containing the text and a preview.
        ```
        === Code Search Results for '"user.not.found"' ===
        Found matches in 1 file(s):

          - src/main/java/com/example/service/MyServiceImpl.java (com.example.service.MyServiceImpl)
            Preview: '"user.not.found"'

        Press Enter to return...
        ```

---

### 4. Method Analysis

*   Dive deep into specific methods, either by searching or entering their full key.

    ```
    === Method Analysis Menu ===
    1 - Analyze by Searching Name
    2 - Analyze by Entering Full Key
    0 - Back to Main Menu

    Enter choice:
    ```
    *   **Analyze by Searching Name:** Same as the Search menu option, leads to analysis.
    *   **Analyze by Entering Full Key:** Provide the exact method key (e.g., `com.example.service.MyService.findUserById(java.lang.Long)`).
        ```
        === Method Analysis: MyServiceImpl.findUserById(java.lang.Long) ===
        Component:    MyServiceImpl (Service)
        Key:          com.example.service.MyServiceImpl.findUserById(java.lang.Long)
        Annotations:  @Override

        --- Source Code ---
          @Override
          public User findUserById(Long id) {
              log.info("Finding user by id: {}", id);
              return userRepository.findById(id)
                      .orElseThrow(() -> new ResourceNotFoundException("user.not.found"));
          }
          ... (more lines)

        --- Calls (Outgoing) ---
          ├─ Logger.info(java.lang.String,java.lang.Object) (Logger)
          └─ MyRepository.findById(java.lang.Object) (MyRepository)
             └─ ... (calls within findById, if graph goes deeper)

        --- Called By (Incoming) ---
          └─ MyController.getUser(java.lang.Long) (MyController)

        Press Enter to return...
        ```

---

### 5. File / Git Operations

*   Perform actions related to files or Git.

    ```
    === File / Git Operations Menu ===
    1 - Convert Files/Directory to Text
    2 - Browse Files Interactively
    3 - Create Git Patch from Local Changes
    0 - Back to Main Menu

    Enter choice:
    ```
    *   **Convert to Text:** Enter a file/directory index (from structure view) and an optional output directory. Converts source files to `.txt`.
    *   **Browse Files Interactively:** Same as in the Project Structure menu.
    *   **Create Git Patch:** Creates a `.patch` file of your uncommitted changes (`git diff HEAD`). Prompts for output path and whether to include binary files.

---

### 6. Settings & Debug

*   Manage the cache or view debug information.

    ```
    === Settings & Debug Menu ===
    1 - Clear Cache & Re-analyze Project
    2 - Debug: Show Annotations & Component Types
    3 - Debug: List Java Parsing Errors
    0 - Back to Main Menu

    Enter choice:
    ```
    *   **Clear Cache & Re-analyze:** Deletes the `.explorer_cache` directory and runs the analysis again. Requires confirmation.
    *   **Debug Annotations/Types:** Lists all unique annotations found and counts of each component type detected.
    *   **List Parsing Errors:** Shows any errors encountered by `javalang` while parsing Java files.

---

### 0. Exit

*   Exits the Spring Boot Code Explorer.

## 💾 Caching

*   To speed up subsequent runs, the tool caches analysis results (ASTs, component info, call graph) in a `.explorer_cache` directory within your project root.
*   The cache is automatically invalidated and analysis is re-run if any `.java`, `.properties`, `.yml`, `.yaml`, or `.xml` files in your project have been modified since the cache was created.
*   You can force a cache clear and re-analysis using the `--no-cache` command-line option or the "Clear Cache & Re-analyze" option in the Settings menu.
*   Use `--clear-cache-only` to just remove the cache without running the tool.

##🤝 Contributing

Contributions are welcome! Please feel free to:

*   Report Bugs: Create an issue detailing the problem.
*   Suggest Features: Open an issue to discuss new ideas.
*   Submit Pull Requests: Fork the repository, make your changes, and submit a PR. Please try to follow existing code style.