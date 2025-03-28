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
    from javalang.tree import MethodInvocation, TypeDeclaration # Keep specific imports needed
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
                logger.warning(f"Cache dir error: {e}")
        logger.info(f"Init Explorer for: {self.project_path}")

    def analyze_project(self):
        logger.info("Analysis starting..."); t_start=time.time()
        if self._load_from_cache(): logger.info(f"Loaded cache in {time.time()-t_start:.2f}s"); return
        logger.info("Cache invalid/missing, analyzing..."); self._build_project_structure(); self._parse_java_files()
        self._build_component_relationships(); self._build_call_graph(); self._build_string_index(); self._save_to_cache()
        logger.info(f"Analysis done in {time.time()-t_start:.2f}s. Comps:{len(self.components)}, Methods:{len(self.methods)}.")
        if self.parse_errors: logger.warning(f"{len(self.parse_errors)} parse errors.")

    def _build_project_structure(self):
        logger.info("Building structure..."); self.index_structure={"index":"0", "path":self.project_path, "name":os.path.basename(self.project_path), "type":"directory", "children":[]}
        self._traverse_directory(self.project_path, self.index_structure["children"], "")
        logger.info("Structure built.")

    def _traverse_directory(self, directory, children_list, parent_idx):
        try:
            items = sorted(os.listdir(directory))
        except Exception as e:
            logger.debug(f"Cannot list {directory}: {e}"); return
        if os.path.basename(directory) in self.IGNORED_DIRS: return
        for i, item in enumerate(items):
            path = os.path.join(directory, item); idx = f"{parent_idx}.{i+1}" if parent_idx else f"{i+1}"
            try:
                is_dir = os.path.isdir(path); is_file = os.path.isfile(path)
            except OSError:
                continue
            if is_dir:
                if os.path.basename(path) not in self.IGNORED_DIRS:
                    entry={"index":idx,"path":path,"name":item,"type":"directory","children":[]}; children_list.append(entry)
                    self._traverse_directory(path, entry["children"], idx)
            elif is_file: children_list.append({"index":idx,"path":path,"name":item,"type":self._determine_file_type(item)})

    def _determine_file_type(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        types={'.java':'java','.properties':'config','.yml':'config','.yaml':'config','.xml':'xml','.html':'web','.css':'web','.js':'web','.jsp':'web','.ts':'web','.tsx':'web','.jsx':'web','.md':'doc','.txt':'doc','.png':'image','.jpg':'image','.jpeg':'image','.gif':'image','.svg':'image','.sql':'sql'}
        return types.get(ext, 'other')

    def _parse_java_files(self):
        logger.info("Parsing Java..."); files = self._find_files_by_type(self.index_structure, "java")
        if not files: logger.warning("No Java files found."); return
        use_par = len(files) > 50; parser = self._parse_java_files_parallel if use_par else self._parse_java_files_sequential
        logger.info(f"Parsing {len(files)} files ({'parallel' if use_par else 'sequential'})...")
        parser(files); logger.info("Parsing attempt finished.")

    def _parse_java_files_sequential(self, files):
        for i, f_info in enumerate(files):
            # logger.debug(f"Parsing {i+1}/{len(files)}: {f_info['path']}")
            try:
                self._parse_java_file(f_info["path"], f_info["index"])
            except Exception as e:
                logger.error(f"Unhandled parse error {f_info['path']}: {e}"); self.parse_errors.append((f_info['path'], f"Unhandled: {e}"))

    def _parse_java_files_parallel(self, files):
        max_w = min(12, (os.cpu_count() or 1)+4)
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            f_map = {executor.submit(self._parse_java_file, f["path"], f["index"]): f for f in files}
            for i, fut in enumerate(as_completed(f_map)):
                f_info = f_map[fut]
                try:
                    fut.result()
                except Exception as e:
                    logger.error(f"Thread error {f_info['path']}: {e}"); self.parse_errors.append((f_info['path'], f"Thread error: {e}"))
                # if (i+1)%100==0: logger.info(f"Parsed {i+1}/{len(files)}...")

    def _find_files_by_type(self, node, f_type):
        res = [];
        if node.get("type") == f_type: res.append(node)
        for c in node.get("children", []): res.extend(self._find_files_by_type(c, f_type))
        return res

    def _parse_java_file(self, file_path, index):
        content = None; encodings = ['utf-8', 'latin-1', 'cp1252']
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f: content = f.read(); break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.warning(f"Read error {file_path}({enc}): {e}"); self.parse_errors.append((file_path, f"Read({enc}): {e}")); return
        if content is None: logger.warning(f"Cannot read {file_path}"); self.parse_errors.append((file_path,"Read encoding error")); return

        try:
            tree = javalang.parse.parse(content)
            pkg = tree.package.name if tree.package else ""
            imports = [imp.path for imp in tree.imports]
            for path, node in tree.filter(TypeDeclaration): # Use imported TypeDeclaration
                if not any(isinstance(p, TypeDeclaration) for p in path): # Top-level only
                    self._process_type_declaration(node, pkg, imports, content, file_path, index)
        except (javalang.tokenizer.LexerError, javalang.parser.JavaSyntaxError, IndexError, TypeError, AttributeError, RecursionError) as e:
            line = e.pos.line if hasattr(e,'pos') and e.pos else '?'; err=type(e).__name__; desc=getattr(e,'description',str(e))[:100]
            logger.warning(f"{err} in {os.path.basename(file_path)} L{line}: {desc}.")
            self.parse_errors.append((file_path, f"{err} L{line}: {desc}"))
        except Exception as e:
            logger.error(f"Unexpected parse error {file_path}: {type(e).__name__}-{e}"); self.parse_errors.append((file_path, f"Unexpected: {type(e).__name__}-{e}"))

    def _process_type_declaration(self, node, context_name, imports, content, file_path, index):
        name = node.name; fqn = f"{context_name}${name}" if '$' in context_name or ('.' in context_name and context_name not in self.package_structure) else (f"{context_name}.{name}" if context_name else name)
        comp_type = self._determine_component_type(node); annos = [f"@{a.name}" for a in getattr(node,'annotations',[])]
        comp = SpringBootComponent(name, file_path, comp_type, index)
        comp.imports=imports; comp.annotations=annos; comp.package=context_name.split('$')[0] if '$' in context_name else context_name; comp.fully_qualified_name=fqn
        comp.generics=[p.name for p in getattr(node,'type_parameters',[]) if p];
        ext = getattr(node,'extends',None); imp = getattr(node,'implements',None)
        if ext: comp.extends = [self._format_type(e) for e in ext] if isinstance(ext,list) else self._format_type(ext)
        if imp: comp.implements = [self._format_type(i) for i in imp]
        if hasattr(node,'fields'): [self._process_field(f, comp) for f in node.fields]
        if hasattr(node,'methods'): [self._process_method(m, comp, content) for m in node.methods]
        if hasattr(node,'constructors'): [self._process_constructor(c, comp, content) for c in node.constructors]
        # Store/Update component
        self.components[fqn] = comp
        if '.' in fqn and '$' not in fqn: # Add top-level FQN to package structure
            pkg_name = '.'.join(fqn.split('.')[:-1])
            if fqn not in self.package_structure[pkg_name]: self.package_structure[pkg_name].append(fqn)
        # Recurse for inner types
        if hasattr(node, 'body'):
            # Original code used enumerate(m for m in node.body if isinstance(m, javalang.tree.TypeDeclaration))
            # Replicating using imported TypeDeclaration
            inner_type_decls = [m for m in node.body if isinstance(m, TypeDeclaration)]
            for idx, member in enumerate(inner_type_decls):
                self._process_type_declaration(member, fqn, imports, content, file_path, f"{index}.i{idx+1}") # Pass current FQN as context

    def _determine_component_type(self, node):
        # Use javalang types directly
        type_map = {javalang.tree.ClassDeclaration:"Class", javalang.tree.InterfaceDeclaration:"Interface", javalang.tree.EnumDeclaration:"Enum", javalang.tree.AnnotationDeclaration:"Annotation"}
        comp_type = type_map.get(type(node), "Unknown")
        if hasattr(node, 'annotations'):
            for anno in node.annotations:
                for sa in self.SPRING_ANNOTATIONS:
                    # Check anno.name exists before lowercasing
                    if hasattr(anno, 'name') and anno.name and anno.name.lower() == sa[1:].lower():
                        return sa[1:] # Return canonical Spring name
        return comp_type

    def _format_type(self, node):
        if node is None: return "void"
        # Original code used isinstance(node, list) and node.count('dimensions')
        # This check seems specific and might need javalang.tree types if it was intended for array dimensions
        # Let's keep the logic but be aware it might need adjustment based on javalang structure.
        # If 'dimensions' is a direct attribute/key on list-like elements from javalang, it stays.
        # If not, this part might fail or need rework based on how javalang represents arrays.
        # For safety, let's assume it works as originally intended for now.
        if isinstance(node, list):
            dims_present = hasattr(node, 'dimensions') # Check if dimensions attr exists on the list-like object
            return self._format_type(node[0]) + ('[]' * len(node.dimensions) if dims_present and node.dimensions else '')

        name = getattr(node,'name',None)
        if name:
            base=name; sub=getattr(node,'sub_type',None); args=getattr(node,'arguments',None); dims=getattr(node,'dimensions',None)
            if sub: base += '.'+self._format_type(sub)
            if args: base += f"<{','.join([(self._format_type(a.type) if hasattr(a,'type') and a.type else (self._format_type(a.pattern_type) if hasattr(a,'pattern_type') else (getattr(a,'name','?') or '?'))) for a in args])}>"
            if dims: base += '[]'*len(dims)
            return base
        # Check for basic types represented differently in javalang
        if isinstance(node, javalang.tree.BasicType):
            return node.name
        # Fallback for primitives or other structures
        return getattr(node,'value',str(node))

    def _process_field(self, node, comp):
        type_s=self._format_type(node.type); mods=list(node.modifiers or []); annos=[f"@{a.name}" for a in node.annotations or []]
        for decl in node.declarators:
            name=decl.name; type_f=type_s+('[]'*len(decl.dimensions) if decl.dimensions else '')
            field=Field(name,type_f,mods,comp); field.annotations=annos; comp.fields[name]=field

    def _extract_source_lines(self, node, source_code):
        # This method uses string manipulation, no javalang specifics changed
        lines=source_code.splitlines(); start, end = -1,-1
        if hasattr(node,'position') and node.position: start=node.position.line
        if start>0:
            level,idx,found_start,end_line_calc=0,start-1,False,start # Renamed 'end' to avoid conflict
            while idx<len(lines):
                line=lines[idx]; open_b=line.count('{'); close_b=line.count('}')
                if not found_start:
                    if open_b > 0: found_start=True; level+=open_b-close_b;
                    elif idx > start+10: break # Give up
                else: level += open_b - close_b
                # Check if level returns to 0 or less *after* processing line's braces
                if found_start and level <= 0 and (open_b > 0 or close_b > 0): # Ensure brace was involved
                    # Special case: single line body {}
                    if level == 0 and open_b > 0 and idx == start -1:
                        end_line_calc = idx + 1 # End on the same line
                    elif level <= 0:
                        end_line_calc = idx + 1 # End on current line
                    break
                idx+=1
                if idx > start+2000: logger.warning(f"No end brace L{start}?"); end_line_calc=start+20; break # Use calculated end line
            end = end_line_calc # Assign calculated end line to the return variable
        if start > 0 and end >= start and end <= len(lines)+1 : # Allow end to be one past last line index
            end_idx = min(end, len(lines)) # Cap end index for slicing
            return lines[start-1:end_idx], "\n".join(lines[start-1:end_idx]), start, end_idx
        return [],"",-1,-1

    def _process_method(self, node, comp, content):
        name=node.name; params, types=[],[]
        if node.parameters: [(params.append(f"{self._format_type(p.type)}{'...' if p.varargs else ''} {p.name}"), types.append(f"{self._format_type(p.type)}{'...' if p.varargs else ''}")) for p in node.parameters]
        sig_disp=f"({', '.join(params)})"; sig_key=f"({','.join(types)})"
        lines, _, start, end = self._extract_source_lines(node, content) # Don't store body on method object
        m = Method(name, sig_disp, "", comp); m.modifiers=list(node.modifiers or []); m.return_type=self._format_type(node.return_type) or "void"
        m.parameters=params; m.source_lines=lines; m.start_line=start; m.end_line=end; m.annotations=[f"@{a.name}" for a in node.annotations or []]
        m.exceptions=[self._format_type(e) for e in node.throws or []]
        if hasattr(node, 'body') and node.body:
            visitor=MethodCallVisitor(m)
            try:
                # Original code iterated over node.filter(javalang.tree.Statement)
                # Replicating using javalang.tree.Statement
                if isinstance(node.body, list):
                    # Wrap statement processing in a loop or list comprehension
                    for stmt in node.body:
                        # The original code used filter, which is more complex.
                        # A simple visit might be sufficient if MethodCallVisitor handles recursion.
                        # Let's try visiting each statement directly.
                        if stmt: # Check if statement is not None
                            visitor.visit(stmt)
                            # If deeper traversal needed within statements, visitor.visit needs to handle it.
                elif node.body: # If body is a single node (e.g., lambda)
                    visitor.visit(node.body)
            except Exception as e: logger.warning(f"Visitor {comp.name}.{name}: {e}")
            m.method_invocations = visitor.method_invocations # Assign collected invocations
        key = f"{comp.fully_qualified_name}.{name}{sig_key}"; self.methods[key]=m; comp.methods[f"{name}{sig_disp}"]=m

    def _process_constructor(self, node, comp, content):
        name="<init>"; disp_name=comp.name; params, types=[],[]
        if node.parameters: [(params.append(f"{self._format_type(p.type)}{'...' if p.varargs else ''} {p.name}"), types.append(f"{self._format_type(p.type)}{'...' if p.varargs else ''}")) for p in node.parameters]
        sig_disp=f"({', '.join(params)})"; sig_key=f"({','.join(types)})"
        lines, _, start, end = self._extract_source_lines(node, content)
        c = Method(name, sig_disp, "", comp); c.modifiers=list(node.modifiers or []); c.parameters=params
        c.source_lines=lines; c.start_line=start; c.end_line=end; c.annotations=[f"@{a.name}" for a in node.annotations or []]
        c.exceptions=[self._format_type(e) for e in node.throws or []]; c.return_type=comp.name
        if hasattr(node, 'body') and node.body:
            visitor=MethodCallVisitor(c)
            try:
                # Similar logic as _process_method for handling the body
                if isinstance(node.body, list):
                    for stmt in node.body:
                        if stmt:
                            visitor.visit(stmt)
                elif node.body:
                    visitor.visit(node.body)
            except Exception as e: logger.warning(f"Visitor constructor {disp_name}: {e}")
            c.method_invocations = visitor.method_invocations # Assign collected invocations
        key = f"{comp.fully_qualified_name}.{name}{sig_key}"; self.methods[key]=c; comp.methods[f"{disp_name}{sig_disp}"]=c # Use disp_name for constructor key in component

    def _build_component_relationships(self):
        logger.info("Building relationships...")
        for comp in self.components.values():
            try: # Add try block for safety
                if comp.extends: comp.extends = [self._resolve_type_name(e,comp) for e in (comp.extends if isinstance(comp.extends,list) else [comp.extends])] if comp.extends else None
                if comp.implements: comp.implements = [self._resolve_type_name(i,comp) for i in comp.implements]
            except Exception as e: logger.error(f"Relationship error for {comp.fully_qualified_name}: {e}")

    def _resolve_type_name(self, type_name, comp):
        # This method primarily deals with strings and component lookups, should be fine
        if not isinstance(type_name, str): return str(type_name)
        base, generic = type_name.split('<',1)[0], type_name[type_name.find('<'):] if '<' in type_name else ""
        if "." in base: return type_name
        curr = comp # Start search from current component outwards
        while curr: # Check inner classes in current and outer scopes
            inner_fqn_simple = f"{curr.fully_qualified_name}${base}"
            if inner_fqn_simple in self.components: return inner_fqn_simple + generic
            # Need to handle potentially missing components during lookup
            outer_fqn_base = '$'.join(curr.fully_qualified_name.split('$')[:-1]) if '$' in curr.fully_qualified_name else None
            curr = self.components.get(outer_fqn_base) if outer_fqn_base else None

        for imp in comp.imports:
            if imp.endswith(f".{base}"): return imp + generic
        if comp.package:
            fqn_pkg = f"{comp.package}.{base}";
            if fqn_pkg in self.components: return fqn_pkg + generic
        for imp in comp.imports:
            if imp.endswith(".*"):
                pkg=imp[:-1]; fqn_wild=f"{pkg}{base}"
                if fqn_wild in self.components: return fqn_wild + generic
                # Heuristic needs careful check if java packages are correctly resolved elsewhere or need explicit handling
                if pkg in ["java.util", "java.io", "java.net", "java.sql", "javax.sql", "java.time"]: return f"{pkg}{base}" + generic # Corrected heuristic string formatting

        # Java lang check needs adjustment if generics were intended
        # Making it simpler: return qualified name if it's a known java.lang or java.util type
        java_lang_types = {"String","Object","Integer","Boolean","Long","Double","Float","Character","Byte","Short","Void","Class","System","Math","Thread","Runnable","Exception","RuntimeException","Error","Throwable","Override","Deprecated","SuppressWarnings"}
        java_util_types = {"List","Map","Set","Collection","Optional"}

        if base in java_lang_types:
            return f"java.lang.{base}" + generic
        if base in java_util_types:
            return f"java.util.{base}" + generic

        return type_name # Unresolved

    def _build_call_graph(self):
        logger.info("Building call graph..."); self.call_graph = nx.DiGraph(); [self.call_graph.add_node(k) for k in self.methods]
        inv_c, res_c = 0, 0
        for key, method in self.methods.items():
            inv_c += len(method.method_invocations)
            for inv in method.method_invocations:
                try: # Add try block for robustness
                    # Ensure inv is a MethodInvocation node before accessing attributes
                    if isinstance(inv, MethodInvocation):
                        targets = self._resolve_method_invocation(inv, method.parent_component, method)
                        if targets:
                            res_c += len(targets)
                            for target_key in targets:
                                if target_key in self.call_graph and not self.call_graph.has_edge(key, target_key):
                                    self.call_graph.add_edge(key, target_key)
                                    # Make sure target_key exists before accessing self.methods[target_key]
                                    if target_key in self.methods:
                                        # Check if self.methods[target_key] is a Method object before appending
                                        target_method_obj = self.methods.get(target_key)
                                        if isinstance(target_method_obj, Method):
                                            method.calls.append(target_method_obj)
                                        else:
                                            logger.debug(f"Call graph target '{target_key}' not a valid Method object.")
                                    else:
                                        logger.debug(f"Call graph target '{target_key}' not found in self.methods map.")
                    else:
                        logger.debug(f"Item in method_invocations for {key} is not a MethodInvocation: {type(inv)}")

                except Exception as e:
                    member_name = getattr(inv, 'member', '?') if hasattr(inv, 'member') else '?'
                    logger.debug(f"Resolve error in {key} for invocation '{member_name}': {e}", exc_info=False) # Limit traceback noise

        logger.info(f"Call graph: {self.call_graph.number_of_nodes()} nodes, {self.call_graph.number_of_edges()} edges. ~{inv_c} invocs, ~{res_c} resolved.")


    def _resolve_method_invocation(self, inv, comp, method_context):
        # Ensure inv is valid MethodInvocation
        if not isinstance(inv, MethodInvocation):
            logger.warning(f"Attempted to resolve non-MethodInvocation: {type(inv)}")
            return []

        name=inv.member; qual=inv.qualifier; target_fqn=None
        if qual:
            # Use javalang's built-in string conversion for nodes if available, otherwise basic str()
            qual_s = str(qual)
            if qual_s == 'this': target_fqn = comp.fully_qualified_name
            elif qual_s == 'super':
                # Ensure comp.extends is resolved and accessible
                super_type = None
                if comp.extends:
                    # Handle both list and single string cases for extends
                    first_super = comp.extends[0] if isinstance(comp.extends, list) else comp.extends
                    # Resolve might return the simple name if it fails, handle that
                    resolved_super = self._resolve_type_name(first_super, comp)
                    # Check if resolution actually produced a FQN or just returned the input
                    if resolved_super != first_super or '.' in resolved_super:
                        super_type = resolved_super
                    else:
                        # Fallback or log warning if super couldn't be resolved
                        logger.debug(f"Could not fully resolve super type '{first_super}' for {comp.fully_qualified_name}")
                        super_type = "java.lang.Object" # Default assumption

                target_fqn = super_type if super_type else "java.lang.Object"

            else:
                # Check fields
                field_obj = comp.fields.get(qual_s)
                f_type = field_obj.field_type if field_obj else None

                # Check parameters if field not found
                if not f_type and method_context and hasattr(method_context, 'parameters'):
                    for p_sig in method_context.parameters: # p_sig is like "String myVar"
                        parts = p_sig.split()
                        if len(parts) > 1 and parts[-1] == qual_s:
                            f_type = parts[0].split('<')[0] # Get base type before generics
                            break

                # Local variable resolution is complex and generally skipped in static analysis like this.
                # If qualifier isn't a field or param, try resolving as a type name.

                if f_type:
                    target_fqn = self._resolve_type_name(f_type.split('<')[0], comp) # Resolve base type
                else:
                    # Try resolving qualifier as a class name
                    resolved = self._resolve_type_name(qual_s, comp)
                    # Check if resolution was successful (different from input or contains '.')
                    if resolved != qual_s or '.' in resolved:
                        # Check if it's a known component FQN
                        if resolved in self.components:
                            target_fqn = resolved
                        elif '.' in resolved: # Assume it's a FQN even if not in our components map (e.g., JDK)
                            target_fqn = resolved
                        # Else: resolution failed or returned simple name, likely cannot resolve target FQN
                    # else: qualifier is likely a local variable or unresolved simple name

        else: # No qualifier, method call on 'this'
            target_fqn = comp.fully_qualified_name

        if target_fqn:
            # Pass the original MethodInvocation object 'inv' to find_method_in_hierarchy
            return self._find_method_in_hierarchy(target_fqn, name, inv)

        # Log if target_fqn could not be determined
        # logger.debug(f"Could not determine target FQN for {name} in {comp.fully_qualified_name}.{method_context.name}")
        return []


    def _find_method_in_hierarchy(self, start_fqn, name, inv):
        matches=set(); queue=[start_fqn]; visited=set()
        # Use MethodInvocation 'inv' to get argument count
        arg_c = len(inv.arguments) if inv and hasattr(inv,'arguments') and inv.arguments is not None else -1

        while queue:
            fqn = queue.pop(0)
            if fqn in visited or not fqn: continue
            visited.add(fqn)

            # Check self.methods directly using startswith and name match
            # Iterate through potentially matching methods based on FQN prefix
            possible_keys = [k for k in self.methods if k.startswith(f"{fqn}.{name}(")]

            for m_key in possible_keys:
                m_obj = self.methods[m_key]
                # Check name again just to be sure (though startswith should cover it)
                if m_obj.name == name:
                    # Check arg count if available from invocation node
                    if arg_c == -1 or len(m_obj.parameters) == arg_c:
                        # Basic argument count matching. Type matching would be much more complex.
                        matches.add(m_key)
                    # else: Arg count mismatch

            # Add supertypes to queue if they exist and haven't been visited
            comp = self.components.get(fqn)
            if comp:
                supertypes = []
                if comp.extends:
                    # Ensure extends is a list for iteration
                    extends_list = comp.extends if isinstance(comp.extends, list) else [comp.extends]
                    supertypes.extend(extends_list)
                if comp.implements:
                    supertypes.extend(comp.implements)

                for st in supertypes:
                    # Resolve potentially simple names within the context of the current component
                    # Pass 'comp' as the context for resolving 'st'
                    resolved = self._resolve_type_name(st, comp) if st else None
                    if resolved and resolved not in visited:
                        queue.append(resolved)

            elif fqn and fqn.startswith("java."): # Stop hierarchy search for JDK unless Object needed
                # Add java.lang.Object only if we haven't found matches yet and haven't visited Object
                if fqn != "java.lang.Object" and not matches and "java.lang.Object" not in visited:
                    queue.append("java.lang.Object")

        # If still no matches, explicitly check Object methods if not visited and name matches standard ones
        if not matches and "java.lang.Object" not in visited and name in ["equals","hashCode","toString","getClass","notify","notifyAll","wait"]:
            # Construct potential keys for Object methods. This requires knowing their exact signatures.
            # This part is tricky without pre-populating Object methods or making assumptions.
            # Example: Object.equals(Object)
            if name == "equals" and arg_c == 1:
                obj_key = "java.lang.Object.equals(java.lang.Object)"
                # Check if this hypothetical key exists (it likely won't unless manually added)
                if obj_key in self.methods:
                    matches.add(obj_key)
            elif name == "toString" and arg_c == 0:
                obj_key = "java.lang.Object.toString()"
                if obj_key in self.methods:
                    matches.add(obj_key)
            # Add other Object methods similarly if needed...

            # If we don't have exact keys, we cannot reliably add matches here.
            pass # Avoid adding imprecise keys

        return list(matches)


    def _build_string_index(self):
        logger.info("Building string index..."); self.string_index = defaultdict(list)
        for fqn, comp in self.components.items():
            content="";
            try: # Corrected file reading with proper except blocks
                try:
                    with open(comp.file_path,'r',encoding='utf-8') as f: content=f.read()
                except UnicodeDecodeError:
                    logger.debug(f"{comp.file_path} not UTF-8, trying latin-1.")
                    with open(comp.file_path,'r',encoding='latin-1') as f: content=f.read()
            except Exception as e: logger.warning(f"Read failed {comp.file_path}: {e}"); continue

            try: # Process content
                # Regex for Java identifiers (simplified)
                words=set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', content))
                # Filter out keywords and very short words if desired
                # keywords = {'public', 'private', 'protected', ...}
                # words = {w for w in words if len(w)>2 and not w.isdigit() and w not in keywords}
                [ self.string_index[w.lower()].append({'fqn':fqn,'path':comp.file_path,'original':w}) for w in words if len(w)>2 and not w.isdigit() ]

                # Regex for string literals
                # Original: r'"((?:\\.|[^"\\])*)"' - This is good for standard strings
                # Consider adding support for text blocks `"""..."""` if needed
                literals=re.findall(r'"((?:\\.|[^"\\])*)"', content)
                [ self.string_index[lit.lower()].append({'fqn':fqn,'path':comp.file_path,'original':lit}) for lit in literals if len(lit)>1 ]

            except Exception as e: logger.error(f"Regex index error {comp.file_path}: {e}")
        logger.info(f"String index: {len(self.string_index)} unique terms/literals.")


    def _get_cache_key(self, path):
        try:
            return f"{path}:{os.path.getmtime(path)}"
        except:
            return f"{path}:err"

    def _save_to_cache(self):
        if not os.path.isdir(self.project_path): logger.error("Proj path invalid."); return
        file = os.path.join(self.cache_dir, "explorer_cache.pkl"); logger.info(f"Saving cache: {file}")
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
            except Exception as e:
                logger.error(f"Cache dir err: {e}"); return

        # Prepare data for pickling
        components_dict = {}
        for k, v in self.components.items():
            try:
                components_dict[k] = v.to_dict()
            except Exception as e:
                logger.error(f"Error serializing component {k}: {e}")
                # Optionally skip this component or handle error differently

        methods_dict = {}
        for k, v in self.methods.items():
            try:
                methods_dict[k] = v.to_dict()
            except Exception as e:
                logger.error(f"Error serializing method {k}: {e}")

        data = {
            'components': components_dict,
            'methods': methods_dict,
            'index_structure': self.index_structure,
            'package_structure': dict(self.package_structure),
            'string_index': {k:list(v) for k,v in self.string_index.items()}, # Convert defaultdict values
            'call_graph_edges': list(self.call_graph.edges()) if self.call_graph else [], # Handle empty graph
            'timestamp': time.time(),
            'parse_errors': self.parse_errors,
            'project_path': self.project_path
        }
        try:
            with open(file,'wb') as f: pickle.dump(data,f,pickle.HIGHEST_PROTOCOL)
            logger.info("Cache saved.")
        except Exception as e: logger.error(f"Cache save error: {e}")


    def _load_from_cache(self):
        file = os.path.join(self.cache_dir, "explorer_cache.pkl")
        if not os.path.isfile(file): logger.info("Cache file missing."); return False
        logger.info(f"Loading cache: {file}")
        try:
            with open(file, 'rb') as f: data = pickle.load(f)

            # --- Basic Cache Validation ---
            if data.get('project_path') != self.project_path:
                logger.warning("Cache project path mismatch."); return False

            cache_time=data.get('timestamp', 0)
            if cache_time == 0:
                logger.warning("Cache timestamp missing or invalid."); return False

            # --- Timestamp Validation ---
            latest_mod = 0; exts=('.java','.properties','.yml','.yaml','.xml')
            try:
                for r, ds, fs in os.walk(self.project_path):
                    # Filter ignored directories efficiently
                    ds[:] = [d for d in ds if d not in self.IGNORED_DIRS and not d.startswith('.')] # Also ignore hidden dirs generally
                    for f in fs:
                        # Check extension and get modification time
                        if f.endswith(exts):
                            try:
                                latest_mod = max(latest_mod, os.path.getmtime(os.path.join(r, f)))
                            except OSError: pass # Ignore errors like file not found during walk
            except Exception as e: logger.warning(f"Cache timestamp validation error: {e}."); return False

            if latest_mod > cache_time:
                logger.info(f"Project modified ({time.ctime(latest_mod)} > {time.ctime(cache_time)}), invalidating cache."); return False

            # --- Data Reconstruction ---
            logger.info("Cache valid. Loading data...");
            self.index_structure = data.get('index_structure', {})
            self.package_structure = defaultdict(list, data.get('package_structure', {}))
            self.string_index = defaultdict(list) # Rebuild defaultdict structure
            cached_string_index = data.get('string_index', {})
            for k, v_list in cached_string_index.items(): # Populate defaultdict
                self.string_index[k].extend(v_list)

            self.parse_errors = data.get('parse_errors', [])
            self.components = {} # Clear before load
            self.methods = {}    # Clear before load

            # Reconstruct components
            cached_components = data.get('components', {})
            if not cached_components: logger.warning("Cache contains no component data."); # Don't necessarily fail
            for fqn, cd in cached_components.items():
                try:
                    c=SpringBootComponent(cd['name'],cd['file_path'],cd['component_type'],cd['index'])
                    # Assign attributes safely using .get() with defaults
                    c.imports = cd.get('imports', [])
                    c.annotations = cd.get('annotations', [])
                    c.package = cd.get('package', '')
                    c.fully_qualified_name = cd.get('fully_qualified_name', fqn) # Use key as fallback FQN
                    c.extends = cd.get('extends') # Can be None, str, or list
                    c.implements = cd.get('implements', [])
                    c.generics = cd.get('generics', [])
                    # Fields and Methods will be linked later or are just stored by name in dict
                    # If full Field/Method objects were needed here, reconstruction would be more complex
                    self.components[fqn] = c
                except KeyError as e_key:
                    logger.error(f"Missing key {e_key} loading component {fqn} from cache.")
                    # Optionally skip this component or return False
                except Exception as e_comp:
                    logger.error(f"Error loading component {fqn} from cache: {e_comp}")

            # Reconstruct methods (linking to parent components)
            cached_methods = data.get('methods', {})
            if not cached_methods: logger.warning("Cache contains no method data."); # Don't necessarily fail
            for key, md in cached_methods.items():
                try:
                    # Determine parent FQN carefully
                    fqn_parts = key.split('.')
                    method_name_with_sig = fqn_parts[-1]
                    class_fqn_parts = fqn_parts[:-1]
                    method_name = md.get('name') # Get name from dict

                    # Heuristic for parent FQN based on constructor name convention
                    parent_fqn = '.'.join(class_fqn_parts)
                    if method_name == '<init>':
                        # Constructor's parent FQN might not include the innermost class name if it's part of key
                        # Example: com.example.Outer$Inner.<init>() -> parent FQN should be com.example.Outer$Inner
                        # This needs careful parsing based on how keys were constructed.
                        # Assuming the key format: package.Class.method(params) or package.Outer$Inner.method(params)
                        # The parent FQN should be everything before the last '.' separating class/method
                        pass # The parent_fqn derived above should be correct

                    parent_comp = self.components.get(parent_fqn)
                    if parent_comp:
                        m=Method(method_name, md['signature'], "", parent_comp) # No body needed
                        m.annotations = md.get('annotations', [])
                        m.modifiers = md.get('modifiers', [])
                        m.return_type = md.get('return_type')
                        m.parameters = md.get('parameters', [])
                        m.exceptions = md.get('exceptions', [])
                        m.start_line = md.get('start_line', 0)
                        m.end_line = md.get('end_line', 0)
                        # 'calls' and 'called_by' lists are rebuilt from the graph later
                        # 'source_lines' and 'method_invocations' are not typically cached

                        self.methods[key] = m
                        # Link method back to parent component's method dict
                        # Use the display signature format for the component's dict key
                        comp_method_key = f"{method_name}{md['signature']}"
                        if method_name == '<init>': # Adjust key for constructors in component dict
                            comp_method_key = f"{parent_comp.name}{md['signature']}" # Use class name + signature

                        parent_comp.methods[comp_method_key] = m

                    else:
                        logger.warning(f"Parent component '{parent_fqn}' not found for method '{key}' during cache load.")

                except KeyError as e_key:
                    logger.error(f"Missing key {e_key} loading method {key} from cache.")
                except Exception as e_meth:
                    logger.error(f"Error loading method {key} from cache: {e_meth}")

            # Reconstruct call graph
            self.call_graph = nx.DiGraph()
            # Add nodes *only* for methods successfully loaded
            [self.call_graph.add_node(k) for k in self.methods]
            edges = data.get('call_graph_edges', [])
            valid_edges = [(u, v) for u, v in edges if u in self.call_graph and v in self.call_graph]
            self.call_graph.add_edges_from(valid_edges)

            # Rebuild Method.calls and Method.called_by lists from graph
            for u, v in self.call_graph.edges():
                if u in self.methods and v in self.methods:
                    caller_method = self.methods[u]
                    callee_method = self.methods[v]
                    if callee_method not in caller_method.calls: # Avoid duplicates if loaded differently
                        caller_method.calls.append(callee_method)
                    if caller_method not in callee_method.called_by: # Avoid duplicates
                        callee_method.called_by.append(caller_method)

            logger.info(f"Loaded cache successfully. Graph: {self.call_graph.number_of_nodes()} nodes, {self.call_graph.number_of_edges()} edges.")
            return True

        except (EOFError, pickle.UnpicklingError, KeyError, AttributeError, TypeError) as e:
            logger.error(f"Cache file '{file}' is invalid or corrupt: {e}. Removing cache file.")
            try: os.remove(file)
            except OSError: pass
            return False
        except Exception as e:
            logger.error(f"Unexpected error loading cache: {type(e).__name__} - {e}.");
            # Optionally remove cache on any load error:
            # try: os.remove(file)
            # except OSError: pass
            return False

    # --- Public API Methods ---
    def search_method(self, name): return sorted([m for k,m in self.methods.items() if name.lower() in m.name.lower()], key=lambda m: m.parent_component.fully_qualified_name+m.name)
    def search_string(self, term): return self.string_index.get(term.lower(), []) # Already handles default

    def get_spring_components(self, comp_type=None):
        target_low = comp_type.lower() if comp_type else None; results = []
        known_low = {sa[1:].lower() for sa in self.SPRING_ANNOTATIONS}
        for fqn, comp in self.components.items():
            # Ensure component_type is a string before lowercasing
            curr_low = comp.component_type.lower() if isinstance(comp.component_type, str) else ""
            match = False
            is_spring_type = curr_low in known_low or any(a[1:].lower() in known_low for a in comp.annotations if isinstance(a, str) and len(a)>1)

            if target_low is None: # Get all Spring components
                if is_spring_type:
                    match = True
                    # Refine type if current type isn't a primary Spring stereotype but has one in annotations
                    if curr_low not in known_low:
                        for a in comp.annotations:
                            if isinstance(a, str) and len(a) > 1 and a[1:].lower() in known_low:
                                # Update component_type to the found Spring annotation (e.g., from 'Class' to 'Service')
                                comp.component_type = a[1:].capitalize() # Use canonical capitalization
                                break # Stop after finding the first Spring annotation
            # Specific type requested (handle RestController as Controller)
            elif target_low == curr_low or (target_low == "controller" and curr_low == "restcontroller"):
                match = True

            if match: results.append(comp)

        return sorted(results, key=lambda c: c.fully_qualified_name)


    def analyze_method_flow(self, key):
        m_obj, c_key = (self.methods[key], key) if key in self.methods else (None, None)
        if not m_obj:
            # Case-insensitive search if exact key fails
            key_lower = key.lower()
            matches = [(k, m) for k, m in self.methods.items() if key_lower in k.lower()]

            if len(matches) == 1:
                c_key, m_obj = matches[0]; logger.info(f"Found unique case-insensitive match for '{key}': {c_key}")
            elif len(matches) > 1:
                logger.warning(f"Ambiguous method key '{key}'. Found multiple potential matches.")
                # Return structure indicating multiple matches for CLI to handle
                return {"multiple_matches": [m[1] for m in matches]} # Return method objects
            else:
                logger.error(f"Method key '{key}' not found, even with case-insensitive search."); return None

        if not m_obj or not c_key: return None # Should not happen if logic above is correct

        # Attempt to read source lines if not already populated (and cache didn't populate them)
        src = m_obj.source_lines
        if not src and m_obj.start_line > 0 and m_obj.end_line > 0 and m_obj.parent_component:
            try:
                content=""; encs=['utf-8','latin-1','cp1252']; read_ok = False
                file_path = m_obj.parent_component.file_path
                if os.path.isfile(file_path):
                    for enc in encs:
                        try:
                            with open(file_path,'r',encoding=enc) as f: content=f.read(); read_ok = True; break;
                        except UnicodeDecodeError: continue
                        except Exception: break # Stop trying encodings on other errors
                    if read_ok and content:
                        lines = content.splitlines()
                        # Adjust slice indices, line numbers are 1-based, list indices 0-based
                        start_idx = m_obj.start_line - 1
                        end_idx = m_obj.end_line # Slice up to, but not including end_line index
                        if 0 <= start_idx < end_idx <= len(lines):
                            src = [l.rstrip() for l in lines[start_idx:end_idx]]
                            m_obj.source_lines = src # Store back if successfully read
                        else:
                            logger.warning(f"Invalid line numbers ({m_obj.start_line}-{m_obj.end_line}) for file {file_path}")
                else:
                    logger.warning(f"Source file not found for method {c_key}: {file_path}")

            except Exception as e: logger.warning(f"Source code read failed for {c_key}: {e}")

        # Build result dictionary
        result = {
            "method": f"{m_obj.parent_component.name}.{m_obj.name}{m_obj.signature}",
            "method_key": c_key,
            "component": m_obj.parent_component.name,
            "component_type": m_obj.parent_component.component_type,
            "signature": m_obj.signature,
            "source": src, # Use potentially loaded source
            "calls": self._get_method_calls(c_key),
            "called_by": self._get_method_callers(c_key),
            "annotations": m_obj.annotations
        }
        return result


    def _get_method_calls(self, key, depth=0, max_d=3, visited=None):
        if visited is None: visited=set();
        if depth>max_d or key in visited or key not in self.call_graph: return []
        visited.add(key); calls=[]
        # Ensure successors() is called only if key is in graph
        successors = list(self.call_graph.successors(key)) if key in self.call_graph else []
        for target in successors:
            if target in self.methods:
                m=self.methods[target]; info = {"method":f"{m.parent_component.name}.{m.name}{m.signature}", "method_key":target, "component":m.parent_component.name, "component_type":m.parent_component.component_type, "children":[]}
                if depth<max_d:
                    # Pass a copy of visited to avoid sibling calls interfering
                    info["children"]=self._get_method_calls(target, depth+1, max_d, visited.copy())
                calls.append(info)
        return sorted(calls, key=lambda x:x['method']) # Sort by method string


    def _get_method_callers(self, key, depth=0, max_d=1, visited=None):
        if visited is None: visited=set();
        if depth>max_d or key in visited or key not in self.call_graph: return []
        visited.add(key); callers=[]
        # Ensure predecessors() is called only if key is in graph
        predecessors = list(self.call_graph.predecessors(key)) if key in self.call_graph else []
        for source in predecessors:
            if source in self.methods:
                m=self.methods[source]; info={"method":f"{m.parent_component.name}.{m.name}{m.signature}", "method_key":source, "component":m.parent_component.name, "component_type":m.parent_component.component_type, "parents":[]}
                if depth<max_d:
                    # Pass a copy of visited
                    info["parents"]=self._get_method_callers(source, depth+1, max_d, visited.copy())
                callers.append(info)
        return sorted(callers, key=lambda x:x['method']) # Sort by method string


    def print_project_structure(self):
        # Uses colored from utils
        print(colored(self.index_structure.get('name', 'Project Root'), Colors.BOLD))
        self._print_node_ascii(self.index_structure.get('children', []), "")

    def _print_node_ascii(self, children, prefix):
        # Uses colored from utils
        s_children = sorted(children, key=lambda x: (x.get('type')!='directory', x.get('name')))
        ptrs = ['├─ ']*(len(s_children)-1) + ['└─ '] if s_children else []
        for i, child in enumerate(s_children):
            name=child.get('name','?'); n_type=child.get('type','?'); index=child.get('index','?')
            ptr=ptrs[i]; ext = '│  ' if i<len(s_children)-1 else '   '
            # Use Colors constants for coloring
            n_color = Colors.WHITE # Default
            if n_type == 'directory': n_color = Colors.BRIGHT_BLUE
            elif n_type == 'java': n_color = Colors.BRIGHT_GREEN
            elif n_type in ['config','xml','properties','yml','yaml']: n_color = Colors.BRIGHT_YELLOW
            n_str = colored(name, n_color)

            print(f"{prefix}{ptr}{colored(index, Colors.BRIGHT_MAGENTA)} {n_str}")
            if child.get('type') == 'directory':
                # Ensure children exist before recursing
                if 'children' in child:
                    self._print_node_ascii(child.get('children', []), prefix+ext)


    def get_parse_errors(self): return self.parse_errors

    def get_node_by_index(self, index):
        if not isinstance(index, str) or not index: return None
        if index=='0': return self.index_structure
        parts=index.split('.'); node=self.index_structure
        try:
            current_node = node # Start with root
            for part in parts:
                idx=int(part) # Convert part to integer index
                children=current_node.get('children',[])
                if 0 < idx <= len(children):
                    current_node = children[idx-1] # 1-based index from user, 0-based list access
                else:
                    logger.warning(f"Index part {idx} is out of bounds for node {current_node.get('name', '?')}"); return None
            return current_node # Return the final node found
        except ValueError:
            logger.error(f"Invalid index format: '{index}'. Parts must be integers."); return None
        except Exception as e: logger.error(f"Error getting node by index '{index}': {e}"); return None


    def convert_files_to_txt(self, node_index, target_dir=None):
        node = self.get_node_by_index(node_index)
        if not node: return False, f"Node with index '{node_index}' not found"

        # Determine files to convert based on node type
        files_to_convert = []
        if node.get('type') == 'directory':
            files_to_convert = self._get_all_files_in_node(node)
        elif node.get('type') != 'directory' and 'path' in node: # Check it's a file node with a path
            files_to_convert = [node]
        else:
            return False, f"Node '{node_index}' is not a directory or a file node with a path."

        if not files_to_convert: return True, "No files found within the specified node to convert."

        # Prepare output directory
        base_out = None
        if target_dir:
            base_out = os.path.abspath(target_dir)
            if not os.path.exists(base_out):
                try: os.makedirs(base_out); logger.info(f"Created output directory: {base_out}")
                except OSError as e: return False, f"Cannot create output directory '{base_out}': {e}"
            elif not os.path.isdir(base_out):
                return False, f"Specified output path '{base_out}' exists but is not a directory."

        count, errors = 0, []
        for f_node in files_to_convert:
            if 'path' in f_node and os.path.isfile(f_node['path']): # Double check it's a file path
                ok, msg_or_target = self._convert_single_file_to_txt(f_node['path'], base_out)
                if ok: count += 1
                else: errors.append(f"{os.path.basename(f_node['path'])}: {msg_or_target}")
            else:
                errors.append(f"Skipped invalid file node: {f_node.get('name', '?')} (Index: {f_node.get('index', '?')})")


        if not errors: return True, f"Successfully converted {count} file(s)."
        else: return False, f"Converted {count} file(s) with {len(errors)} error(s):\n - "+"\n - ".join(errors)


    def _get_all_files_in_node(self, node):
        files = []
        # If the node itself is a file, add it (and don't recurse)
        if node.get('type') != 'directory' and 'path' in node and os.path.isfile(node['path']):
            files.append(node)
        # If it's a directory, iterate through children
        elif node.get('type') == 'directory':
            for c in node.get('children', []):
                files.extend(self._get_all_files_in_node(c)) # Recursively call
        return files

    def _convert_single_file_to_txt(self, src_path, base_out_dir):
        try:
            # Determine target path
            if base_out_dir:
                # Create relative path structure within the output directory
                rel_path = os.path.relpath(src_path, self.project_path)
                target_path = os.path.join(base_out_dir, rel_path + '.txt')
                os.makedirs(os.path.dirname(target_path), exist_ok=True) # Ensure target subdirectory exists
            else:
                # Save next to the original file
                target_path = src_path + '.txt'

            # Read source file with multiple encoding attempts
            content = ""; encs = ['utf-8', 'latin-1', 'cp1252']; read_ok = False
            for enc in encs:
                try:
                    with open(src_path, 'r', encoding=enc) as f_in: content = f_in.read(); read_ok = True; break
                except UnicodeDecodeError: continue
                except Exception as e_read: raise IOError(f"Read failed ({enc}): {e_read}") from e_read # Chain exception
            if not read_ok: raise IOError(f"Could not read file with tested encodings: {src_path}")

            # Write target file in UTF-8
            with open(target_path, 'w', encoding='utf-8') as f_out: f_out.write(content)

            return True, target_path # Return success and target path

        except Exception as e:
            logger.error(f"Error converting file '{os.path.basename(src_path)}' to txt: {e}")
            return False, str(e) # Return failure and error message


    def interactive_structure_browser(self):
        # Uses utils: clear_screen, colored, Colors, menu_option, error, warning, info
        # Calls self.get_node_by_index, self.convert_files_to_txt
        node = self.index_structure
        while True:
            clear_screen(); print(colored(f"Current: {node.get('path', 'N/A')}", Colors.BOLD))
            print(colored(f"{'Index':<15} {'Type':<5} {'Name'}", Colors.UNDERLINE))

            # Option to go up
            if node != self.index_structure:
                # Find parent index carefully
                parent_idx = '0' # Default to root if only one part
                if '.' in node.get('index', ''):
                    parent_idx = '.'.join(node['index'].split('.')[:-1])
                print(f"{colored('..', Colors.BRIGHT_YELLOW):<15} {'Dir':<5} {'Go up'}")


            children = sorted(node.get('children', []), key=lambda x: (x.get('type')!='directory', x.get('name')))
            for c in children:
                n,t,i = c.get('name','?'), c.get('type','?'), c.get('index','?')
                ts = t.capitalize()[:4] if t else '????'; ns=n
                # Use Colors constants
                if t=='directory': ns=colored(n,Colors.BRIGHT_BLUE); ts=colored('Dir',Colors.BRIGHT_BLUE)
                elif t=='java': ns=colored(n,Colors.BRIGHT_GREEN); ts=colored('Java',Colors.BRIGHT_GREEN)
                elif t in ['config','xml','properties','yml','yaml']: ns=colored(n,Colors.BRIGHT_YELLOW); ts=colored('Conf',Colors.BRIGHT_YELLOW)
                else: ts=colored(ts, Colors.BRIGHT_CYAN) # Default coloring for other types
                print(f"{colored(i, Colors.BRIGHT_MAGENTA):<15} {ts:<5} {ns}")

            print("\nActions:"); print(colored("Enter index to navigate | c INDEX [-o DIR] | v INDEX | q", Colors.BRIGHT_CYAN))
            choice = input(colored("\nEnter index/action: ", Colors.BOLD)).strip()

            if choice.lower() == 'q': break
            elif choice == '..': # Go up
                if node != self.index_structure:
                    parent_idx = '0'
                    if '.' in node.get('index', ''):
                        parent_idx = '.'.join(node['index'].split('.')[:-1])
                    parent_node = self.get_node_by_index(parent_idx)
                    node = parent_node if parent_node else self.index_structure # Go to parent or root if lookup fails

            elif choice.lower().startswith('c '): # Convert
                parts=choice.split(); idx_to_convert=parts[1] if len(parts)>1 else None; t_dir=None
                if '-o' in parts:
                    try: t_dir=parts[parts.index('-o')+1]
                    except IndexError: print(error("Missing directory path after -o option")); time.sleep(1); continue
                if not idx_to_convert: print(error("Missing index for conversion command 'c'")); time.sleep(1); continue

                print(info(f"Attempting to convert node '{idx_to_convert}'..."));
                ok, msg = self.convert_files_to_txt(idx_to_convert, t_dir)
                print(success(msg) if ok else error(msg)); input(colored("Press Enter to continue...", Colors.BOLD))

            elif choice.lower().startswith('v '): # View
                idx_to_view = choice[2:].strip()
                if not idx_to_view: print(error("Missing index for view command 'v'")); time.sleep(1); continue

                f_node = self.get_node_by_index(idx_to_view)
                if not f_node: print(error(f"Index '{idx_to_view}' not found.")); time.sleep(1); continue
                if f_node.get('type')=='directory': print(warning("Cannot view a directory. Enter index of a file.")); time.sleep(1); continue
                if 'path' not in f_node or not os.path.isfile(f_node['path']): print(error(f"Node {idx_to_view} is not a valid file path.")); time.sleep(1); continue

                try:
                    clear_screen(); print(colored(f"Viewing File: {f_node['path']}",Colors.BOLD)); print(colored("="*80, Colors.BRIGHT_CYAN))
                    content = ""; page_size=os.get_terminal_size().lines - 5 if hasattr(os, 'get_terminal_size') else 30 # Adjust page size
                    read_ok = False; encs = ['utf-8','latin-1','cp1252']
                    for enc in encs:
                        try:
                            with open(f_node['path'],'r',encoding=enc) as f: content=f.read(); read_ok=True; break
                        except UnicodeDecodeError: continue
                        except Exception as e_r: raise IOError(f"Read error ({enc}): {e_r}") from e_r # Chain exception
                    if not read_ok: raise IOError("Cannot read file with tested encodings")

                    lines = content.splitlines(); line_count = len(lines)
                    for page_start in range(0, line_count, page_size):
                        page_end = min(page_start + page_size, line_count)
                        # Display lines for the current page
                        print("\n".join(lines[page_start:page_end]))

                        if page_end < line_count: # If not the last page
                            cont_prompt = input(colored(f"--More-- (Lines {page_start+1}-{page_end}/{line_count}) (Enter/q):",Colors.BRIGHT_YELLOW))
                            if cont_prompt.lower() == 'q': break
                        else: # Last page
                            print(colored("\n--End of File--", Colors.BRIGHT_YELLOW))

                    print(colored("="*80, Colors.BRIGHT_CYAN)); input(colored("Press Enter to return...", Colors.BOLD))
                except Exception as e: print(error(f"Error viewing file: {e}")); time.sleep(2)

            else: # Try to navigate using the input as an index
                target_node = self.get_node_by_index(choice)
                if target_node and target_node.get('type') == 'directory':
                    node = target_node # Navigate into directory
                elif target_node: # It's a file or other non-directory node
                    print(warning(f"'{choice}' is not a directory. Use 'v {choice}' to view or 'c {choice}' to convert.")); time.sleep(1.5)
                else: # Invalid index or command
                    print(error(f"Invalid index or command: '{choice}'")); time.sleep(1)

    def clear_cache(self):
        # Uses utils: logger, info, error
        if os.path.exists(self.cache_dir):
            try:
                shutil.rmtree(self.cache_dir)
                os.makedirs(self.cache_dir) # Recreate empty dir
                logger.info("Cache cleared successfully.")
                # Reset internal state as if freshly initialized
                self.__init__(self.project_path) # Call __init__ again
                # Note: This clears components, methods etc. Analysis needed again.
                return True, "Cache cleared. Re-analysis is required."
            except Exception as e:
                logger.error(f"Failed to clear cache directory '{self.cache_dir}': {e}");
                return False, f"Error clearing cache: {e}"
        else:
            logger.info("Cache directory not found, nothing to clear.")
            # Consider if re-init is still desired even if no dir existed
            # self.__init__(self.project_path) # Optionally re-init anyway
            return True, "Cache directory not found."


    def debug_annotations(self):
        # Uses defaultdict
        # Collects annotations from components, methods, fields
        all_annotations = set()

        for comp in self.components.values():
            if hasattr(comp, 'annotations'):
                all_annotations.update(a for a in comp.annotations if isinstance(a, str))
            if hasattr(comp, 'fields'):
                for field in comp.fields.values():
                    if hasattr(field, 'annotations'):
                        all_annotations.update(a for a in field.annotations if isinstance(a, str))

        for method in self.methods.values():
            if hasattr(method, 'annotations'):
                all_annotations.update(a for a in method.annotations if isinstance(a, str))

        # Summarize component types
        component_summary = defaultdict(int)
        for comp in self.components.values():
            comp_type_str = comp.component_type if isinstance(comp.component_type, str) else "Unknown"
            component_summary[comp_type_str] += 1

        return sorted(list(all_annotations)), dict(component_summary)


    # --- Patch Creation Method ---
    def create_patch_from_local_changes(self, output_patch_file, include_binary=False):
        # Uses utils: logger, info, warning, error
        logger.info(f"Attempting to create patch file at: {output_patch_file}")
        git_dir = os.path.join(self.project_path, '.git')
        if not os.path.isdir(git_dir):
            msg = f"Project path is not a Git repository: {self.project_path}"; logger.error(msg); return False, msg

        out_abs = os.path.abspath(output_patch_file)
        out_dir = os.path.dirname(out_abs)
        if not os.path.isdir(out_dir):
            try: os.makedirs(out_dir); logger.info(f"Created output directory: {out_dir}")
            except OSError as e: msg=f"Cannot create output directory '{out_dir}': {e}"; logger.error(msg); return False, msg

        # Prepare git diff command
        cmd = ['git', '-C', self.project_path, 'diff'] # Use -C to specify repo path safely
        if include_binary: cmd.append('--binary')
        cmd.append('HEAD') # Diff against the index (staged changes) and working tree vs HEAD

        try:
            logger.info(f"Running git command: {' '.join(cmd)}")
            # Run git diff against HEAD
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False) # Don't check=True yet

            # Check if 'HEAD' exists (e.g., in a new repo with no commits)
            head_error = False
            if res.returncode != 0 and res.stderr and ("fatal: ambiguous argument 'HEAD'" in res.stderr or "fatal: bad revision 'HEAD'" in res.stderr):
                logger.warning("Git HEAD revision not found (likely new repo or error). Trying diff against empty tree.")
                head_error = True
                # Diff against the magical empty tree object hash for "everything added"
                cmd[-1] = '4b825dc642cb6eb9a060e54bf8d69288fbee4904' # Git's empty tree hash
                logger.info(f"Retrying git command: {' '.join(cmd)}")
                res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)

            # Check final result after potential retry
            # Git diff returns 0 if no changes, 1 if changes found. Other codes are errors.
            if res.returncode not in [0, 1]:
                error_context = "during initial diff" if not head_error else "during empty tree diff retry"
                msg=f"Git diff command failed {error_context} (Return Code: {res.returncode})."
                logger.error(f"{msg}\nGit stderr:\n{res.stderr.strip()}")
                return False, f"{msg} Git Error: {res.stderr.strip()}"

            patch_content = res.stdout

            # Write the patch file
            try:
                with open(out_abs, 'w', encoding='utf-8') as f:
                    f.write(patch_content)

                # Determine success message based on content and return code
                if not patch_content and res.returncode == 0:
                    msg = f"Patch created successfully (no changes detected): {out_abs}"
                elif not patch_content and res.returncode == 1:
                    # This case is unusual but possible if git diff has weird output
                    msg = f"Patch created (empty content, but git indicated changes): {out_abs}"
                    logger.warning(msg)
                else: # Has content
                    msg = f"Patch created successfully: {out_abs}"

                logger.info(msg); return True, msg

            except IOError as e:
                msg=f"Error writing patch file '{out_abs}': {e}"; logger.error(msg); return False, msg

        except FileNotFoundError:
            # This occurs if 'git' command is not found in PATH
            msg = "'git' command not found. Please ensure Git is installed and accessible in your system's PATH."; logger.error(msg); return False, msg
        except Exception as e:
            # Catch any other unexpected exceptions during subprocess execution or handling
            msg = f"An unexpected error occurred during patch creation: {e}"; logger.error(msg, exc_info=True); return False, msg
    # --- End SpringBootExplorer ---
