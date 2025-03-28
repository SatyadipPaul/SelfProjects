# spring_explorer/explorer.py
import subprocess
import os
import sys
import pickle
import re
import time
import shutil
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Library Imports with Checks ---
try:
    import javalang
    # Import specific types needed for checks and processing
    from javalang.tree import (MethodInvocation, TypeDeclaration, ClassDeclaration,
                               InterfaceDeclaration, EnumDeclaration, AnnotationDeclaration,
                               BasicType, Statement, MethodDeclaration, ConstructorDeclaration)
    from javalang.tokenizer import LexerError
    from javalang.parser import JavaSyntaxError
except ImportError:
    print("ERROR: 'javalang' library not found. Please install it using: pip install javalang")
    sys.exit(1)
try:
    import networkx as nx
except ImportError:
    print("ERROR: 'networkx' library not found. Please install it using: pip install networkx")
    sys.exit(1)
# --- End Library Imports ---

# --- Local Imports ---
from .models import SpringBootComponent, Field, Method, MethodCallVisitor
from .utils import logger, Colors, colored # Import necessary items from utils
# --- End Local Imports ---


# --- Main Explorer Class ---
class SpringBootExplorer:
    SPRING_ANNOTATIONS = ["@Controller", "@RestController", "@Service", "@Repository", "@Component", "@Configuration", "@Bean", "@Entity", "@Autowired", "@ControllerAdvice", "@RestControllerAdvice", "@RequestMapping", "@GetMapping", "@PostMapping", "@PutMapping", "@DeleteMapping", "@ExceptionHandler", "@PathVariable", "@RequestParam", "@RequestBody", "@ResponseBody", "@Valid", "@Qualifier", "@Scope", "@Lazy", "@Conditional", "@Profile", "@Primary", "@Order"]
    IGNORED_DIRS = {".git", "target", "build", "node_modules", ".idea", ".gradle", ".settings", ".classpath", ".project", "__pycache__", ".DS_Store", ".explorer_cache", "dist", "out"}

    def __init__(self, project_path):
        self.project_path = os.path.abspath(project_path)
        self.components={}; self.methods={}; self.index_structure={}; self.call_graph=nx.DiGraph();
        self.string_index=defaultdict(list); self.package_structure=defaultdict(list); self.cache={}; self.parse_errors=[]
        self.cache_dir = os.path.join(self.project_path, ".explorer_cache")
        if not os.path.isdir(self.project_path): raise FileNotFoundError(f"Project path invalid: {self.project_path}")
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
            except Exception as e:
                logger.warning(f"Cache dir creation error: {e}")
        logger.info(f"Initialized SpringBootExplorer for: {self.project_path}")

    def analyze_project(self):
        logger.info("Starting project analysis..."); t_start=time.time()
        if self._load_from_cache():
             logger.info(f"Successfully loaded analysis results from cache in {time.time()-t_start:.2f}s"); return
        logger.info("Cache miss or invalid. Performing full analysis...");
        self._build_project_structure()
        self._parse_java_files()
        self._build_component_relationships()
        self._build_call_graph()
        self._build_string_index()
        self._save_to_cache()
        logger.info(f"Project analysis completed in {time.time()-t_start:.2f}s. Components: {len(self.components)}, Methods: {len(self.methods)}.")
        if self.parse_errors: logger.warning(f"Encountered {len(self.parse_errors)} parsing errors during analysis.")

    def _build_project_structure(self):
        logger.info("Building project file structure index..."); self.index_structure={"index":"0", "path":self.project_path, "name":os.path.basename(self.project_path), "type":"directory", "children":[]}
        self._traverse_directory(self.project_path, self.index_structure["children"], "")
        logger.info("Project structure index built.")

    def _traverse_directory(self, directory, children_list, parent_idx):
        try:
            items = sorted(os.listdir(directory))
        except Exception as e:
            logger.debug(f"Cannot list directory {directory}: {e}"); return
        # Skip ignored directories by basename
        if os.path.basename(directory) in self.IGNORED_DIRS or directory == self.cache_dir:
             logger.debug(f"Skipping ignored directory: {directory}")
             return

        for i, item in enumerate(items):
            path = os.path.join(directory, item); idx = f"{parent_idx}.{i+1}" if parent_idx else f"{i+1}"
            try:
                # Check if path exists and handle potential race conditions/errors
                if not os.path.exists(path): continue
                is_dir = os.path.isdir(path); is_file = os.path.isfile(path)
            except OSError as e:
                 logger.debug(f"OS error accessing {path}: {e}"); continue

            if is_dir:
                # Recurse into non-ignored directories
                if os.path.basename(path) not in self.IGNORED_DIRS and path != self.cache_dir:
                    entry={"index":idx,"path":path,"name":item,"type":"directory","children":[]}
                    children_list.append(entry)
                    self._traverse_directory(path, entry["children"], idx)
            elif is_file:
                 # Add file entry
                 children_list.append({"index":idx,"path":path,"name":item,"type":self._determine_file_type(item)})

    def _determine_file_type(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        types={'.java':'java','.properties':'config','.yml':'config','.yaml':'config','.xml':'xml','.html':'web','.css':'web','.js':'web','.jsp':'web','.ts':'web','.tsx':'web','.jsx':'web','.md':'doc','.txt':'doc','.png':'image','.jpg':'image','.jpeg':'image','.gif':'image','.svg':'image','.sql':'sql', '.gradle':'build', '.mvn':'build'} # Added build types
        return types.get(ext, 'other')

    def _parse_java_files(self):
        logger.info("Searching for Java files..."); files = self._find_files_by_type(self.index_structure, "java")
        if not files: logger.warning("No Java files found in the project structure."); return

        num_files = len(files)
        use_parallel = num_files > 50 # Threshold for parallel parsing
        parser = self._parse_java_files_parallel if use_parallel else self._parse_java_files_sequential
        logger.info(f"Starting parsing of {num_files} Java files ({'parallel' if use_parallel else 'sequential'})...")
        parser(files); logger.info("Java file parsing attempt finished.")

    def _parse_java_files_sequential(self, files):
        total = len(files)
        for i, f_info in enumerate(files):
            # Optional: Add progress logging for sequential
            # if (i + 1) % 100 == 0: logger.info(f"Parsing {i+1}/{total}...")
            try:
                self._parse_java_file(f_info["path"], f_info["index"])
            except Exception as e:
                # Catch unexpected errors during the parse call itself
                logger.error(f"Unhandled error during parsing of {f_info['path']}: {e}", exc_info=True)
                self.parse_errors.append((f_info['path'], f"Unhandled parsing exception: {e}"))

    def _parse_java_files_parallel(self, files):
        max_workers = min(12, (os.cpu_count() or 1) + 4) # Limit threads
        total = len(files)
        processed_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all parsing tasks
            future_to_file = {executor.submit(self._parse_java_file, f["path"], f["index"]): f for f in files}

            # Process results as they complete
            for future in as_completed(future_to_file):
                f_info = future_to_file[future]
                processed_count += 1
                try:
                    future.result() # Raise exceptions from the thread, if any
                except Exception as e:
                     # Catch errors raised from within _parse_java_file in the thread
                     logger.error(f"Error processing file {f_info['path']} in thread: {e}", exc_info=False) # Keep log cleaner
                     # Error might have already been added in _parse_java_file, but add generic one if not
                     if not any(err[0] == f_info['path'] for err in self.parse_errors):
                          self.parse_errors.append((f_info['path'], f"Parallel processing error: {e}"))
                # Optional: Progress logging for parallel
                # if processed_count % 100 == 0: logger.info(f"Parsed {processed_count}/{total} files...")


    def _find_files_by_type(self, node, file_type):
        results = [];
        if node is None: return results # Safety check

        if node.get("type") == file_type and 'path' in node: # Ensure it's the right type and has a path
             results.append(node)

        # Recursively search children if they exist
        for child in node.get("children", []) or []: # Safe iteration
             if child: # Ensure child is not None
                 results.extend(self._find_files_by_type(child, file_type))
        return results

    def _parse_java_file(self, file_path, index):
        content = None; encodings = ['utf-8', 'latin-1', 'cp1252']
        read_success = False
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f: content = f.read(); read_success = True; break
            except UnicodeDecodeError: continue # Try next encoding
            except FileNotFoundError: logger.warning(f"File not found during parsing: {file_path}"); self.parse_errors.append((file_path, "File not found")); return
            except Exception as e: logger.warning(f"Error reading {file_path} with encoding {enc}: {e}"); self.parse_errors.append((file_path, f"Read error ({enc}): {e}")); return # Stop trying encodings on error
        if not read_success: logger.warning(f"Could not read file {file_path} with tested encodings."); self.parse_errors.append((file_path,"Read encoding error")); return

        try:
            tree = javalang.parse.parse(content)
            # SAFE: Check package exists before accessing name
            pkg_name = tree.package.name if tree.package and hasattr(tree.package, 'name') else ""
            # SAFE: Ensure imports is iterable
            imports_list = [imp.path for imp in tree.imports or [] if imp and hasattr(imp, 'path')]

            # Process top-level type declarations using safe iteration
            for path, node in tree.filter(TypeDeclaration):
                 # SAFE: Check node is not None
                 if node is None: continue
                 # SAFE: Ensure path is iterable (though filter usually yields tuples)
                 if not isinstance(path, (list, tuple)): path = []

                 # Check if it's a top-level declaration (not nested within another TypeDeclaration)
                 if not any(isinstance(p, TypeDeclaration) for p in path):
                     self._process_type_declaration(node, pkg_name, imports_list, content, file_path, index)

        except (LexerError, JavaSyntaxError, IndexError, TypeError, AttributeError, RecursionError) as e:
            line = e.pos.line if hasattr(e,'pos') and e.pos else '?'; err_type=type(e).__name__
            # Use the full exception string representation for potentially more detail
            full_error_str = str(e)
            # Log the full error string along with the type and location
            logger.warning(f"Parsing failed for {os.path.basename(file_path)} - {err_type} at L{line}: {full_error_str}")
            # Store a concise version or the full string - your choice
            self.parse_errors.append((file_path, f"{err_type} at L{line}: {full_error_str[:150]}")) # Limit stored length
        except Exception as e:
            # Catch any other unexpected errors during parsing itself
            logger.error(f"Unexpected parsing error in {file_path}: {type(e).__name__}-{e}", exc_info=False)
            self.parse_errors.append((file_path, f"Unexpected parsing error: {type(e).__name__}-{e}"))


    def _process_type_declaration(self, node, context_name, imports, content, file_path, index):
        # SAFE: Check if node is None before accessing attributes
        if node is None:
             logger.warning(f"Skipping None node in _process_type_declaration for {file_path}")
             return

        name = node.name if hasattr(node, 'name') else 'UnnamedType'
        # Determine Fully Qualified Name (FQN)
        fqn_base = f"{context_name}.{name}" if context_name else name
        fqn = f"{context_name}${name}" if '$' in context_name else fqn_base # Simple inner class check

        comp_type = self._determine_component_type(node)
        # SAFE: Add 'or []' and check annotation name exists
        annos = [f"@{a.name}" for a in getattr(node, 'annotations', []) or [] if hasattr(a, 'name')]
        comp = SpringBootComponent(name, file_path, comp_type, index)
        comp.imports=imports; comp.annotations=annos; comp.package=context_name.split('$')[0] if '$' in context_name else context_name; comp.fully_qualified_name=fqn
        # SAFE: Add 'or []' and check type parameter name
        comp.generics=[p.name for p in getattr(node,'type_parameters', []) or [] if hasattr(p, 'name')];

        ext = getattr(node,'extends',None); imp = getattr(node,'implements',None)

        # SAFE: Process extends/implements only if they exist and are not None
        if ext:
            ext_list = ext if isinstance(ext, list) else ([ext] if ext else [])
            comp.extends = [self._format_type(e) for e in ext_list if e] # Filter None elements
        if imp:
            imp_list = imp if isinstance(imp, list) else ([imp] if imp else [])
            comp.implements = [self._format_type(i) for i in imp_list if i] # Filter None elements

        # SAFE: Use 'or []' and check elements when processing fields, methods, constructors
        if hasattr(node,'fields'): [self._process_field(f, comp) for f in node.fields or [] if f]
        if hasattr(node,'methods'): [self._process_method(m, comp, content) for m in node.methods or [] if m]
        if hasattr(node,'constructors'): [self._process_constructor(c, comp, content) for c in node.constructors or [] if c]

        # Store/Update component
        self.components[fqn] = comp
        if '.' in fqn and '$' not in fqn: # Add top-level FQN to package structure
            pkg_name = '.'.join(fqn.split('.')[:-1])
            # Ensure package_structure entry is a list
            if not isinstance(self.package_structure.get(pkg_name), list):
                 self.package_structure[pkg_name] = []
            if fqn not in self.package_structure[pkg_name]:
                 self.package_structure[pkg_name].append(fqn)

        # Recurse for inner types
        if hasattr(node, 'body'):
            # SAFE: Add 'or []' when iterating through body members
            inner_type_decls = [m for m in node.body or [] if isinstance(m, TypeDeclaration)]
            for idx, member in enumerate(inner_type_decls):
                 if member: # SAFE: Check member is not None before recursing
                     self._process_type_declaration(member, fqn, imports, content, file_path, f"{index}.i{idx+1}") # Use current FQN as context


    def _determine_component_type(self, node):
        # SAFE: Check node before type check
        if node is None: return "Unknown"
        # Use specific javalang types for clarity
        type_map = {ClassDeclaration:"Class", InterfaceDeclaration:"Interface", EnumDeclaration:"Enum", AnnotationDeclaration:"Annotation"}
        comp_type = type_map.get(type(node), "Unknown")

        # Check annotations for Spring stereotypes
        # SAFE: Use getattr with default and 'or []' for annotations
        for anno in getattr(node, 'annotations', []) or []:
             # SAFE: Check anno and anno.name exist
             if anno and hasattr(anno, 'name') and anno.name:
                 anno_name_lower = anno.name.lower()
                 for sa in self.SPRING_ANNOTATIONS:
                     if anno_name_lower == sa[1:].lower(): # Compare lowercase annotation name
                         return sa[1:] # Return canonical Spring name (e.g., "Service")
        return comp_type


    def _format_type(self, node):
        if node is None: return "void"

        # Handle lists (potentially representing arrays in some javalang versions/contexts)
        if isinstance(node, list):
             # SAFE: Ensure node[0] exists if node is a list, provide fallback
             first_element = self._format_type(node[0]) if node else "<?>"
             # SAFE: Check dimensions exist and are iterable
             dims_list = getattr(node, 'dimensions', []) or [] # Assume dimensions attr if list represents array node
             return first_element + ('[]' * len(dims_list))

        # Handle javalang type nodes
        name = getattr(node,'name',None)
        if name:
            base=name; sub=getattr(node,'sub_type',None); args=getattr(node,'arguments',None); dims=getattr(node,'dimensions',None)
            if sub: base += '.'+self._format_type(sub) # Recursive call
            # SAFE: Add 'or []' for arguments and check argument 'a'
            if args: base += f"<{','.join([(self._format_type(a.type) if hasattr(a,'type') and a.type else (self._format_type(a.pattern_type) if hasattr(a,'pattern_type') else (getattr(a,'name','?') or '?'))) for a in args or [] if a])}>"
            # SAFE: Add 'or []' for dimensions
            if dims: base += '[]'*len(dims or [])
            return base

        # Check for basic types like 'int', 'float' etc.
        if isinstance(node, BasicType):
            return node.name # BasicType has a 'name' attribute

        # Fallback for primitives represented as strings, or other unexpected node types
        return getattr(node,'value',str(node))


    def _process_field(self, node, comp):
        # SAFE: Check node is not None
        if node is None: return
        type_s=self._format_type(node.type) # Format the base type
        # SAFE: Use 'or []' for modifiers and annotations, check annotation name
        mods=list(node.modifiers or [])
        annos=[f"@{a.name}" for a in node.annotations or [] if hasattr(a, 'name')]

        # SAFE: Use 'or []' for declarators and check declarator 'decl'
        for decl in node.declarators or []:
            if decl is None: continue
            name=decl.name
            # SAFE: Check dimensions exist and are iterable before len()
            dims = decl.dimensions or []
            type_f=type_s+('[]'*len(dims)) # Append array dimensions if any
            field=Field(name,type_f,mods,comp); field.annotations=annos
            # SAFE: Ensure fields dict exists
            if comp.fields is None: comp.fields = {}
            comp.fields[name]=field


    def _extract_source_lines(self, node, source_code):
        lines=source_code.splitlines(); start, end = -1,-1
        # SAFE: Check node exists before accessing position
        if node and hasattr(node,'position') and node.position:
             start=node.position.line
        else:
             return [],"",-1,-1 # Cannot determine lines without position

        if start > 0:
            level, idx, found_start, end_line_calc = 0, start - 1, False, start
            while idx < len(lines):
                line = lines[idx]; open_b = line.count('{'); close_b = line.count('}')
                if not found_start:
                    # Find the line where the body likely starts (contains '{')
                    if '{' in line: found_start = True; level += open_b - close_b
                    # Heuristic: Give up if no '{' found within reasonable range
                    elif idx > start + 10: break
                else: level += open_b - close_b

                # Check if braces balance out *after* processing the current line
                # Requires careful handling of single-line methods/blocks
                if found_start and level <= 0 and (open_b > 0 or close_b > 0):
                    if level == 0 and open_b > 0 and idx == start -1 and '}' in line: # Single line {}
                        end_line_calc = idx + 1
                    elif level <= 0:
                         end_line_calc = idx + 1
                    break # Found the end

                idx += 1
                # Safety break for extremely long methods or runaway parsing
                if idx > start + 2000: logger.warning(f"Potential runaway brace count near L{start} in {getattr(node,'name','?')}, stopping search."); end_line_calc=start+20; break

            end = end_line_calc # Assign calculated end line

        # Validate calculated start/end lines
        if start > 0 and end >= start and end <= len(lines) + 1:
            # Ensure indices are within bounds for slicing
            start_idx = max(0, start - 1)
            end_idx = min(end, len(lines)) # Slice up to end_idx
            if start_idx < end_idx: # Ensure valid slice range
                extracted_lines = lines[start_idx:end_idx]
                return extracted_lines, "\n".join(extracted_lines), start, end_idx # Return calculated end line num
            else: # Handle cases where start/end are same or invalid range
                 return [], "", start, start # Return start line num, empty content

        return [],"",-1,-1 # Return default if lines couldn't be extracted


    def _process_method(self, node, comp, content):
        # SAFE: Check node is not None
        if node is None: return
        name=node.name if hasattr(node, 'name') else 'UnnamedMethod'
        params, types=[],[]
        # SAFE: Use 'or []' for parameters and check parameter 'p'
        for p in node.parameters or []:
             if p is None: continue
             param_type_str = self._format_type(p.type)
             param_name = p.name or '?' # Handle unnamed parameters
             varargs_suffix = '...' if p.varargs else ''
             params.append(f"{param_type_str}{varargs_suffix} {param_name}")
             types.append(f"{param_type_str}{varargs_suffix}")

        sig_disp=f"({', '.join(params)})"; sig_key=f"({','.join(types)})"
        lines, _, start, end = self._extract_source_lines(node, content)

        m = Method(name, sig_disp, "", comp) # Body not stored directly
        # SAFE: Use 'or []' for modifiers, annotations, throws
        m.modifiers=list(node.modifiers or [])
        m.return_type=self._format_type(node.return_type) or "void"
        m.parameters=params; m.source_lines=lines; m.start_line=start; m.end_line=end
        m.annotations=[f"@{a.name}" for a in node.annotations or [] if hasattr(a, 'name')]
        m.exceptions=[self._format_type(e) for e in node.throws or [] if e] # Check 'e'

        # SAFE: Check body exists and iterate safely
        if hasattr(node, 'body') and node.body:
            visitor=MethodCallVisitor(m)
            try:
                body_content = node.body or [] # Default to empty list if body is None
                if isinstance(body_content, list):
                     # Iterate over statements safely
                     for stmt in body_content:
                         if stmt: visitor.visit(stmt) # Check stmt is not None
                elif body_content: # If body is a single node (e.g., lambda)
                    visitor.visit(body_content)
            except Exception as e: logger.warning(f"Visitor error processing body of {comp.name}.{name}: {e}")
            m.method_invocations = visitor.method_invocations

        key = f"{comp.fully_qualified_name}.{name}{sig_key}";
        # SAFE: Ensure methods dict exists
        if self.methods is None: self.methods = {}
        if comp.methods is None: comp.methods = {}
        self.methods[key]=m; comp.methods[f"{name}{sig_disp}"]=m


    def _process_constructor(self, node, comp, content):
        # SAFE: Check node is not None
        if node is None: return
        name="<init>"; disp_name=comp.name if hasattr(comp, 'name') else 'UnnamedClass'
        params, types=[],[]
        # SAFE: Use 'or []' for parameters and check 'p'
        for p in node.parameters or []:
             if p is None: continue
             param_type_str = self._format_type(p.type)
             param_name = p.name or '?'
             varargs_suffix = '...' if p.varargs else ''
             params.append(f"{param_type_str}{varargs_suffix} {param_name}")
             types.append(f"{param_type_str}{varargs_suffix}")

        sig_disp=f"({', '.join(params)})"; sig_key=f"({','.join(types)})"
        lines, _, start, end = self._extract_source_lines(node, content)
        # Use Method class to store constructor info, name is '<init>'
        c = Method(name, sig_disp, "", comp)
        # SAFE: Use 'or []' for modifiers, annotations, throws
        c.modifiers=list(node.modifiers or [])
        c.parameters=params
        c.source_lines=lines; c.start_line=start; c.end_line=end
        c.annotations=[f"@{a.name}" for a in node.annotations or [] if hasattr(a, 'name')]
        c.exceptions=[self._format_type(e) for e in node.throws or [] if e];
        c.return_type=disp_name # Constructor returns instance of the class

        # SAFE: Check body exists and iterate safely
        if hasattr(node, 'body') and node.body:
            visitor=MethodCallVisitor(c)
            try:
                body_content = node.body or []
                if isinstance(body_content, list):
                    for stmt in body_content:
                         if stmt: visitor.visit(stmt)
                elif body_content:
                    visitor.visit(body_content)
            except Exception as e: logger.warning(f"Visitor error processing constructor body {disp_name}: {e}")
            c.method_invocations = visitor.method_invocations

        key = f"{comp.fully_qualified_name}.{name}{sig_key}";
        # SAFE: Ensure methods dict exists
        if self.methods is None: self.methods = {}
        if comp.methods is None: comp.methods = {}
        self.methods[key]=c; comp.methods[f"{disp_name}{sig_disp}"]=c # Use ClassName(params) for key in component


    def _build_component_relationships(self):
        logger.info("Building component inheritance/implementation relationships...")
        for comp in self.components.values():
            try:
                # SAFE: Handle extends (check if list/str and not None)
                if comp.extends:
                     ext_list = comp.extends if isinstance(comp.extends, list) else [comp.extends]
                     # Filter out None before resolving, store resolved names
                     comp.extends = [self._resolve_type_name(e, comp) for e in ext_list if e]

                # SAFE: Handle implements (check if list and not None)
                if comp.implements:
                     impl_list = comp.implements if isinstance(comp.implements, list) else [comp.implements]
                     # Filter out None before resolving, store resolved names
                     comp.implements = [self._resolve_type_name(i, comp) for i in impl_list if i]

            except Exception as e: logger.error(f"Error building relationships for component {comp.fully_qualified_name}: {e}")


    def _resolve_type_name(self, type_name, context_comp):
        # Resolves a simple type name (like 'String', 'MyInnerClass', 'List') to a fully qualified name
        # based on imports, package context, and outer classes.
        if not isinstance(type_name, str): return str(type_name) # Handle non-string input

        # Split base type from generic arguments (e.g., "List<String>" -> "List", "<String>")
        base_name = type_name.split('<',1)[0]
        generic_part = type_name[len(base_name):] if '<' in type_name else ""

        # 1. Already Fully Qualified?
        if "." in base_name: return type_name # Assume it's already qualified

        # 2. Inner Class Resolution (Check current and outer scopes)
        current_scope_comp = context_comp
        while current_scope_comp:
            # Check for Outer$Inner format
            potential_inner_fqn = f"{current_scope_comp.fully_qualified_name}${base_name}"
            if potential_inner_fqn in self.components:
                return potential_inner_fqn + generic_part

            # Move to outer scope if current is an inner class
            if '$' in current_scope_comp.fully_qualified_name:
                 outer_fqn = '$'.join(current_scope_comp.fully_qualified_name.split('$')[:-1])
                 current_scope_comp = self.components.get(outer_fqn) # Get outer component object
            else:
                 current_scope_comp = None # Reached top-level

        # 3. Direct Import Match (e.g., import com.example.MyClass;)
        # SAFE: Iterate over imports safely
        for imp in context_comp.imports or []:
            if imp and imp.endswith(f".{base_name}"):
                return imp + generic_part

        # 4. Same Package Match (e.g., class MyClass calling OtherClass in same package)
        if context_comp.package:
            potential_pkg_fqn = f"{context_comp.package}.{base_name}"
            if potential_pkg_fqn in self.components:
                return potential_pkg_fqn + generic_part

        # 5. Wildcard Import Match (e.g., import java.util.*; calling List)
        # SAFE: Iterate over imports safely
        for imp in context_comp.imports or []:
            if imp and imp.endswith(".*"):
                package_prefix = imp[:-1] # Remove '*'
                potential_wild_fqn = f"{package_prefix}{base_name}" # Note: package usually ends with '.'
                if potential_wild_fqn in self.components:
                    return potential_wild_fqn + generic_part
                # Heuristic: Assume common wildcard imports resolve (can be inaccurate)
                # Be cautious with this, might lead to incorrect graph edges
                # if package_prefix in ["java.util.", "java.io.", "java.net.", "java.sql.", "javax.sql.", "java.time."]:
                #      return potential_wild_fqn + generic_part

        # 6. java.lang Implicit Import (String, Object, Integer, etc.)
        java_lang_types = {"String","Object","Integer","Boolean","Long","Double","Float","Character","Byte","Short","Void","Class","System","Math","Thread","Runnable","Exception","RuntimeException","Error","Throwable","Override","Deprecated","SuppressWarnings"}
        if base_name in java_lang_types:
             return f"java.lang.{base_name}" + generic_part

        # 7. Common java.util types (often used without explicit wildcard import in sample code)
        java_util_types = {"List","Map","Set","Collection","Optional", "ArrayList", "HashMap", "HashSet"}
        if base_name in java_util_types:
            return f"java.util.{base_name}" + generic_part


        # 8. Unresolved - Return original name (maybe it's a primitive type or truly unresolved)
        # logger.debug(f"Could not resolve type '{type_name}' in context {context_comp.fully_qualified_name}")
        return type_name


    def _build_call_graph(self):
        logger.info("Building method call graph..."); self.call_graph = nx.DiGraph(); [self.call_graph.add_node(k) for k in self.methods]
        total_invocations, resolved_invocations = 0, 0
        for method_key, method_obj in self.methods.items():
            # SAFE: Ensure method_invocations is iterable, default to empty list
            invocations = method_obj.method_invocations or []
            total_invocations += len(invocations)

            for inv in invocations:
                # SAFE: Skip if invocation object is None
                if inv is None: continue
                try:
                    # Ensure inv is a MethodInvocation node before proceeding
                    if isinstance(inv, MethodInvocation):
                        target_method_keys = self._resolve_method_invocation(inv, method_obj.parent_component, method_obj)

                        # SAFE: Ensure targets is iterable before checking/looping
                        if target_method_keys:
                             resolved_invocations += len(target_method_keys)
                             for target_key in target_method_keys or []: # Add 'or []'
                                 # Add edge if target exists in graph and edge doesn't already exist
                                 if target_key in self.call_graph and not self.call_graph.has_edge(method_key, target_key):
                                     self.call_graph.add_edge(method_key, target_key)
                                     # Update Method.calls list (caller side)
                                     target_method_obj = self.methods.get(target_key)
                                     if target_method_obj: # Ensure target object exists
                                          # SAFE: Initialize calls list if None
                                          if method_obj.calls is None: method_obj.calls = []
                                          if target_method_obj not in method_obj.calls:
                                               method_obj.calls.append(target_method_obj)
                                          # Update Method.called_by list (callee side)
                                          if target_method_obj.called_by is None: target_method_obj.called_by = []
                                          if method_obj not in target_method_obj.called_by:
                                               target_method_obj.called_by.append(method_obj)
                    else:
                         # Log if item in list is not a MethodInvocation
                         logger.debug(f"Skipping non-MethodInvocation item in {method_key}: {type(inv)}")

                except Exception as e:
                    # Log errors during resolution for a specific invocation
                    member_name = getattr(inv, 'member', '?') if hasattr(inv, 'member') else '?'
                    logger.debug(f"Error resolving invocation '{member_name}' in {method_key}: {e}", exc_info=False) # Limit traceback noise

        edge_count = self.call_graph.number_of_edges()
        node_count = self.call_graph.number_of_nodes()
        logger.info(f"Call graph built: {node_count} nodes, {edge_count} edges. Processed ~{total_invocations} potential invocations, resolved ~{resolved_invocations} calls.")


    def _resolve_method_invocation(self, inv, context_comp, context_method):
        # Resolves a MethodInvocation node to a list of potential target method keys (FQNs with signatures)
        if not isinstance(inv, MethodInvocation):
             logger.warning(f"Attempted to resolve non-MethodInvocation: {type(inv)}")
             return []

        method_name = inv.member # Name of the method being called
        qualifier_node = inv.qualifier # Node representing the object/class the method is called on (e.g., variable, 'this', 'super', ClassName)
        target_fqn = None # Fully qualified name of the class containing the target method

        if qualifier_node:
            qualifier_str = str(qualifier_node) # String representation for simple checks/lookups

            if qualifier_str == 'this': target_fqn = context_comp.fully_qualified_name
            elif qualifier_str == 'super':
                 # Determine superclass FQN
                 super_type = None
                 # SAFE: Check extends exists and is not None before accessing
                 extends_val = context_comp.extends or [] # Default to empty list
                 if extends_val:
                     # Assuming comp.extends contains resolved FQNs from _build_component_relationships
                     first_super_fqn = extends_val[0] if isinstance(extends_val, list) else extends_val
                     super_type = first_super_fqn # Use the resolved FQN
                 target_fqn = super_type if super_type else "java.lang.Object" # Default to Object if no superclass found/resolved

            else: # Qualifier is a variable, field, parameter, or class name
                resolved_qualifier_type_fqn = None

                # 1. Check Fields
                # SAFE: Use safe dict access
                field_obj = (context_comp.fields or {}).get(qualifier_str)
                if field_obj:
                    # Field type might be simple, needs resolving
                    resolved_qualifier_type_fqn = self._resolve_type_name(field_obj.field_type.split('<')[0], context_comp)

                # 2. Check Method Parameters (if field not found)
                if not resolved_qualifier_type_fqn and context_method and hasattr(context_method, 'parameters'):
                    # SAFE: Use 'or []'
                    for p_sig in context_method.parameters or []:
                         if not p_sig: continue
                         parts = p_sig.split()
                         # Check if parameter name matches qualifier
                         if len(parts) > 1 and parts[-1] == qualifier_str:
                             param_type_name = parts[0].split('<')[0] # Base type of parameter
                             resolved_qualifier_type_fqn = self._resolve_type_name(param_type_name, context_comp)
                             break # Found matching parameter

                # 3. Local Variable Resolution (Skipped - too complex for static analysis)
                # We assume if it's not a field or parameter, it might be a static call on a class

                # 4. Assume Static Call (if not resolved as field/param type)
                if not resolved_qualifier_type_fqn:
                    # Try resolving the qualifier string itself as a type name
                    resolved_as_type = self._resolve_type_name(qualifier_str, context_comp)
                    # Check if resolution was successful (different from input or contains '.')
                    # This indicates it's likely a class name (either ours or JDK)
                    if resolved_as_type != qualifier_str or '.' in resolved_as_type:
                        resolved_qualifier_type_fqn = resolved_as_type

                target_fqn = resolved_qualifier_type_fqn # Target is the class identified

        else: # No qualifier - method call on 'this' (implicitly)
            target_fqn = context_comp.fully_qualified_name

        # If we determined a target class FQN, find the method in its hierarchy
        if target_fqn:
            return self._find_method_in_hierarchy(target_fqn, method_name, inv)
        else:
             # Log if we couldn't figure out the target class
             logger.debug(f"Could not determine target class FQN for invocation '{method_name}' in {context_method}")
             return []


    def _find_method_in_hierarchy(self, start_fqn, method_name, invocation_node):
        # Finds potential method keys matching name and arg count up the hierarchy
        matches = set()
        queue = [start_fqn] # Start BFS from the initial target FQN
        visited = set()

        # SAFE: Default arg_c to -1 if arguments is None or not present
        arg_count = len(invocation_node.arguments) if invocation_node and hasattr(invocation_node,'arguments') and invocation_node.arguments is not None else -1

        while queue:
            current_fqn = queue.pop(0)
            if not current_fqn or current_fqn in visited: continue # Skip if None, empty, or already visited
            visited.add(current_fqn)

            # --- Check Methods in current_fqn ---
            # Optimization: Iterate only potentially matching keys
            prefix = f"{current_fqn}.{method_name}("
            possible_keys = [k for k in self.methods if k.startswith(prefix)]

            for method_key in possible_keys:
                 method_obj = self.methods[method_key]
                 # Double check name (should match due to prefix)
                 if method_obj.name == method_name:
                     # SAFE: Check parameters exists and is iterable before len()
                     num_params = len(method_obj.parameters or [])
                     # Match if arg count unknown (-1) or matches exactly
                     if arg_count == -1 or num_params == arg_count:
                         matches.add(method_key)
                     # else: Arg count mismatch

            # --- Add Superclasses and Interfaces to Queue ---
            current_comp = self.components.get(current_fqn)
            if current_comp:
                supertypes_to_check = []
                # SAFE: Use 'or []' for extends and implements, ensure they contain strings
                extends_list = (current_comp.extends if isinstance(current_comp.extends, list) else ([current_comp.extends] if current_comp.extends else []))
                implements_list = current_comp.implements or []

                # Add resolved FQNs from extends/implements (assuming they were resolved earlier)
                supertypes_to_check.extend(e for e in extends_list if isinstance(e, str))
                supertypes_to_check.extend(i for i in implements_list if isinstance(i, str))

                for supertype_fqn in supertypes_to_check:
                     if supertype_fqn and supertype_fqn not in visited:
                         queue.append(supertype_fqn)

            # Handle java.lang.Object implicitly if needed
            # If current_fqn is a known class (not Object) and we haven't found matches yet
            elif current_fqn and not current_fqn.startswith("java.") and not matches:
                 if "java.lang.Object" not in visited:
                      queue.append("java.lang.Object")
            elif current_fqn and current_fqn.startswith("java.") and current_fqn != "java.lang.Object" and not matches:
                 if "java.lang.Object" not in visited: # Ensure Object is added if hierarchy search stops at JDK class
                     queue.append("java.lang.Object")


        # Special check for common java.lang.Object methods if no matches found yet
        # This relies on knowing standard signatures.
        if not matches and "java.lang.Object" in visited: # Only check if Object was potentially searched
            obj_methods = {
                ("equals", 1): "java.lang.Object.equals(java.lang.Object)",
                ("hashCode", 0): "java.lang.Object.hashCode()",
                ("toString", 0): "java.lang.Object.toString()",
                ("getClass", 0): "java.lang.Object.getClass()",
                # notify, notifyAll, wait have different signatures, handle if needed
            }
            lookup_key = (method_name, arg_count)
            if lookup_key in obj_methods:
                 potential_obj_key = obj_methods[lookup_key]
                 # Check if we actually have this Object method key (unlikely unless pre-populated)
                 if potential_obj_key in self.methods:
                      matches.add(potential_obj_key)

        return list(matches)


    def _build_string_index(self):
        logger.info("Building string and identifier index..."); self.string_index = defaultdict(list)
        # Regex for Java identifiers (allows Unicode chars common in some languages)
        identifier_regex = re.compile(r'\b[a-zA-Z_\u00C0-\u00FF][a-zA-Z0-9_\u00C0-\u00FF]*\b')
        # Regex for standard Java string literals (handles basic escapes)
        string_literal_regex = re.compile(r'"((?:\\.|[^"\\])*)"')
        # Simple regex for potential properties/YAML keys (may need refinement)
        # property_key_regex = re.compile(r'^\s*([a-zA-Z0-9.-]+)\s*[:=]')

        for fqn, comp in self.components.items():
            content = ""; file_path = comp.file_path
            try: # Read file content (similar logic as in _parse_java_file)
                read_ok = False
                for enc in ['utf-8', 'latin-1', 'cp1252']:
                    try:
                         with open(file_path,'r',encoding=enc) as f: content=f.read(); read_ok=True; break
                    except UnicodeDecodeError: continue
                    except Exception: break # Stop on other read errors
                if not read_ok: logger.warning(f"Index build: Could not read {file_path}"); continue
            except Exception as e: logger.warning(f"Index build: Failed reading {file_path}: {e}"); continue

            try: # Process content for indexing
                # Index identifiers
                words = set(identifier_regex.findall(content))
                # Filter out very short words, pure numbers, and maybe keywords later
                for w in words:
                     if len(w)>2 and not w.isdigit():
                          self.string_index[w.lower()].append({'fqn':fqn,'path':file_path,'original':w, 'type':'identifier'})

                # Index string literals
                literals = string_literal_regex.findall(content)
                for lit in literals:
                     if len(lit)>1: # Ignore empty strings ""
                          self.string_index[lit.lower()].append({'fqn':fqn,'path':file_path,'original':lit, 'type':'literal'})

                # Consider adding indexing for comments or properties if needed
                # for line in content.splitlines():
                #      prop_match = property_key_regex.match(line)
                #      if prop_match:
                #           key = prop_match.group(1)
                #           if len(key)>2:
                #                self.string_index[key.lower()].append({'fqn': fqn, 'path': file_path, 'original': key, 'type': 'property'})


            except Exception as e: logger.error(f"Error during regex indexing for {file_path}: {e}")
        logger.info(f"String/Identifier index built with {len(self.string_index)} unique terms.")


    # --- Caching Logic ---

    def _get_cache_key(self, path):
        try:
            return f"{path}:{os.path.getmtime(path)}"
        except OSError: # Handle file not found during key generation
            return f"{path}:error_or_missing"

    def _save_to_cache(self):
        if not os.path.isdir(self.project_path): logger.error("Project path is invalid, cannot save cache."); return
        cache_file = os.path.join(self.cache_dir, "explorer_cache.pkl"); logger.info(f"Saving analysis cache to: {cache_file}")

        # Ensure cache directory exists
        if not os.path.exists(self.cache_dir):
            try: os.makedirs(self.cache_dir)
            except Exception as e: logger.error(f"Cannot create cache directory '{self.cache_dir}': {e}"); return

        # Prepare data for pickling (convert objects to dicts)
        components_serializable = {}
        for k, v in self.components.items():
            try: components_serializable[k] = v.to_dict()
            except Exception as e: logger.error(f"Error serializing component {k} for cache: {e}")

        methods_serializable = {}
        for k, v in self.methods.items():
             try: methods_serializable[k] = v.to_dict()
             except Exception as e: logger.error(f"Error serializing method {k} for cache: {e}")

        cache_data = {
            'project_path': self.project_path,
            'timestamp': time.time(),
            'components': components_serializable,
            'methods': methods_serializable,
            'index_structure': self.index_structure,
            'package_structure': dict(self.package_structure), # Convert defaultdict
            'string_index': {k: list(v) for k, v in self.string_index.items()}, # Convert defaultdict values
            'call_graph_edges': list(self.call_graph.edges()) if self.call_graph else [],
            'parse_errors': self.parse_errors
        }
        try:
            with open(cache_file, 'wb') as f: pickle.dump(cache_data, f, pickle.HIGHEST_PROTOCOL)
            logger.info("Analysis cache saved successfully.")
        except Exception as e: logger.error(f"Failed to save cache file '{cache_file}': {e}")


    def _load_from_cache(self):
        cache_file = os.path.join(self.cache_dir, "explorer_cache.pkl")
        if not os.path.isfile(cache_file): logger.info("Cache file not found."); return False
        logger.info(f"Attempting to load analysis cache from: {cache_file}")
        try:
            with open(cache_file, 'rb') as f: data = pickle.load(f)

            # --- Basic Cache Validation ---
            if data.get('project_path') != self.project_path:
                logger.warning("Cache belongs to a different project path. Ignoring cache."); return False

            cache_timestamp = data.get('timestamp', 0)
            if cache_timestamp == 0:
                 logger.warning("Cache timestamp missing or invalid. Ignoring cache."); return False

            # --- Timestamp Validation (Check for newer source files) ---
            logger.debug("Validating cache timestamp against project files...")
            latest_modification_time = 0
            relevant_extensions = ('.java', '.properties', '.yml', '.yaml', '.xml')
            try:
                for root, dirs, files in os.walk(self.project_path):
                    # Efficiently filter ignored directories
                    dirs[:] = [d for d in dirs if d not in self.IGNORED_DIRS and not d.startswith('.')]
                    for filename in files:
                        if filename.endswith(relevant_extensions):
                            try:
                                file_path = os.path.join(root, filename)
                                latest_modification_time = max(latest_modification_time, os.path.getmtime(file_path))
                            except OSError: pass # Ignore errors for files that might disappear during walk
            except Exception as e: logger.warning(f"Error during cache timestamp validation walk: {e}. Assuming cache is invalid."); return False

            if latest_modification_time > cache_timestamp:
                logger.info(f"Project files modified ({time.ctime(latest_modification_time)}) since cache was created ({time.ctime(cache_timestamp)}). Invalidating cache."); return False

            # --- Data Reconstruction ---
            logger.info("Cache is valid. Loading data...");
            # Load basic structures
            self.index_structure = data.get('index_structure', {})
            self.package_structure = defaultdict(list, data.get('package_structure', {}))
            # Rebuild string_index as defaultdict
            self.string_index = defaultdict(list)
            cached_string_idx = data.get('string_index', {})
            for k, v_list in cached_string_idx.items(): self.string_index[k].extend(v_list)

            self.parse_errors = data.get('parse_errors', [])
            self.components = {} # Clear before loading
            self.methods = {}    # Clear before loading

            # Reconstruct components from dicts
            cached_components = data.get('components', {})
            if not cached_components: logger.warning("Cache contains no component data.");
            for fqn, comp_dict in cached_components.items():
                 try:
                      c=SpringBootComponent(comp_dict['name'],comp_dict['file_path'],comp_dict['component_type'],comp_dict['index'])
                      # Assign attributes safely using .get()
                      c.imports = comp_dict.get('imports', [])
                      c.annotations = comp_dict.get('annotations', [])
                      c.package = comp_dict.get('package', '')
                      c.fully_qualified_name = comp_dict.get('fully_qualified_name', fqn)
                      c.extends = comp_dict.get('extends') # Can be None, str, or list
                      c.implements = comp_dict.get('implements', [])
                      c.generics = comp_dict.get('generics', [])
                      # Fields and Methods dicts on component will be populated when Methods are loaded below
                      c.fields = {} # Initialize empty dicts
                      c.methods = {}
                      self.components[fqn] = c
                 except KeyError as e_key: logger.error(f"Missing key {e_key} loading component {fqn} from cache.")
                 except Exception as e_comp: logger.error(f"Error reconstructing component {fqn} from cache: {e_comp}")

            # Reconstruct methods from dicts and link to components
            cached_methods = data.get('methods', {})
            if not cached_methods: logger.warning("Cache contains no method data.");
            for method_key, method_dict in cached_methods.items():
                try:
                    # Determine parent FQN (needs careful parsing based on key structure)
                    fqn_parts = method_key.split('.')
                    # method_name_with_sig = fqn_parts[-1] # Not reliable if class name has '.'
                    method_name = method_dict.get('name')

                    # Heuristic: Assume key is package.Class$Inner.method(params) or package.Class.method(params)
                    # Find the last part that starts with lowercase (likely method name start) or known delimiters like '('
                    split_point = -1
                    for i in range(len(fqn_parts) - 1, 0, -1):
                         part = fqn_parts[i]
                         # Check for method signature start or common method naming patterns
                         if '(' in part or (part and part[0].islower() and i > 0 and fqn_parts[i-1][0].isupper()):
                              split_point = i
                              break
                    if split_point != -1:
                         parent_fqn = '.'.join(fqn_parts[:split_point])
                    else: # Fallback if heuristic fails (e.g., all caps class names)
                         parent_fqn = '.'.join(fqn_parts[:-1]) # Assume last part is method name + sig


                    parent_comp = self.components.get(parent_fqn)
                    if parent_comp:
                        m=Method(method_name, method_dict['signature'], "", parent_comp) # No body needed
                        m.annotations = method_dict.get('annotations', [])
                        m.modifiers = method_dict.get('modifiers', [])
                        m.return_type = method_dict.get('return_type')
                        m.parameters = method_dict.get('parameters', [])
                        m.exceptions = method_dict.get('exceptions', [])
                        m.start_line = method_dict.get('start_line', 0)
                        m.end_line = method_dict.get('end_line', 0)
                        m.calls = [] # Will be rebuilt from graph
                        m.called_by = [] # Will be rebuilt from graph

                        self.methods[method_key] = m
                        # Link method back to parent component's method dict
                        comp_method_key_sig = method_dict['signature']
                        if method_name == '<init>': # Use ClassName for constructor key in component
                             comp_method_key = f"{parent_comp.name}{comp_method_key_sig}"
                        else:
                             comp_method_key = f"{method_name}{comp_method_key_sig}"

                        # SAFE: Ensure component's methods dict exists
                        if parent_comp.methods is None: parent_comp.methods = {}
                        parent_comp.methods[comp_method_key] = m
                    else:
                        logger.warning(f"Parent component '{parent_fqn}' not found for method '{method_key}' during cache load.")

                except KeyError as e_key: logger.error(f"Missing key {e_key} loading method {method_key} from cache.")
                except Exception as e_meth: logger.error(f"Error reconstructing method {method_key} from cache: {e_meth}")

            # Reconstruct call graph
            self.call_graph = nx.DiGraph()
            # Add nodes *only* for methods successfully loaded
            [self.call_graph.add_node(k) for k in self.methods]
            edges = data.get('call_graph_edges', [])
            # Add edges only between nodes that exist in the graph
            valid_edges = [(u, v) for u, v in edges if u in self.call_graph and v in self.call_graph]
            self.call_graph.add_edges_from(valid_edges)

            # Rebuild Method.calls and Method.called_by lists from the loaded graph
            for u, v in self.call_graph.edges():
                 # Check both ends exist in our reconstructed methods map
                 if u in self.methods and v in self.methods:
                     caller_method = self.methods[u]
                     callee_method = self.methods[v]
                     # Append if not already present (safety check)
                     if callee_method not in (caller_method.calls or []):
                         if caller_method.calls is None: caller_method.calls = []
                         caller_method.calls.append(callee_method)
                     if caller_method not in (callee_method.called_by or []):
                         if callee_method.called_by is None: callee_method.called_by = []
                         callee_method.called_by.append(caller_method)

            logger.info(f"Cache loaded successfully. Graph: {self.call_graph.number_of_nodes()} nodes, {self.call_graph.number_of_edges()} edges.")
            return True

        except (EOFError, pickle.UnpicklingError, KeyError, AttributeError, TypeError) as e:
             logger.error(f"Cache file '{cache_file}' is invalid or corrupt: {e}. Removing cache file.")
             try: os.remove(cache_file)
             except OSError: pass # Ignore error if removal fails
             return False
        except Exception as e:
             logger.error(f"Unexpected error loading cache: {type(e).__name__} - {e}.");
             # Optionally remove cache on any load error:
             # try: os.remove(cache_file)
             # except OSError: pass
             return False


    # --- Public API / Helper Methods ---

    def search_method(self, name_part):
        """Searches for methods whose names contain the given string (case-insensitive)."""
        name_lower = name_part.lower()
        # Use list comprehension for potentially better performance on large method sets
        matches = [m for k, m in self.methods.items() if name_lower in m.name.lower()]
        # Sort results for consistent display
        return sorted(matches, key=lambda m: (m.parent_component.fully_qualified_name, m.name))

    def search_string(self, term):
        """Searches the pre-built index for identifiers or string literals (case-insensitive)."""
        # defaultdict handles missing keys automatically, returning []
        return self.string_index.get(term.lower(), [])

    def get_spring_components(self, component_type_filter=None):
        """Returns a sorted list of SpringBootComponent objects, optionally filtered by type."""
        target_type_lower = component_type_filter.lower() if component_type_filter else None
        results = []
        known_spring_types_lower = {sa[1:].lower() for sa in self.SPRING_ANNOTATIONS} # Pre-calculate lowercase set

        for fqn, comp in self.components.items():
            # SAFE: Ensure component_type is a string before lowercasing
            current_type_lower = comp.component_type.lower() if isinstance(comp.component_type, str) else ""
            match = False

            # Check if the component's type or annotations match known Spring types
            is_spring_type = current_type_lower in known_spring_types_lower
            if not is_spring_type:
                 # SAFE: Check annotations list exists and items are strings
                 is_spring_type = any(a[1:].lower() in known_spring_types_lower for a in comp.annotations or [] if isinstance(a, str) and len(a)>1)

            if not is_spring_type: continue # Skip if not identified as a Spring component at all

            # Apply filter if provided
            if target_type_lower is None: # Get all Spring components
                match = True
                # Refine type if current type isn't a primary Spring stereotype but has one in annotations
                if current_type_lower not in known_spring_types_lower:
                    for a in comp.annotations or []:
                        if isinstance(a, str) and len(a) > 1 and a[1:].lower() in known_spring_types_lower:
                            comp.component_type = a[1:].capitalize() # Update type (e.g., 'Class' -> 'Service')
                            break # Use the first Spring annotation found
            # Specific type requested (handle RestController as Controller special case)
            elif target_type_lower == current_type_lower or \
                 (target_type_lower == "controller" and current_type_lower == "restcontroller"):
                 match = True

            if match: results.append(comp)

        return sorted(results, key=lambda c: c.fully_qualified_name) # Sort by FQN


    def analyze_method_flow(self, method_key):
        """Retrieves details, source, calls, and callers for a given method key."""
        method_obj, canonical_key = (self.methods.get(method_key), method_key)

        # If exact key not found, try case-insensitive search
        if not method_obj:
            key_lower = method_key.lower()
            matches = [(k, m) for k, m in self.methods.items() if key_lower in k.lower()]

            if len(matches) == 1:
                canonical_key, method_obj = matches[0]; logger.info(f"Found unique case-insensitive match for '{method_key}': {canonical_key}")
            elif len(matches) > 1:
                logger.warning(f"Ambiguous method key '{method_key}'. Found multiple potential matches.")
                # Return structure indicating multiple matches for UI handling
                return {"multiple_matches": [m for k, m in matches]} # Return method objects
            else:
                logger.error(f"Method key '{method_key}' not found."); return None

        if not method_obj or not canonical_key: return None # Should not happen

        # Attempt to read source lines if not already available
        source_lines = method_obj.source_lines or []
        if not source_lines and method_obj.start_line > 0 and method_obj.end_line > 0 and method_obj.parent_component:
            file_path = method_obj.parent_component.file_path
            if os.path.isfile(file_path):
                try:
                     content = ""; encs=['utf-8','latin-1','cp1252']; read_ok = False
                     for enc in encs:
                         try:
                             with open(file_path,'r',encoding=enc) as f: content=f.read(); read_ok = True; break;
                         except UnicodeDecodeError: continue
                         except Exception: break
                     if read_ok and content:
                          all_lines = content.splitlines()
                          start_idx = method_obj.start_line - 1
                          end_idx = method_obj.end_line # Slice uses end index
                          if 0 <= start_idx < end_idx <= len(all_lines):
                               source_lines = [l.rstrip() for l in all_lines[start_idx:end_idx]]
                               method_obj.source_lines = source_lines # Cache back if read
                          else: logger.warning(f"Invalid line numbers ({method_obj.start_line}-{method_obj.end_line}) for file {file_path}")
                     elif not read_ok : logger.warning(f"Could not read source file {file_path} with tested encodings.")
                except Exception as e: logger.warning(f"Source code read failed for {canonical_key}: {e}")
            else: logger.warning(f"Source file not found for method {canonical_key}: {file_path}")

        # Build result dictionary
        result = {
            "method": f"{method_obj.parent_component.name}.{method_obj.name}{method_obj.signature}",
            "method_key": canonical_key,
            "component": method_obj.parent_component.name,
            "component_type": method_obj.parent_component.component_type,
            "signature": method_obj.signature,
            "source": source_lines,
            "calls": self._get_method_calls(canonical_key), # Uses graph
            "called_by": self._get_method_callers(canonical_key), # Uses graph
            "annotations": method_obj.annotations or [] # Ensure list
        }
        return result


    def _get_method_calls(self, method_key, depth=0, max_depth=3, visited=None):
        """Recursively gets outgoing calls from the graph (limited depth)."""
        if visited is None: visited = set()
        # Stop recursion if depth exceeded, key visited, or key not in graph
        if depth > max_depth or method_key in visited or method_key not in self.call_graph: return []
        visited.add(method_key); outgoing_calls = []

        # Get successors safely
        successors = list(self.call_graph.successors(method_key)) if method_key in self.call_graph else []
        for target_key in successors:
            target_method = self.methods.get(target_key)
            if target_method:
                call_info = {
                    "method": f"{target_method.parent_component.name}.{target_method.name}{target_method.signature}",
                    "method_key": target_key,
                    "component": target_method.parent_component.name,
                    "component_type": target_method.parent_component.component_type,
                    "children": [] # Placeholder for recursive calls
                }
                if depth < max_depth:
                     # Pass a copy of visited to avoid issues with sibling branches
                     call_info["children"] = self._get_method_calls(target_key, depth + 1, max_depth, visited.copy())
                outgoing_calls.append(call_info)

        return sorted(outgoing_calls, key=lambda x: x['method']) # Sort for consistent display


    def _get_method_callers(self, method_key, depth=0, max_depth=1, visited=None):
        """Recursively gets incoming callers from the graph (limited depth)."""
        if visited is None: visited = set()
        if depth > max_depth or method_key in visited or method_key not in self.call_graph: return []
        visited.add(method_key); incoming_callers = []

        # Get predecessors safely
        predecessors = list(self.call_graph.predecessors(method_key)) if method_key in self.call_graph else []
        for source_key in predecessors:
            source_method = self.methods.get(source_key)
            if source_method:
                 caller_info = {
                    "method": f"{source_method.parent_component.name}.{source_method.name}{source_method.signature}",
                    "method_key": source_key,
                    "component": source_method.parent_component.name,
                    "component_type": source_method.parent_component.component_type,
                    "parents": [] # Placeholder for recursive calls
                 }
                 if depth < max_depth:
                      # Pass a copy of visited
                      caller_info["parents"] = self._get_method_callers(source_key, depth + 1, max_depth, visited.copy())
                 incoming_callers.append(caller_info)

        return sorted(incoming_callers, key=lambda x: x['method'])


    def print_project_structure(self):
        """Prints the indexed project structure to the console."""
        # Uses colored utility function
        root_name = self.index_structure.get('name', 'Project Root')
        print(colored(f"\n--- Project Structure: {root_name} ---", Colors.BOLD + Colors.UNDERLINE))
        self._print_node_ascii(self.index_structure.get('children', []), "")
        print("--- End of Structure ---")

    def _print_node_ascii(self, children, prefix):
        # SAFE: Ensure children is iterable
        safe_children = children or []
        # Sort children: directories first, then by name
        s_children = sorted(safe_children, key=lambda x: (x.get('type', '') != 'directory', x.get('name', '').lower()))
        num_children = len(s_children)

        for i, child in enumerate(s_children):
            if child is None: continue # Skip None entries if any

            name=child.get('name','?'); node_type=child.get('type','?'); index=child.get('index','?')
            is_last = (i == num_children - 1)
            ptr = '└─ ' if is_last else '├─ '
            child_prefix = '   ' if is_last else '│  '

            # Determine color based on type using Colors constants
            name_color = Colors.WHITE # Default
            if node_type == 'directory': name_color = Colors.BRIGHT_BLUE
            elif node_type == 'java': name_color = Colors.BRIGHT_GREEN
            elif node_type in ['config','xml','properties','yml','yaml', 'build']: name_color = Colors.BRIGHT_YELLOW
            elif node_type == 'web': name_color = Colors.CYAN
            elif node_type == 'doc': name_color = Colors.MAGENTA
            # Add more type colors as needed

            name_str = colored(name, name_color)
            index_str = colored(f"[{index}]", Colors.BRIGHT_MAGENTA) # Add brackets to index

            print(f"{prefix}{ptr}{index_str} {name_str}")

            # Recurse into directories
            if child.get('type') == 'directory':
                 # SAFE: Pass child's children list safely using 'or []'
                 self._print_node_ascii(child.get('children', []) or [], prefix + child_prefix)


    def get_parse_errors(self):
        """Returns the list of parsing errors recorded during analysis."""
        return self.parse_errors or []


    def get_node_by_index(self, index):
        """Finds a node in the index_structure using its dot-separated index string."""
        if not isinstance(index, str) or not index: return None
        if index == '0': return self.index_structure # Root node

        parts = index.split('.')
        current_node = self.index_structure
        try:
            for part in parts:
                # Convert index part to integer (1-based from user)
                idx_num = int(part)
                # Access children safely, default to empty list
                children = current_node.get('children', []) or []
                # Check bounds (convert 1-based to 0-based list index)
                if 0 < idx_num <= len(children):
                     current_node = children[idx_num - 1]
                     # SAFE: Check if node became None unexpectedly
                     if current_node is None:
                          logger.warning(f"Found None node at index part {idx_num} for '{index}'")
                          return None
                else:
                     logger.warning(f"Index part {idx_num} is out of bounds for node {current_node.get('name', '?')} (Index: '{index}')"); return None
            return current_node # Return the final node found
        except ValueError:
             logger.error(f"Invalid index format: '{index}'. Parts must be integers separated by dots."); return None
        except Exception as e: logger.error(f"Error getting node by index '{index}': {e}"); return None


    def convert_files_to_txt(self, node_index, target_output_dir=None):
        """Converts files under a given index node to .txt format."""
        node = self.get_node_by_index(node_index)
        if not node: return False, f"Node with index '{node_index}' not found in project structure."

        # Gather list of file nodes to convert
        files_to_convert = self._get_all_files_in_node(node) # Recursive helper

        if not files_to_convert: return True, f"No files found within node '{node_index}' to convert."

        # Prepare and validate output directory
        base_output_path = None
        if target_output_dir:
             base_output_path = os.path.abspath(target_output_dir)
             if not os.path.exists(base_output_path):
                 try: os.makedirs(base_output_path); logger.info(f"Created output directory: {base_output_path}")
                 except OSError as e: return False, f"Cannot create output directory '{base_output_path}': {e}"
             elif not os.path.isdir(base_output_path):
                  return False, f"Specified output path '{base_output_path}' exists but is not a directory."

        conversion_count, conversion_errors = 0, []
        for f_node in files_to_convert:
             # Ensure node has a valid file path
             if 'path' in f_node and os.path.isfile(f_node['path']):
                 ok, msg_or_target = self._convert_single_file_to_txt(f_node['path'], base_output_path)
                 if ok: conversion_count += 1
                 else: conversion_errors.append(f"{os.path.basename(f_node['path'])}: {msg_or_target}")
             else:
                  # Skip nodes that aren't valid files
                  logger.debug(f"Skipping conversion for non-file node: {f_node.get('name', '?')}")

        # Report results
        if not conversion_errors: return True, f"Successfully converted {conversion_count} file(s)."
        else: return False, f"Converted {conversion_count} file(s) with {len(conversion_errors)} error(s):\n - "+"\n - ".join(conversion_errors)


    def _get_all_files_in_node(self, node):
        """Recursively finds all file nodes under a given structure node."""
        file_nodes = []
        if node is None: return file_nodes # Safety check

        # If the node itself is a file with a valid path, add it
        if node.get('type') != 'directory' and 'path' in node and os.path.isfile(node['path']):
             file_nodes.append(node)
        # If it's a directory, recurse into children
        elif node.get('type') == 'directory':
             # SAFE: Iterate over children safely
             for child in node.get('children', []) or []:
                 if child: # Ensure child is not None
                     file_nodes.extend(self._get_all_files_in_node(child))
        return file_nodes


    def _convert_single_file_to_txt(self, source_file_path, base_output_dir):
        """Reads a single file and writes its content to a .txt file."""
        try:
            # Determine target path
            target_file_path = ""
            if base_output_dir:
                 # Maintain relative structure within the output directory
                 try:
                      relative_path = os.path.relpath(source_file_path, self.project_path)
                 except ValueError: # Handle paths on different drives (Windows)
                      relative_path = os.path.basename(source_file_path) # Fallback to just filename
                 target_file_path = os.path.join(base_output_dir, relative_path + '.txt')
                 # Ensure target subdirectory exists
                 os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
            else:
                 # Save .txt next to the original file
                 target_file_path = source_file_path + '.txt'

            # Read source file with multiple encoding attempts
            content = ""; encs = ['utf-8', 'latin-1', 'cp1252']; read_ok = False
            for enc in encs:
                try:
                    with open(source_file_path, 'r', encoding=enc) as f_in: content = f_in.read(); read_ok = True; break
                except UnicodeDecodeError: continue
                except Exception as e_read: raise IOError(f"Read failed ({enc}): {e_read}") from e_read
            if not read_ok: raise IOError(f"Could not read file with tested encodings: {source_file_path}")

            # Write target file using UTF-8
            with open(target_file_path, 'w', encoding='utf-8') as f_out: f_out.write(content)

            return True, target_file_path # Return success and the path created

        except Exception as e:
            logger.error(f"Error converting file '{os.path.basename(source_file_path)}' to txt: {e}")
            return False, str(e) # Return failure and error message


    def interactive_structure_browser(self):
        """Provides a console-based interactive file browser."""
        # Uses utils: clear_screen, colored, Colors, menu_option, error, warning, info
        # Calls self.get_node_by_index, self.convert_files_to_txt
        current_node = self.index_structure
        if not current_node: logger.error("Project structure index is empty!"); return

        while True:
            clear_screen(); print(colored(f"Current Directory: {current_node.get('path', 'N/A')}", Colors.BOLD))
            print(colored(f"{'Index':<18} {'Type':<6} {'Name'}", Colors.UNDERLINE))

            # Option to go up, unless at root
            parent_idx = None
            current_idx = current_node.get('index', '0')
            if current_idx != '0' and '.' in current_idx:
                 parent_idx = '.'.join(current_idx.split('.')[:-1])
            elif current_idx != '0': # Handle direct child of root
                 parent_idx = '0'

            if parent_idx is not None:
                 print(f"{colored('[..]', Colors.BRIGHT_YELLOW):<18} {'<DIR>':<6} {'Go up'}")

            # List children
            children = sorted(current_node.get('children', []) or [], key=lambda x: (x.get('type', '') != 'directory', x.get('name', '').lower()))
            if not children and parent_idx is None: # Special case for empty root
                 print(colored("  (Project appears empty or could not be indexed)", Colors.YELLOW))

            for c in children:
                if c is None: continue
                n, t, i = c.get('name','?'), c.get('type','?'), c.get('index','?')
                # Format type display
                type_display = "<DIR>" if t == 'directory' else (f"<{t[:4].upper()}>" if t else "<????>")
                # Get color
                n_color = Colors.WHITE
                if t == 'directory': n_color = Colors.BRIGHT_BLUE
                elif t == 'java': n_color = Colors.BRIGHT_GREEN
                elif t in ['config','xml','properties','yml','yaml','build']: n_color = Colors.BRIGHT_YELLOW
                # Add more colors...
                print(f"{colored(f'[{i}]', Colors.BRIGHT_MAGENTA):<18} {colored(type_display, n_color):<6} {colored(n, n_color)}")

            # Print actions
            print("\n" + colored("─"*60, Colors.BRIGHT_BLACK))
            print(colored("Actions: Enter index to navigate | v [INDEX] (view) | c [INDEX] [-o DIR] (convert) | .. (up) | q (quit)", Colors.BRIGHT_CYAN))
            choice = input(colored("Enter index or command: ", Colors.BOLD)).strip()

            if choice.lower() == 'q': break
            elif choice == '..': # Go up
                 if parent_idx is not None:
                      parent_node = self.get_node_by_index(parent_idx)
                      current_node = parent_node if parent_node else self.index_structure # Go to parent or root
                 else: print(warning("Already at the project root.")); time.sleep(1)

            elif choice.lower().startswith('c '): # Convert action
                parts=choice.split(); idx_to_convert=parts[1] if len(parts)>1 else None; output_dir=None
                if not idx_to_convert: print(error("Missing index for conversion command 'c'")); time.sleep(1); continue
                # Check for output directory argument
                if '-o' in parts:
                    try: output_dir = parts[parts.index('-o')+1]
                    except IndexError: print(error("Missing directory path after -o option")); time.sleep(1); continue

                print(info(f"Attempting to convert node '{idx_to_convert}'..."))
                ok, msg = self.convert_files_to_txt(idx_to_convert, output_dir)
                print(success(msg) if ok else error(f"Conversion Failed:\n{msg}")); input(colored("Press Enter...", Colors.BOLD))

            elif choice.lower().startswith('v '): # View action
                idx_to_view = choice[2:].strip()
                if not idx_to_view: print(error("Missing index for view command 'v'")); time.sleep(1); continue

                file_node = self.get_node_by_index(idx_to_view)
                if not file_node: print(error(f"Index '{idx_to_view}' not found.")); time.sleep(1); continue
                if file_node.get('type')=='directory': print(warning("Cannot view a directory. Enter index of a file.")); time.sleep(1); continue
                file_path_to_view = file_node.get('path')
                if not file_path_to_view or not os.path.isfile(file_path_to_view): print(error(f"Node {idx_to_view} does not point to a valid file path.")); time.sleep(1); continue

                # Use the shared _view_source method (from cli.py originally) - needs refactoring maybe
                # For now, duplicate simplified view logic here
                try:
                    clear_screen(); print(colored(f"Viewing File: {file_path_to_view}", Colors.BOLD)); print(colored("="*80, Colors.BRIGHT_CYAN))
                    content = ""; page_size = os.get_terminal_size().lines - 5 if hasattr(os, 'get_terminal_size') else 30
                    read_ok = False; encs = ['utf-8','latin-1','cp1252']
                    for enc in encs:
                        try:
                            with open(file_path_to_view,'r',encoding=enc) as f: content=f.read(); read_ok=True; break
                        except UnicodeDecodeError: continue
                        except Exception as e_r: raise IOError(f"Read error ({enc}): {e_r}") from e_r
                    if not read_ok: raise IOError("Cannot read file with tested encodings")

                    lines = content.splitlines(); line_count = len(lines)
                    for page_start in range(0, line_count, page_size):
                         page_end = min(page_start + page_size, line_count)
                         print("\n".join(f"{colored(str(i+1).rjust(4), Colors.BRIGHT_BLACK)}: {lines[i]}" for i in range(page_start, page_end)))
                         if page_end < line_count:
                             cont = input(colored(f"--More-- (L{page_start+1}-{page_end}/{line_count}) (Enter/q):", Colors.BRIGHT_YELLOW))
                             if cont.lower() == 'q': break
                         else: print(colored("\n--End of File--", Colors.BRIGHT_YELLOW))
                    print(colored("="*80, Colors.BRIGHT_CYAN)); input(colored("Press Enter...", Colors.BOLD))
                except Exception as e: print(error(f"Error viewing file: {e}")); time.sleep(2)

            else: # Try navigating using the input as an index
                target_node = self.get_node_by_index(choice)
                if target_node and target_node.get('type') == 'directory':
                     current_node = target_node # Navigate into directory
                elif target_node: # It's a file or other non-directory node
                     print(warning(f"'{choice}' is not a directory. Use 'v {choice}' to view or 'c {choice}' to convert.")); time.sleep(1.5)
                else: # Invalid index or command
                     print(error(f"Invalid index or command: '{choice}'")); time.sleep(1)


    def clear_cache(self):
        """Removes the cache directory and re-initializes explorer state."""
        # Uses utils: logger, info, error
        if os.path.exists(self.cache_dir):
            try:
                 shutil.rmtree(self.cache_dir)
                 # Recreate directory immediately after deletion? Optional.
                 # os.makedirs(self.cache_dir)
                 logger.info("Cache directory removed successfully.")
                 # Reset internal state by calling __init__ again
                 self.__init__(self.project_path) # Re-initialize attributes
                 return True, "Cache cleared. Re-analysis is required on next run."
            except Exception as e:
                 logger.error(f"Failed to remove cache directory '{self.cache_dir}': {e}");
                 return False, f"Error clearing cache: {e}"
        else:
             logger.info("Cache directory not found, nothing to clear.")
             # Optionally re-init state even if no directory existed
             # self.__init__(self.project_path)
             return True, "Cache directory not found."


    def debug_annotations(self):
        """Collects unique annotations and summarizes component types."""
        # Uses defaultdict
        all_annotations = set()

        # SAFE: Iterate over components safely
        for comp in (self.components or {}).values():
             if comp: # Check component object exists
                 # SAFE: Use 'or []' for annotations
                 all_annotations.update(a for a in comp.annotations or [] if isinstance(a, str))
                 # SAFE: Check fields dict and iterate safely
                 for field in (comp.fields or {}).values():
                      if field: # Check field object exists
                           all_annotations.update(a for a in field.annotations or [] if isinstance(a, str))

        # SAFE: Iterate over methods safely
        for method in (self.methods or {}).values():
             if method: # Check method object exists
                  all_annotations.update(a for a in method.annotations or [] if isinstance(a, str))

        # Summarize component types
        component_summary = defaultdict(int)
        for comp in (self.components or {}).values():
             if comp:
                 comp_type_str = comp.component_type if isinstance(comp.component_type, str) else "Unknown"
                 component_summary[comp_type_str] += 1

        return sorted(list(all_annotations)), dict(component_summary)


    def create_patch_from_local_changes(self, output_patch_file, include_binary=False):
        """Creates a git patch file from local uncommitted changes."""
        # Uses utils: logger, info, warning, error
        logger.info(f"Attempting to create patch file at: {output_patch_file}")
        git_dir_path = os.path.join(self.project_path, '.git')
        if not os.path.isdir(git_dir_path):
            msg = f"Project path does not appear to be a Git repository (missing .git dir): {self.project_path}"; logger.error(msg); return False, msg

        output_abs_path = os.path.abspath(output_patch_file)
        output_dir = os.path.dirname(output_abs_path)
        # Ensure output directory exists
        if not os.path.isdir(output_dir):
            try: os.makedirs(output_dir); logger.info(f"Created output directory for patch: {output_dir}")
            except OSError as e: msg=f"Cannot create output directory '{output_dir}': {e}"; logger.error(msg); return False, msg

        # Prepare git diff command using -C for safety
        cmd = ['git', '-C', self.project_path, 'diff']
        if include_binary: cmd.append('--binary')
        cmd.append('HEAD') # Diff working tree & index against last commit

        try:
            logger.info(f"Running command: {' '.join(cmd)}")
            # Run initial diff against HEAD
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)

            # Check for "fatal: ambiguous argument 'HEAD'" (common in new/empty repos)
            head_error = False
            if res.returncode != 0 and res.stderr and ("ambiguous argument 'HEAD'" in res.stderr or "bad revision 'HEAD'" in res.stderr):
                 logger.warning("Git HEAD revision not found. Retrying diff against empty tree (4b825...).")
                 head_error = True
                 cmd[-1] = '4b825dc642cb6eb9a060e54bf8d69288fbee4904' # Git's empty tree hash
                 logger.info(f"Retrying command: {' '.join(cmd)}")
                 res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)

            # Check final result (0=no changes, 1=changes found, other=error)
            if res.returncode not in [0, 1]:
                 error_context = "during initial diff" if not head_error else "during empty tree diff"
                 msg=f"Git diff command failed {error_context} (Code: {res.returncode})."
                 logger.error(f"{msg}\nGit stderr: {res.stderr.strip()}")
                 return False, f"{msg} Git Error: {res.stderr.strip()}"

            patch_content = res.stdout

            # Write the patch file
            try:
                with open(output_abs_path, 'w', encoding='utf-8') as f: f.write(patch_content)
                # Determine success message
                if not patch_content and res.returncode == 0: msg = f"Patch created (no changes detected): {output_abs_path}"
                elif not patch_content and res.returncode == 1: msg = f"Patch created (empty content, though git indicated changes?): {output_abs_path}"; logger.warning(msg)
                else: msg = f"Patch created successfully: {output_abs_path}"
                logger.info(msg); return True, msg
            except IOError as e: msg=f"Error writing patch file '{output_abs_path}': {e}"; logger.error(msg); return False, msg

        except FileNotFoundError:
             msg = "'git' command not found. Ensure Git is installed and in your system's PATH."; logger.error(msg); return False, msg
        except Exception as e:
             msg = f"An unexpected error occurred during patch creation: {e}"; logger.error(msg, exc_info=True); return False, msg

# --- End SpringBootExplorer ---
