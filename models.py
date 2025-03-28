# spring_explorer/models.py
import javalang
from javalang.tree import MethodInvocation

# --- Data Classes ---
class SpringBootComponent:
    def __init__(self, name, file_path, component_type, index):
        self.name=name; self.file_path=file_path; self.component_type=component_type; self.index=index
        self.methods={}; self.fields={}; self.imports=[]; self.extends=None; self.implements=[]
        self.annotations=[]; self.package=""; self.inner_classes=[]; self.generics=[]; self.fully_qualified_name=""
    def __str__(self): return f"{self.index}: {self.component_type} - {self.name}"
    def to_dict(self): return {k: (v.to_dict() if hasattr(v,'to_dict') else ({n:m.to_dict() for n,m in v.items()} if k=='methods' else ({n:str(f) for n,f in v.items()} if k=='fields' else v))) for k, v in self.__dict__.items() if k != 'source_code'}

class Field:
    def __init__(self, name, field_type, modifiers, parent_component):
        self.name=name; self.field_type=field_type; self.modifiers=modifiers; self.parent_component=parent_component; self.annotations=[]
    def __str__(self): return f"{' '.join(self.modifiers)} {self.field_type} {self.name}"

class Method:
    def __init__(self, name, signature, body, parent_component):
        self.name=name; self.signature=signature; self.parent_component=parent_component # Body not stored
        self.calls=[]; self.called_by=[]; self.annotations=[]; self.modifiers=[]; self.return_type=None
        self.parameters=[]; self.exceptions=[]; self.start_line=0; self.end_line=0
        self.source_lines=[]; self.method_invocations=[] # Raw nodes
    def __str__(self): return f"{self.parent_component.name}.{self.name}{self.signature}"
    def to_dict(self): return {k:v for k,v in {'name': self.name, 'signature': self.signature, 'annotations': self.annotations, 'modifiers': self.modifiers, 'return_type': str(self.return_type) if self.return_type else None, 'parameters': self.parameters, 'exceptions': self.exceptions, 'start_line': self.start_line, 'end_line': self.end_line, 'calls': [str(c) for c in self.calls], 'called_by': [str(c) for c in self.called_by]}.items()}

class MethodCallVisitor:
    def __init__(self, method): self.method=method; self.calls=[]; self.method_invocations=[]
    def visit(self, node):
        if isinstance(node, MethodInvocation):
            if node not in self.method_invocations: self.method_invocations.append(node)
            q = node.qualifier or "this"; n = node.member; t = (str(q), n) # Convert qualifier node/str to str
            if t not in self.calls: self.calls.append(t)
        # Recurse using filter
        # Note: javalang's filter might not work exactly as intended recursively here.
        # A full AST traversal might be needed for deep calls, but we keep original logic.
        try:
            # Attempt filter, acknowledging potential limitations
            for _, child in node.filter(MethodInvocation):
                if isinstance(child, MethodInvocation): # Double check type
                    if child not in self.method_invocations: self.method_invocations.append(child)
                    cq = child.qualifier or "this"; cn = child.member; ct = (str(cq), cn)
                    if ct not in self.calls: self.calls.append(ct)
        except AttributeError: # Handle nodes without filter or other issues gracefully
            pass
        except Exception: # Catch unexpected errors during traversal
            # Consider logging this if it happens frequently
            pass

# --- End Data Classes ---
