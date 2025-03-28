# spring_explorer/utils.py
import os
import sys
import logging

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SpringBootExplorer")
# --- End Logging Setup ---

# --- Color Class and Functions ---
class Colors:
    BLACK = '\033[30m'; RED = '\033[31m'; GREEN = '\033[32m'; YELLOW = '\033[33m'
    BLUE = '\033[34m'; MAGENTA = '\033[35m'; CYAN = '\033[36m'; WHITE = '\033[37m'
    BRIGHT_BLACK = '\033[90m'; BRIGHT_RED = '\033[91m'; BRIGHT_GREEN = '\033[92m'; BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'; BRIGHT_MAGENTA = '\033[95m'; BRIGHT_CYAN = '\033[96m'; BRIGHT_WHITE = '\033[97m'
    BG_BLACK = '\033[40m'; BG_RED = '\033[41m'; BG_GREEN = '\033[42m'; BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'; BG_MAGENTA = '\033[45m'; BG_CYAN = '\033[46m'; BG_WHITE = '\033[47m'
    BOLD = '\033[1m'; UNDERLINE = '\033[4m'; REVERSED = '\033[7m'; END = '\033[0m'

    @staticmethod
    def component_color(component_type):
        if not component_type: return Colors.WHITE
        ct = component_type.lower()
        color_map = {"controller": Colors.BRIGHT_BLUE, "service": Colors.BRIGHT_GREEN, "repository": Colors.BRIGHT_YELLOW,
                     "component": Colors.BRIGHT_CYAN, "configuration": Colors.BRIGHT_MAGENTA, "entity": Colors.YELLOW}
        for name, color in color_map.items():
            if name in ct: return color
        return Colors.WHITE

def supports_color():
    if os.environ.get('FORCE_COLOR', '').lower() in ('1', 'true', 'yes'): return True
    if 'NO_COLOR' in os.environ: return False
    if 'PYCHARM_HOSTED' in os.environ: return True
    if any(k in os.environ for k in ['TERM', 'COLORTERM']) and 'dumb' not in os.environ.get('TERM', ''): return True
    is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    if sys.platform != 'win32': return is_a_tty
    return is_a_tty or 'ANSICON' in os.environ

# IMPORTANT: This global needs to be potentially modified by __main__.py
USE_COLORS = supports_color()

def colored(text, color, end_color=Colors.END): return f"{color}{text}{end_color}" if USE_COLORS else text
def header(text): return colored(f" {text} ", Colors.WHITE+Colors.BG_BLUE+Colors.BOLD)
def menu_option(index, text): return f"{colored(str(index), Colors.BRIGHT_YELLOW)} - {colored(text, Colors.WHITE)}"
def menu_title(text):
    line = "─" * (len(text) + 4); return f"\n{colored(line, Colors.BRIGHT_BLUE)}\n{colored('┌', Colors.BRIGHT_BLUE)}{colored(f' {text} ', Colors.BOLD + Colors.BRIGHT_WHITE)}{colored('┐', Colors.BRIGHT_BLUE)}\n{colored(line, Colors.BRIGHT_BLUE)}" if USE_COLORS else f"\n=== {text} ==="
def success(text): return colored(text, Colors.BRIGHT_GREEN)
def error(text): return colored(text, Colors.BRIGHT_RED)
def info(text): return colored(text, Colors.BRIGHT_CYAN)
def warning(text): return colored(text, Colors.BRIGHT_YELLOW)
def clear_screen(): os.system('cls' if os.name == 'nt' else 'clear')
# --- End Color Functions ---
