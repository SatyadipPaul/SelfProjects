# spring_explorer/__main__.py
import argparse
import os
import sys
import shutil

# --- Local Imports ---
# Import necessary components from our package
from .cli import InteractiveSpringExplorer
# CORRECTED IMPORT LINE: Added 'success'
from .utils import logger, info, warning, error, success
# Import the utils module itself to modify its global USE_COLORS
import spring_explorer.utils as utils
# --- End Local Imports ---


# --- Main Function ---
def main():
    parser = argparse.ArgumentParser(
        description="Spring Boot Code Explorer - Analyze and browse Spring Boot projects.",
        epilog="Run without arguments in a project directory or specify path. Use --interactive (default) for CLI."
    )
    parser.add_argument(
        "project_path",
        nargs='?',
        default='.',
        help="Path to the Spring Boot project root directory (default: current directory)."
    )
    # --interactive is arguably the default, but keep flag for clarity maybe? Or remove.
    # parser.add_argument(
    #     "--interactive",
    #     action="store_true",
    #     help="Launch the interactive command-line interface (default behavior)."
    # )
    parser.add_argument(
        "--force-color",
        action="store_true",
        help="Force enable colored terminal output."
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore and clear any existing analysis cache on startup."
    )
    parser.add_argument(
        "--clear-cache-only",
        action="store_true",
        help="Only clear the cache for the project path and exit. Does not run analysis."
    )


    args = parser.parse_args()

    # --- Handle Color Override ---
    if args.force_color:
        print(info("Forcing color output ON."))
        utils.USE_COLORS = True # Modify the global in the imported utils module

    # --- Handle Cache Clearing ---
    project_abs_path = os.path.abspath(args.project_path)
    cache_dir = os.path.join(project_abs_path, ".explorer_cache")

    if args.clear_cache_only:
        if os.path.exists(cache_dir):
            try:
                print(info(f"Clearing cache directory: {cache_dir}"))
                shutil.rmtree(cache_dir)
                print(success("Cache cleared successfully."))
                return 0
            except Exception as e:
                print(error(f"Failed to clear cache directory: {e}"))
                return 1
        else:
            print(info("Cache directory not found, nothing to clear."))
            return 0

    if args.no_cache:
        if os.path.exists(cache_dir):
            try:
                print(info(f"Ignoring cache (--no-cache): Clearing existing cache at {cache_dir}"))
                shutil.rmtree(cache_dir)
            except Exception as e:
                print(warning(f"Could not clear existing cache directory (continuing without cache): {e}"))
        else:
            print(info("No existing cache found to clear (--no-cache)."))


    # --- Run the Explorer ---
    try:
        # Instantiate the CLI, which handles initialization and analysis
        explorer_cli = InteractiveSpringExplorer(project_abs_path)
        # Run the interactive loop
        explorer_cli.run()
        return 0 # Exit cleanly after CLI finishes
    except KeyboardInterrupt:
        print(info("\nOperation cancelled by user."))
        return 130 # Standard exit code for Ctrl+C
    except FileNotFoundError as e:
        # Error should be printed by InteractiveSpringExplorer __init__
        # print(error(f"Error: Project path not found - {e}")) # Redundant?
        return 1
    except ImportError as e:
        # Error should be printed by InteractiveSpringExplorer __init__ or module imports
        return 1
    except Exception as e:
        # Catch-all for unexpected critical errors during startup or run
        logger.critical(f"A critical error occurred: {e}", exc_info=True)
        print(error(f"A critical error occurred: {type(e).__name__} - {e}"))
        print(error("Please check logs for more details."))
        return 1

# --- Entry Point Check ---
if __name__ == "__main__":
    sys.exit(main())