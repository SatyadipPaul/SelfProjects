# spring_explorer/cli.py
import os
import sys
import time
from collections import defaultdict

# --- Local Imports ---
from .explorer import SpringBootExplorer
from .utils import (logger, Colors, colored, header, menu_option, menu_title,
                    success, error, info, warning, clear_screen)
from .models import Method # Import Method if needed for type checking (e.g. in _select_...)
# --- End Local Imports ---


# --- Interactive CLI Class ---
class InteractiveSpringExplorer:
    def __init__(self, project_path):
        try:
            self.explorer = SpringBootExplorer(project_path)
            print(info("Initializing and analyzing project... This may take a moment."))
            self.explorer.analyze_project() # Call analysis here
            print(success("Analysis complete. Explorer ready."))
        except FileNotFoundError as e: print(error(f"Initialization failed: Project path not found - {e}")); sys.exit(1)
        except ImportError as e: print(error(f"Initialization failed: Missing library - {e}")); sys.exit(1) # Catch import errors too
        except Exception as e: print(error(f"Unexpected initialization error: {e}")); logger.error("Initialization error", exc_info=True); sys.exit(1)

    def run(self):
        # Menu definition using function references
        menu = {
            '1': ("Project Structure", self.project_structure_menu),
            '2': ("Spring Components", self.spring_components_menu),
            '3': ("Search", self.search_menu),
            '4': ("Method Analysis", self.method_analysis_menu),
            '5': ("File / Git Operations", self.file_git_operations_menu),
            '6': ("Settings & Debug", self.settings_menu)
        }
        while True:
            clear_screen(); print(menu_title("Spring Boot Code Explorer"))
            print(f"Project: {colored(self.explorer.project_path, Colors.BRIGHT_GREEN)}")
            # Safely access explorer attributes
            comp_count = len(self.explorer.components) if hasattr(self.explorer, 'components') else 0
            meth_count = len(self.explorer.methods) if hasattr(self.explorer, 'methods') else 0
            print(f"Components: {colored(comp_count, Colors.BRIGHT_YELLOW)}, Methods: {colored(meth_count, Colors.BRIGHT_YELLOW)}")
            if hasattr(self.explorer, 'parse_errors') and self.explorer.parse_errors:
                print(warning(f"Parsing Errors: {len(self.explorer.parse_errors)}"))

            print("\nMain Menu:"); [print(menu_option(k, v[0])) for k, v in menu.items()]; print(menu_option(0, "Exit"))

            try:
                choice = input(colored("\nEnter choice: ", Colors.BRIGHT_WHITE)).strip()
                if choice == '0':
                    print(info("Exiting Spring Boot Explorer...")); break
                elif choice in menu:
                    menu[choice][1]() # Call the associated menu function
                else:
                    print(error("Invalid choice. Please try again.")); time.sleep(1)
            except KeyboardInterrupt:
                clear_screen(); print(info("\nCtrl+C detected. Exiting...")); break
            except Exception as e:
                # Log the full error but show a simpler message to the user
                logger.error("Error in main CLI loop", exc_info=True)
                print(error(f"An unexpected error occurred: {type(e).__name__} - {e}"));
                input(colored("Press Enter to return to the main menu...", Colors.BOLD))

    # --- Menu Handlers ---

    def project_structure_menu(self):
        while True:
            clear_screen(); print(menu_title("Project Structure Menu"))
            print(menu_option(1, "View Full Tree (ASCII)")); print(menu_option(2, "Browse Interactively")); print(menu_option(0, "Back to Main Menu"))
            choice = input(colored("\nEnter choice: ", Colors.BRIGHT_WHITE)).strip()
            if choice == '0': break
            elif choice == '1':
                clear_screen(); print(menu_title("Project File Tree"))
                try:
                    self.explorer.print_project_structure()
                except Exception as e:
                    logger.error("Error printing project structure", exc_info=True)
                    print(error(f"Could not display structure: {e}"))
                input(colored("\nPress Enter to return...", Colors.BOLD))
            elif choice == '2':
                try:
                    self.explorer.interactive_structure_browser()
                except Exception as e:
                    logger.error("Error during interactive browsing", exc_info=True)
                    print(error(f"Browser error: {e}")); time.sleep(2)
            else: print(error("Invalid choice.")); time.sleep(1)

    def spring_components_menu(self):
        while True:
            clear_screen(); print(menu_title("Spring Components Menu"));
            print(menu_option(1, "View All Spring Components")); print(menu_option(2, "Filter by Type")); print(menu_option(3, "View Component Details by Name")); print(menu_option(0, "Back to Main Menu"))
            choice = input(colored("\nEnter choice: ", Colors.BRIGHT_WHITE)).strip()
            if choice == '0': break
            elif choice == '1': self._show_all_components()
            elif choice == '2': self.filter_components_menu()
            elif choice == '3': self._select_component_for_details()
            else: print(error("Invalid choice.")); time.sleep(1)

    def _show_all_components(self):
        clear_screen(); print(menu_title("All Detected Spring Components"))
        try:
            comps = self.explorer.get_spring_components()
            if comps:
                print(success(f"Found {len(comps)} Spring components:\n"))
                for c in comps:
                    # Use component_color utility for consistent coloring
                    comp_color = Colors.component_color(c.component_type)
                    type_str = colored(c.component_type, comp_color) if c.component_type else colored("Unknown", Colors.WHITE)
                    fqn_str = colored(c.fully_qualified_name, comp_color)
                    print(f"  - {fqn_str} ({type_str})")
            else:
                print(warning("No Spring components were detected in the analyzed files."))
        except Exception as e:
            logger.error("Error getting/displaying all components", exc_info=True)
            print(error(f"Could not display components: {e}"))
        input(colored("\nPress Enter to return...", Colors.BOLD))

    def filter_components_menu(self):
        clear_screen(); print(menu_title("Filter Components by Type"))
        try:
            # Get unique, sorted component types from the explorer data
            all_comps = self.explorer.components.values() if hasattr(self.explorer, 'components') else []
            types = sorted(list(set(c.component_type for c in all_comps if c.component_type and c.component_type != "Unknown")))

            if not types:
                print(warning("No specific component types detected to filter by.")); time.sleep(1.5); return

            print("Available types:")
            for i, t in enumerate(types):
                print(menu_option(i+1, colored(t, Colors.component_color(t)))) # Use component color
            print(menu_option(0,"Cancel Filter"))

            choice_str = input(colored("\nSelect type number to filter: ", Colors.BRIGHT_WHITE))
            choice = int(choice_str)

            if choice == 0: return # Cancel
            if 0 < choice <= len(types):
                selected_type = types[choice-1]
                self._display_filtered_components(selected_type)
            else:
                print(error("Invalid type number.")); time.sleep(1)
        except ValueError:
            print(error("Invalid input. Please enter a number.")); time.sleep(1)
        except Exception as e:
            logger.error("Error during component filtering", exc_info=True)
            print(error(f"Could not filter components: {e}")); time.sleep(1.5)


    def _display_filtered_components(self, type_filter):
        clear_screen(); print(menu_title(f"Components of Type: {type_filter}"))
        try:
            comps = self.explorer.get_spring_components(type_filter)
            if comps:
                print(success(f"Found {len(comps)} component(s) of type '{type_filter}':\n"))
                comp_color = Colors.component_color(type_filter)
                for c in comps:
                    print(f"  - {colored(c.fully_qualified_name, comp_color)}")
            else:
                print(warning(f"No components found matching type '{type_filter}'."))
        except Exception as e:
            logger.error(f"Error displaying filtered components for type {type_filter}", exc_info=True)
            print(error(f"Could not display components: {e}"))
        input(colored("\nPress Enter to return...", Colors.BOLD))

    def _select_component_for_details(self):
        clear_screen(); print(menu_title("View Component Details"))
        name_part = input(colored("Enter component name (full or partial, case-insensitive): ", Colors.BRIGHT_WHITE)).strip()
        if not name_part: print(warning("No name entered.")); time.sleep(1); return

        try:
            name_lower = name_part.lower()
            matches = [c for fqn, c in self.explorer.components.items() if name_lower in fqn.lower()]

            if not matches:
                print(warning(f"No components found matching '{name_part}'.")); time.sleep(1.5)
            elif len(matches) == 1:
                self.show_component_details(matches[0]) # Show details directly
            else:
                # Let user choose from multiple matches
                self._select_from_multiple_components(matches, name_part)
        except Exception as e:
            logger.error(f"Error searching for component '{name_part}'", exc_info=True)
            print(error(f"Could not search for component: {e}")); time.sleep(1.5)


    def _select_from_multiple_components(self, matches, search_term):
        clear_screen(); print(menu_title(f"Multiple Matches for '{search_term}'"))
        print(warning(f"Found {len(matches)} components matching '{search_term}'. Please select one:"))
        matches.sort(key=lambda c:c.fully_qualified_name) # Sort for consistent display

        for i, comp in enumerate(matches):
            comp_color = Colors.component_color(comp.component_type)
            type_str = colored(f"({comp.component_type})", comp_color) if comp.component_type else ""
            fqn_str = colored(comp.fully_qualified_name, comp_color)
            print(menu_option(i+1, f"{fqn_str} {type_str}"))
        print(menu_option(0,"Cancel Selection"))

        try:
            choice_str = input(colored("\nSelect number: ", Colors.BRIGHT_WHITE))
            sel = int(choice_str)
            if 0 < sel <= len(matches):
                self.show_component_details(matches[sel-1]) # Show details for selected component
            elif sel == 0:
                print(info("Selection cancelled.")) ; time.sleep(1)
            else: print(error("Invalid selection number.")); time.sleep(1)
        except ValueError: print(error("Invalid input. Please enter a number.")); time.sleep(1)
        except Exception as e: # Catch errors during detail display
            logger.error("Error showing details after selection", exc_info=True)
            print(error(f"Could not show component details: {e}")); time.sleep(1.5)


    def show_component_details(self, comp):
        while True: # Loop to allow actions within details view
            clear_screen()
            comp_color = Colors.component_color(comp.component_type)
            print(menu_title(f"Component Details: {comp.name}"))

            print(f"Full Name:    {colored(comp.fully_qualified_name, comp_color)}")
            print(f"Type:         {colored(comp.component_type, comp_color)}")
            try:
                rel_path = os.path.relpath(comp.file_path, self.explorer.project_path)
            except ValueError: # Handle path errors (e.g., different drives on Windows)
                rel_path = comp.file_path # Show absolute path as fallback
            print(f"File:         {rel_path}")
            print(f"Package:      {comp.package}")

            if comp.annotations: print(f"\nAnnotations:  {', '.join(colored(a, Colors.BRIGHT_YELLOW) for a in comp.annotations)}")
            if comp.generics: print(f"Generics:     <{', '.join(comp.generics)}>")
            if comp.extends:
                # Handle extends being str or list
                extends_str = comp.extends if isinstance(comp.extends, str) else ', '.join(comp.extends)
                print(f"Extends:      {extends_str}")
            if comp.implements: print(f"Implements:   {', '.join(comp.implements)}")

            # Display Fields
            if comp.fields:
                print(f"\n--- Fields ({len(comp.fields)}) ---")
                # Sort fields by name for consistent display
                for field_name, field_obj in sorted(comp.fields.items()):
                    print(f"  - {field_obj}") # Uses Field.__str__
                    if field_obj.annotations:
                        print(f"      Annotations: {', '.join(colored(a, Colors.BRIGHT_YELLOW) for a in field_obj.annotations)}")
            else: print("\n--- Fields: None ---")

            # Display Methods (and Constructors)
            # Sort methods/constructors by name/signature
            m_list = []
            for method_sig, method_obj in comp.methods.items():
                display_name = method_sig # Default display
                # Adjust display for constructors
                if method_obj.name == '<init>':
                    # Use class name + signature for display if needed, but method_sig usually has it
                    display_name = f"{comp.name}{method_obj.signature}" # Reconstruct for clarity?
                m_list.append((display_name, method_obj)) # Store (display_name, MethodObject)

            m_list.sort(key=lambda x: x[0]) # Sort by display name

            if m_list:
                print(f"\n--- Methods ({len(m_list)}) ---")
                method_map = {} # To map display index back to method object
                for i, (disp_sig, method_obj) in enumerate(m_list):
                    print(menu_option(i+1, colored(disp_sig, Colors.BRIGHT_CYAN)))
                    method_map[i+1] = method_obj # Store object by display index
            else: print("\n--- Methods: None ---")

            # Action Menu for Component Details
            print("\n--- Actions ---")
            print(menu_option('v',"View Full Source Code"))
            if m_list: print(menu_option('m',"Analyze a Method (Enter Number)"))
            print(menu_option('0',"Back to Previous Menu"))

            choice = input(colored("\nEnter action or method number: ", Colors.BRIGHT_WHITE)).strip().lower()

            if choice == '0': break # Exit component details view
            elif choice == 'v': self._view_source(comp)
            elif choice == 'm' and m_list:
                self._select_method_for_analysis_from_list(method_map, comp) # Pass map and component
            elif choice.isdigit() and m_list: # Allow entering method number directly
                try:
                    idx = int(choice)
                    if idx in method_map:
                        self._analyze_selected_method(method_map[idx], comp)
                    else: print(error("Invalid method number.")); time.sleep(1)
                except ValueError: print(error("Invalid input.")); time.sleep(1) # Should not happen if isdigit passed
            else: print(error("Invalid action choice.")); time.sleep(1)


    def _view_source(self, comp_or_method_obj):
        # Can view source for a component or potentially a method (if path is known)
        # Determine file path and item name
        file_path = None
        item_name = "Unknown Source"
        if hasattr(comp_or_method_obj, 'file_path'): # It's a SpringBootComponent
            file_path = comp_or_method_obj.file_path
            item_name = comp_or_method_obj.name
        elif hasattr(comp_or_method_obj, 'parent_component') and hasattr(comp_or_method_obj.parent_component, 'file_path'): # It's a Method
            file_path = comp_or_method_obj.parent_component.file_path
            item_name = f"{comp_or_method_obj.parent_component.name}.{comp_or_method_obj.name}"

        if not file_path or not os.path.isfile(file_path):
            print(error(f"Source file path not found or invalid for {item_name}.")); time.sleep(1.5); return

        try:
            clear_screen(); print(colored(f"Source Code: {item_name}", Colors.BOLD)); print(colored(f"File: {file_path}", Colors.BRIGHT_BLACK)); print(colored("="*80, Colors.BRIGHT_CYAN))
            content = ""; page_size = os.get_terminal_size().lines - 5 if hasattr(os, 'get_terminal_size') else 30
            read_ok = False; encs = ['utf-8', 'latin-1', 'cp1252']

            for enc in encs:
                try:
                    with open(file_path,'r',encoding=enc) as f: content=f.read(); read_ok=True; break
                except UnicodeDecodeError: continue
                except Exception as e_r: raise IOError(f"Read error ({enc}): {e_r}") from e_r
            if not read_ok: raise IOError("Cannot read file with tested encodings")

            lines = content.splitlines(); line_count = len(lines)
            # Simple Pager
            for page_start in range(0, line_count, page_size):
                page_end = min(page_start + page_size, line_count)
                # Add line numbers (optional but helpful)
                page_lines_with_nums = []
                for i in range(page_start, page_end):
                    line_num = i + 1
                    page_lines_with_nums.append(f"{colored(str(line_num).rjust(4), Colors.BRIGHT_BLACK)}: {lines[i]}")

                print("\n".join(page_lines_with_nums))

                if page_end < line_count:
                    cont = input(colored(f"--More-- (Lines {page_start+1}-{page_end}/{line_count}) (Enter/q):", Colors.BRIGHT_YELLOW))
                    if cont.lower() == 'q': break
                else:
                    print(colored("\n--End of File--", Colors.BRIGHT_YELLOW))

            print(colored("="*80, Colors.BRIGHT_CYAN)); input(colored("Press Enter to return...", Colors.BOLD))
        except Exception as e:
            logger.error(f"Error reading/displaying source for {item_name}", exc_info=True)
            print(error(f"Could not view source: {e}")); time.sleep(2)


    def _select_method_for_analysis_from_list(self, method_map, component):
        # Assumes method_map is {1: MethodObj1, 2: MethodObj2, ...}
        try:
            idx_str = input(colored("Enter method number to analyze: ", Colors.BRIGHT_WHITE))
            idx = int(idx_str)
            if idx in method_map:
                selected_method = method_map[idx]
                self._analyze_selected_method(selected_method, component)
            else:
                print(error("Invalid method number selected.")); time.sleep(1)
        except ValueError:
            print(error("Invalid input. Please enter a number.")); time.sleep(1)
        except Exception as e:
            logger.error("Error during method selection/analysis", exc_info=True)
            print(error(f"Could not analyze method: {e}")); time.sleep(1.5)

    def _analyze_selected_method(self, method_obj, component_obj):
        # Construct the canonical key needed by the explorer's analysis method
        try:
            # Parameter types for the key might need careful extraction if not simple
            # Basic extraction: Get type part, ignore generics for key matching usually
            param_types = []
            if hasattr(method_obj, 'parameters') and method_obj.parameters:
                for p_sig in method_obj.parameters: # e.g., "String arg", "List<String> items"
                    type_part = p_sig.split()[0]
                    base_type = type_part.split('<')[0] # Get "String" or "List"
                    # Resolve simple names if necessary (complex part) - using original logic for now
                    # Assuming _resolve_type_name works correctly for this context:
                    # resolved_type = self.explorer._resolve_type_name(base_type, component_obj)
                    # For simplicity here, we'll just use the base_type found in the signature directly.
                    # More robust analysis might require resolving against imports.
                    param_types.append(base_type)

            signature_key_part = f"({','.join(param_types)})"
            method_key = f"{component_obj.fully_qualified_name}.{method_obj.name}{signature_key_part}"

            # Call the main analysis display function
            self.analyze_method(method_key)

        except Exception as e:
            logger.error(f"Error constructing key or calling analysis for {method_obj}", exc_info=True)
            print(error(f"Could not prepare method for analysis: {e}")); time.sleep(1.5)


    def search_menu(self):
        while True:
            clear_screen(); print(menu_title("Search Menu"));
            print(menu_option(1,"Search Methods by Name")); print(menu_option(2,"Search Code (Strings/Identifiers)")); print(menu_option(0,"Back to Main Menu"))
            choice = input(colored("\nEnter choice: ", Colors.BRIGHT_WHITE)).strip()
            if choice == '0': break
            elif choice == '1': self.search_methods()
            elif choice == '2': self.search_strings()
            else: print(error("Invalid choice.")); time.sleep(1)

    def search_methods(self):
        clear_screen(); print(menu_title("Search Methods by Name"))
        method_name = input(colored("Enter method name (case-insensitive): ", Colors.BRIGHT_WHITE)).strip()
        if not method_name: print(warning("No method name entered.")); time.sleep(1); return

        try:
            found_methods = self.explorer.search_method(method_name) # Assumes search_method is case-insensitive enough

            if not found_methods:
                print(warning(f"No methods found matching '{method_name}'.")); input(colored("Press Enter...", Colors.BOLD)); return

            clear_screen(); print(menu_title(f"Method Search Results for '{method_name}'"))
            print(success(f"Found {len(found_methods)} matching method(s):\n"))

            method_map = {} # Map display index to method object for analysis selection
            for i, m_obj in enumerate(found_methods):
                comp_color = Colors.component_color(m_obj.parent_component.component_type)
                method_str = colored(f"{m_obj.parent_component.name}.{m_obj.name}{m_obj.signature}", Colors.BRIGHT_GREEN)
                comp_str = colored(f"in {m_obj.parent_component.fully_qualified_name}", comp_color)
                print(menu_option(i+1, f"{method_str} {comp_str}"))
                method_map[i+1] = m_obj # Store method object by index

            print(menu_option(0,"Back to Search Menu"))

            try:
                choice_str = input(colored("\nSelect number to analyze (0=Back): ", Colors.BRIGHT_WHITE))
                choice = int(choice_str)
                if choice == 0: return # Go back
                if 0 < choice <= len(found_methods):
                    selected_method = method_map[choice]
                    # Analyze the selected method (needs component context)
                    self._analyze_selected_method(selected_method, selected_method.parent_component)
                else: print(error("Invalid selection number.")); time.sleep(1)
            except ValueError: print(error("Invalid input. Please enter a number.")); time.sleep(1)

        except Exception as e:
            logger.error(f"Error during method search for '{method_name}'", exc_info=True)
            print(error(f"Could not perform method search: {e}")); time.sleep(1.5)


    def search_strings(self):
        clear_screen(); print(menu_title("Search Code (Strings/Identifiers)"))
        search_term = input(colored("Enter text to search for (case-insensitive): ", Colors.BRIGHT_WHITE)).strip()
        if not search_term: print(warning("No search term entered.")); time.sleep(1); return

        try:
            results = self.explorer.search_string(search_term) # Assumes search_string handles case
            clear_screen(); print(menu_title(f"Code Search Results for '{search_term}'"))

            if not results:
                print(warning(f"No matches found for '{search_term}'.")); input(colored("Press Enter...", Colors.BOLD)); return

            # Group results by file path for display
            results_by_file = defaultdict(list)
            for r in results:
                # Ensure path is present
                if 'path' in r and 'original' in r:
                    results_by_file[r['path']].append(r['original'])

            num_files = len(results_by_file)
            print(success(f"Found matches in {num_files} file(s):\n"));

            display_count = 0
            max_display_files = 25 # Limit number of files shown directly

            for file_path, original_matches in sorted(results_by_file.items()):
                if display_count >= max_display_files:
                    print(f"\n... and {num_files - max_display_files} more files.")
                    break

                try: rel_path = os.path.relpath(file_path, self.explorer.project_path)
                except ValueError: rel_path = file_path # Fallback for different drives etc.

                # Try to find the FQN associated with this file (useful for Java files)
                fqn_found = next((r['fqn'] for r in results if r.get('path') == file_path and 'fqn' in r), None)
                fqn_display = colored(f" ({fqn_found})", Colors.BRIGHT_GREEN) if fqn_found else ""

                print(f"  - {colored(rel_path, Colors.BRIGHT_CYAN)}{fqn_display}")

                # Show a preview of unique matches found in the file
                unique_origs = sorted(list(set(original_matches)))
                preview_matches = unique_origs[:5] # Show first few unique matches
                preview_str = ", ".join(f"'{s[:40]}{'...' if len(s)>40 else ''}'" for s in preview_matches)
                if len(unique_origs) > 5: preview_str += f", ... ({len(unique_origs) - 5} more unique)"
                print(f"    Preview: {colored(preview_str, Colors.WHITE)}")

                display_count += 1

            input(colored("\nPress Enter to return...", Colors.BOLD))

        except Exception as e:
            logger.error(f"Error during string/code search for '{search_term}'", exc_info=True)
            print(error(f"Could not perform search: {e}")); time.sleep(1.5)


    def method_analysis_menu(self):
        while True:
            clear_screen(); print(menu_title("Method Analysis Menu"));
            print(menu_option(1,"Analyze by Searching Name")); print(menu_option(2,"Analyze by Entering Full Key")); print(menu_option(0,"Back to Main Menu"))
            choice = input(colored("\nEnter choice: ", Colors.BRIGHT_WHITE)).strip()
            if choice == '0': break
            elif choice == '1':
                # This reuses the search_methods UI, which includes selection for analysis
                self.search_methods()
            elif choice == '2':
                self.analyze_method_by_key_input()
            else: print(error("Invalid choice.")); time.sleep(1)

    def analyze_method_by_key_input(self):
        clear_screen(); print(menu_title("Analyze Method by Full Key"))
        print(info("Example key format: com.example.package.MyClass.myMethod(java.lang.String,int)"))
        method_key = input(colored("\nEnter method key: ", Colors.BRIGHT_WHITE)).strip()
        if method_key:
            self.analyze_method(method_key) # Call the main analysis display
        else:
            print(warning("No method key entered.")); time.sleep(1)

    def analyze_method(self, method_key):
        # This function retrieves analysis data and displays it.
        try:
            flow_data = self.explorer.analyze_method_flow(method_key)

            if not flow_data:
                # Error message already logged by analyze_method_flow if not found
                print(error(f"Could not retrieve analysis data for key '{method_key}'. Check key format and logs.")); time.sleep(2); return

            # Handle case where analyze_method_flow returned multiple matches
            if "multiple_matches" in flow_data:
                print(warning(f"Ambiguous key '{method_key}'. Please select the specific method:"))
                self._select_from_multiple_methods_for_analysis(method_key, flow_data["multiple_matches"])
                return # Return after handling selection

            # --- Display Analysis Results ---
            clear_screen()
            comp_color=Colors.component_color(flow_data.get('component_type', ''))
            print(menu_title(f"Method Analysis: {flow_data.get('method', 'N/A')}"))

            print(f"Component:    {colored(flow_data.get('component', 'N/A'), comp_color)} ({colored(flow_data.get('component_type', 'N/A'), comp_color)})")
            print(f"Key:          {colored(flow_data.get('method_key', 'N/A'), Colors.BRIGHT_MAGENTA)}")
            # print(f"Signature:    {flow_data.get('signature', 'N/A')}") # Already in title

            if flow_data.get('annotations'):
                print(f"Annotations:  {', '.join(colored(a, Colors.BRIGHT_YELLOW) for a in flow_data['annotations'])}")

            # Display Source Code Snippet
            print(colored("\n--- Source Code ---", Colors.BOLD))
            source_lines = flow_data.get('source', [])
            if source_lines:
                # Show limited number of lines directly, prompt to view full source?
                max_lines_preview = 20
                line_count = len(source_lines)
                for i, line in enumerate(source_lines):
                    if i >= max_lines_preview:
                        print(colored(f"  ... ({line_count - max_lines_preview} more lines)", Colors.BRIGHT_BLACK))
                        break
                    print(f"  {line}") # Add line numbers? Maybe not needed here.
            else: print(colored("  (Source code not available or not found)", Colors.BRIGHT_BLACK))

            # Display Calls (Outgoing)
            print(colored("\n--- Calls (Outgoing) ---", Colors.BOLD))
            self._print_flow_hierarchy(flow_data.get("calls", []), "  ", "children") # Pass key 'children'

            # Display Called By (Incoming)
            print(colored("\n--- Called By (Incoming) ---", Colors.BOLD))
            self._print_flow_hierarchy(flow_data.get("called_by", []), "  ", "parents") # Pass key 'parents'

            input(colored("\nPress Enter to return...", Colors.BOLD))

        except Exception as e:
            logger.error(f"Error displaying analysis for key '{method_key}'", exc_info=True)
            print(error(f"Could not display method analysis: {e}")); time.sleep(2)


    def _select_from_multiple_methods_for_analysis(self, original_key, method_objects):
        # Used when a key matches multiple methods (e.g., case-insensitive search)
        print(warning(f"Ambiguous key '{original_key}'. Found {len(method_objects)} potential matches:"))

        method_keys_map = {} # Map display index to full method key string
        for i, m_obj in enumerate(method_objects):
            try:
                # Reconstruct the key string for display and later use
                param_types = []
                if hasattr(m_obj, 'parameters') and m_obj.parameters:
                    for p_sig in m_obj.parameters:
                        type_part = p_sig.split()[0]; base_type = type_part.split('<')[0]
                        param_types.append(base_type)
                sig_key_part = f"({','.join(param_types)})"
                full_key = f"{m_obj.parent_component.fully_qualified_name}.{m_obj.name}{sig_key_part}"

                method_keys_map[i+1] = full_key # Store the constructed key
                # Display option
                comp_color = Colors.component_color(m_obj.parent_component.component_type)
                display_str = colored(full_key, comp_color)
                print(menu_option(i + 1, display_str))

            except Exception as e: # Handle errors reconstructing key/display for a single method
                logger.warning(f"Could not display option for method {m_obj}: {e}")
                print(menu_option(i + 1, colored(f"Error displaying option {i+1}", Colors.RED)))
                method_keys_map[i+1] = None # Mark as unusable

        print(menu_option(0, "Cancel Selection"))

        try:
            choice_str = input(colored("\nSelect number to analyze: ", Colors.BRIGHT_WHITE))
            choice = int(choice_str)
            if choice == 0: print(info("Selection cancelled.")); time.sleep(1); return
            if 0 < choice <= len(method_objects):
                selected_key = method_keys_map.get(choice)
                if selected_key:
                    self.analyze_method(selected_key) # Re-call analysis with the specific key
                else:
                    print(error("Cannot analyze method due to previous error.")); time.sleep(1.5)
            else: print(error("Invalid selection number.")); time.sleep(1)
        except ValueError: print(error("Invalid input. Please enter a number.")); time.sleep(1)


    def _print_flow_hierarchy(self, items, indent, child_key):
        # Generic function to print call/caller trees
        if not items: print(f"{indent}None found."); return

        # Use box drawing characters for tree structure
        connector = '├─ '
        last_connector = '└─ '
        vertical_pipe = '│  '
        space_indent = '   '

        num_items = len(items)
        for i, item in enumerate(items):
            is_last = (i == num_items - 1)
            current_connector = last_connector if is_last else connector

            # Extract display info safely using .get()
            method_str = item.get('method', 'Unknown Method')
            comp_name = item.get('component', 'Unknown Comp')
            comp_type = item.get('component_type', '')
            comp_color = Colors.component_color(comp_type)

            # Format the output line
            display_line = f"{indent}{current_connector}{colored(method_str, Colors.BRIGHT_GREEN)}"
            display_line += f" {colored(f'({comp_name})', comp_color)}"
            print(display_line)

            # Recursively print children/parents if they exist
            children_or_parents = item.get(child_key, [])
            if children_or_parents:
                next_indent = indent + (space_indent if is_last else vertical_pipe)
                self._print_flow_hierarchy(children_or_parents, next_indent, child_key) # Recursive call


    def file_git_operations_menu(self):
        while True:
            clear_screen(); print(menu_title("File / Git Operations Menu"));
            print(menu_option(1,"Convert Files/Directory to Text")); print(menu_option(2,"Browse Files Interactively")); print(menu_option(3,"Create Git Patch from Local Changes")); print(menu_option(0,"Back to Main Menu"))
            choice = input(colored("\nEnter choice: ", Colors.BRIGHT_WHITE)).strip()
            if choice == '0': break
            elif choice == '1': self.convert_files_menu()
            elif choice == '2':
                # Reuse interactive browser from explorer
                try: self.explorer.interactive_structure_browser()
                except Exception as e: logger.error("Error during interactive browsing", exc_info=True); print(error(f"Browser error: {e}")); time.sleep(2)
            elif choice == '3': self.create_patch_menu()
            else: print(error("Invalid choice.")); time.sleep(1)

    def convert_files_menu(self):
        clear_screen(); print(menu_title("Convert Files/Directory to Text"))
        print(info("Enter the index of a file or directory from the project structure."))
        print(info("You can find indices using the 'Project Structure' > 'View Full Tree' or 'Browse' options."))
        node_index = input(colored("Enter index: ", Colors.BRIGHT_WHITE)).strip()
        if not node_index: print(warning("No index entered.")); time.sleep(1); return

        target_dir = input(colored("Enter output directory path (leave blank to save '.txt' next to original): ", Colors.BRIGHT_WHITE)).strip()

        print(info(f"Attempting to convert node '{node_index}' to text..."))
        try:
            ok, msg = self.explorer.convert_files_to_txt(node_index, target_dir if target_dir else None)
            print(success(msg) if ok else error(f"Conversion failed:\n{msg}"))
        except Exception as e:
            logger.error(f"Error during file conversion UI for index {node_index}", exc_info=True)
            print(error(f"An unexpected error occurred during conversion: {e}"))
        input(colored("\nPress Enter to return...", Colors.BOLD))


    def create_patch_menu(self):
        clear_screen(); print(menu_title("Create Git Patch File"))
        print(info("This command creates a patch file (.patch) containing uncommitted local changes (diff against HEAD)."))
        print(info(f"Current Git repository: {self.explorer.project_path}"))

        # Check if it's actually a git repo before proceeding
        git_dir = os.path.join(self.explorer.project_path, '.git')
        if not os.path.isdir(git_dir):
            print(error("\nThe specified project path does not appear to be a Git repository. Cannot create patch."));
            input(colored("Press Enter to return...", Colors.BOLD)); return

        # Suggest a default filename
        default_filename = f"local_changes_{time.strftime('%Y%m%d_%H%M%S')}.patch"
        default_path_display = os.path.join("", default_filename) # Display relative default

        # Get output file path from user
        path_input = input(colored(f"Enter output patch file path [Default: {default_path_display}]: ", Colors.BRIGHT_WHITE)).strip()
        path_cleaned = path_input.strip('"').strip("'") # Remove potential quotes

        # Determine final output path
        output_file_path = ""
        if not path_cleaned:
            # Use default path relative to the project root
            output_file_path = os.path.join(self.explorer.project_path, default_filename)
            print(info(f"Using default output path: {output_file_path}"))
        else:
            # Check if user provided a directory or a full path
            path_abs = os.path.abspath(path_cleaned)
            if os.path.isdir(path_abs):
                # User provided a directory, save with default name inside it
                output_file_path = os.path.join(path_abs, default_filename)
                print(info(f"Output directory specified. Saving patch as: {output_file_path}"))
            else:
                # User provided a full path (or relative path to a file)
                output_file_path = path_abs # Use the absolute path

        # Ask about including binary changes
        include_binary_str = input(colored("Include binary file changes in patch? (y/N): ", Colors.BRIGHT_YELLOW)).strip().lower()
        include_binary = (include_binary_str == 'y')

        print(info("Creating patch file..."))
        try:
            ok, msg = self.explorer.create_patch_from_local_changes(output_file_path, include_binary)
            print(success(msg) if ok else error(f"Patch creation failed: {msg}"))
        except Exception as e:
            logger.error(f"Error during patch creation UI for output {output_file_path}", exc_info=True)
            print(error(f"An unexpected error occurred during patch creation: {e}"))

        input(colored("\nPress Enter to return...", Colors.BOLD))


    def settings_menu(self):
        while True:
            clear_screen(); print(menu_title("Settings & Debug Menu"));
            print(menu_option(1,"Clear Cache & Re-analyze Project")); print(menu_option(2,"Debug: Show Annotations & Component Types")); print(menu_option(3,"Debug: List Java Parsing Errors")); print(menu_option(0,"Back to Main Menu"))
            choice = input(colored("\nEnter choice: ", Colors.BRIGHT_WHITE)).strip()
            if choice == '0': break
            elif choice == '1':
                confirm = input(warning("This will delete the cache and force a full re-analysis. Are you sure? (y/N): ")).strip().lower()
                if confirm == 'y':
                    print(info("Clearing cache..."))
                    try:
                        ok, msg = self.explorer.clear_cache() # clear_cache now re-inits state internally
                        if ok:
                            print(success(msg))
                            print(info("Re-analyzing project... This may take a moment."))
                            self.explorer.analyze_project() # Trigger re-analysis
                            print(success("Re-analysis complete."))
                        else: print(error(msg)) # Show error from clear_cache
                    except Exception as e:
                        logger.error("Error during cache clear / re-analyze process", exc_info=True)
                        print(error(f"An error occurred: {e}"))
                else:
                    print(info("Cache clear cancelled."))
                input(colored("\nPress Enter to return...", Colors.BOLD))

            elif choice == '2': self.debug_annotations_menu()
            elif choice == '3': self.list_parsing_errors()
            else: print(error("Invalid choice.")); time.sleep(1)

    def debug_annotations_menu(self):
        clear_screen(); print(menu_title("Debug: Annotations & Component Types"))
        try:
            annotations_found, component_summary = self.explorer.debug_annotations()

            print(colored(f"--- Unique Annotations Found ({len(annotations_found)}) ---", Colors.BOLD))
            if annotations_found:
                max_annotations_to_show = 50
                for i, anno in enumerate(annotations_found):
                    if i >= max_annotations_to_show:
                        print(colored(f"  ... and {len(annotations_found) - max_annotations_to_show} more.", Colors.BRIGHT_BLACK))
                        break
                    print(f"  - {colored(anno, Colors.BRIGHT_YELLOW)}")
            else: print(info("  No annotations collected (or none found)."))


            print(colored(f"\n--- Component Type Summary ({len(component_summary)}) ---", Colors.BOLD))
            if component_summary:
                # Sort by type name for consistent display
                for comp_type, count in sorted(component_summary.items()):
                    type_color = Colors.component_color(comp_type) # Get color for the type
                    print(f"  - {colored(comp_type, type_color):<30}: {count} instance(s)") # Use color and padding
            else: print(info("  No component types summarized (or no components found)."))

        except Exception as e:
            logger.error("Error generating debug annotations/types summary", exc_info=True)
            print(error(f"Could not generate debug summary: {e}"))

        input(colored("\nPress Enter to return...", Colors.BOLD))


    def list_parsing_errors(self):
        clear_screen(); print(menu_title("Debug: Java Parsing Errors"))
        try:
            errors_list = self.explorer.get_parse_errors()
            if not errors_list:
                print(success("No Java parsing errors were recorded during the last analysis."))
            else:
                num_errors = len(errors_list)
                print(warning(f"{num_errors} file(s) encountered parsing errors:\n"))
                max_errors_to_show = 40
                for i, (file_path, error_msg) in enumerate(errors_list):
                    if i >= max_errors_to_show:
                        print(f"\n... and {num_errors - max_errors_to_show} more errors.")
                        break
                    try: # Try to get relative path
                        rel_path = os.path.relpath(file_path, self.explorer.project_path)
                    except ValueError: rel_path = file_path # Fallback

                    print(f"  File: {colored(rel_path, Colors.BRIGHT_RED)}")
                    print(f"    Error: {colored(error_msg, Colors.WHITE)}")
                    print("-" * 20) # Separator

        except Exception as e:
            logger.error("Error retrieving parsing errors", exc_info=True)
            print(error(f"Could not retrieve parsing errors: {e}"))

        input(colored("\nPress Enter to return...", Colors.BOLD))

# --- End Interactive CLI Class ---
