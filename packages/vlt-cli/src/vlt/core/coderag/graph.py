"""Code graph builder using tree-sitter.

Extracts code relationships (imports, calls, inheritance) from parsed AST trees.
Supports Python, TypeScript, and JavaScript.
"""

from typing import Dict, List, Tuple, Optional, Set, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from tree_sitter import Tree, Node as TSNode
else:
    try:
        from tree_sitter import Tree, Node as TSNode
    except ImportError:
        Tree = None  # type: ignore
        TSNode = None  # type: ignore

from vlt.core.models import NodeType, EdgeType


@dataclass
class CodeNode:
    """Node in code dependency graph (dict form, not SQLAlchemy)."""
    id: str  # Qualified name (e.g., "module.Class.method")
    project_id: str
    file_path: str
    node_type: str  # NodeType enum value as string
    name: str
    signature: Optional[str] = None
    lineno: Optional[int] = None
    docstring: Optional[str] = None


@dataclass
class CodeEdge:
    """Edge in code dependency graph (dict form, not SQLAlchemy)."""
    source_id: str  # Qualified name
    target_id: str  # Qualified name
    edge_type: str  # EdgeType enum value as string
    lineno: Optional[int] = None
    project_id: str = ""


def build_graph(
    parsed_files: Dict[str, Tuple["Tree", str, str]],
    project_id: str
) -> Tuple[List[CodeNode], List[CodeEdge]]:
    """Build code dependency graph from parsed files.

    Args:
        parsed_files: Dict of file_path -> (tree, source_code, language)
        project_id: Project ID for all nodes/edges

    Returns:
        Tuple of (nodes, edges) as dicts (not SQLAlchemy models)
    """
    nodes: List[CodeNode] = []
    edges: List[CodeEdge] = []

    # Track all symbol definitions for qualified names
    symbol_registry: Dict[str, str] = {}  # name -> qualified_name

    # First pass: extract all nodes (symbols)
    for file_path, (tree, source_code, language) in parsed_files.items():
        file_nodes = extract_nodes(tree, source_code, language, file_path, project_id)
        nodes.extend(file_nodes)

        # Register symbols for edge resolution
        for node in file_nodes:
            symbol_registry[node.name] = node.id
            # Also register short name (e.g., "method" in addition to "Class.method")
            if "." in node.id:
                short_name = node.id.split(".")[-1]
                if short_name not in symbol_registry:
                    symbol_registry[short_name] = node.id

    # Second pass: extract edges (relationships)
    for file_path, (tree, source_code, language) in parsed_files.items():
        file_edges = extract_edges(
            tree, source_code, language, file_path, project_id, symbol_registry
        )
        edges.extend(file_edges)

    return nodes, edges


def extract_nodes(
    tree: "Tree",
    source_code: str,
    language: str,
    file_path: str,
    project_id: str
) -> List[CodeNode]:
    """Extract code nodes from a single file's AST.

    Supports Python, TypeScript, JavaScript.
    """
    nodes: List[CodeNode] = []

    if language == "python":
        nodes.extend(_extract_python_nodes(tree, source_code, file_path, project_id))
    elif language in ("typescript", "javascript"):
        nodes.extend(_extract_ts_js_nodes(tree, source_code, file_path, project_id, language))

    return nodes


def extract_edges(
    tree: "Tree",
    source_code: str,
    language: str,
    file_path: str,
    project_id: str,
    symbol_registry: Dict[str, str]
) -> List[CodeEdge]:
    """Extract code edges (relationships) from a single file's AST."""
    edges: List[CodeEdge] = []

    if language == "python":
        edges.extend(_extract_python_edges(tree, source_code, file_path, project_id, symbol_registry))
    elif language in ("typescript", "javascript"):
        edges.extend(_extract_ts_js_edges(tree, source_code, file_path, project_id, symbol_registry))

    return edges


# ============================================================================
# Python Extraction
# ============================================================================

def _extract_python_nodes(
    tree: Tree,
    source_code: str,
    file_path: str,
    project_id: str
) -> List[CodeNode]:
    """Extract Python nodes: functions, classes, methods."""
    nodes: List[CodeNode] = []
    source_lines = source_code.split("\n")

    # Module name from file path
    module_name = file_path.replace("/", ".").replace(".py", "").lstrip(".")

    # Query for top-level and nested definitions
    query_str = """
    (module
      (class_definition
        name: (identifier) @class_name
        body: (_)* @class_body
      ) @class_def
    )
    (module
      (function_definition
        name: (identifier) @func_name
      ) @func_def
    )
    """

    root = tree.root_node

    # Extract classes
    for node in _traverse(root):
        if node.type == "class_definition":
            class_name_node = _find_child_by_field(node, "name")
            if class_name_node:
                class_name = _get_text(class_name_node, source_code)
                qualified_name = f"{module_name}.{class_name}"

                docstring = _extract_docstring(node, source_code)

                nodes.append(CodeNode(
                    id=qualified_name,
                    project_id=project_id,
                    file_path=file_path,
                    node_type=NodeType.CLASS.value,
                    name=class_name,
                    signature=f"class {class_name}",
                    lineno=node.start_point[0] + 1,
                    docstring=docstring
                ))

                # Extract methods within class
                for child in _traverse(node):
                    if child.type == "function_definition" and child.parent.type in ("block", "class_definition"):
                        method_name_node = _find_child_by_field(child, "name")
                        if method_name_node:
                            method_name = _get_text(method_name_node, source_code)
                            method_qualified = f"{qualified_name}.{method_name}"

                            params = _extract_function_params(child, source_code)
                            method_docstring = _extract_docstring(child, source_code)

                            nodes.append(CodeNode(
                                id=method_qualified,
                                project_id=project_id,
                                file_path=file_path,
                                node_type=NodeType.METHOD.value,
                                name=method_name,
                                signature=f"def {method_name}({params})",
                                lineno=child.start_point[0] + 1,
                                docstring=method_docstring
                            ))

        # Top-level functions (not inside classes)
        elif node.type == "function_definition" and node.parent.type == "module":
            func_name_node = _find_child_by_field(node, "name")
            if func_name_node:
                func_name = _get_text(func_name_node, source_code)
                qualified_name = f"{module_name}.{func_name}"

                params = _extract_function_params(node, source_code)
                docstring = _extract_docstring(node, source_code)

                nodes.append(CodeNode(
                    id=qualified_name,
                    project_id=project_id,
                    file_path=file_path,
                    node_type=NodeType.FUNCTION.value,
                    name=func_name,
                    signature=f"def {func_name}({params})",
                    lineno=node.start_point[0] + 1,
                    docstring=docstring
                ))

    return nodes


def _extract_python_edges(
    tree: Tree,
    source_code: str,
    file_path: str,
    project_id: str,
    symbol_registry: Dict[str, str]
) -> List[CodeEdge]:
    """Extract Python edges: imports, calls, inheritance."""
    edges: List[CodeEdge] = []
    root = tree.root_node
    module_name = file_path.replace("/", ".").replace(".py", "").lstrip(".")

    # Track current scope for qualified names
    scope_stack: List[str] = [module_name]

    # Extract import edges
    for node in _traverse(root):
        # Import statements: import foo
        if node.type == "import_statement":
            for name_node in node.children:
                if name_node.type == "dotted_name":
                    imported = _get_text(name_node, source_code)
                    edges.append(CodeEdge(
                        source_id=module_name,
                        target_id=imported,
                        edge_type=EdgeType.IMPORTS.value,
                        lineno=node.start_point[0] + 1,
                        project_id=project_id
                    ))

        # Import from: from foo import bar
        elif node.type == "import_from_statement":
            module_node = _find_child_by_type(node, "dotted_name")
            if module_node:
                imported_module = _get_text(module_node, source_code)
                edges.append(CodeEdge(
                    source_id=module_name,
                    target_id=imported_module,
                    edge_type=EdgeType.IMPORTS.value,
                    lineno=node.start_point[0] + 1,
                    project_id=project_id
                ))

        # Inheritance: class Foo(Bar)
        elif node.type == "class_definition":
            class_name_node = _find_child_by_field(node, "name")
            argument_list = _find_child_by_type(node, "argument_list")

            if class_name_node and argument_list:
                class_name = _get_text(class_name_node, source_code)
                source_qual = f"{module_name}.{class_name}"

                for arg in argument_list.children:
                    if arg.type == "identifier":
                        base_name = _get_text(arg, source_code)
                        target_qual = symbol_registry.get(base_name, base_name)

                        edges.append(CodeEdge(
                            source_id=source_qual,
                            target_id=target_qual,
                            edge_type=EdgeType.INHERITS.value,
                            lineno=node.start_point[0] + 1,
                            project_id=project_id
                        ))

        # Function/method calls
        elif node.type == "call":
            function_node = _find_child_by_field(node, "function")
            if function_node:
                # Determine current scope
                enclosing = _find_enclosing_definition(node)
                if enclosing:
                    source_qual = _get_qualified_name(enclosing, source_code, module_name)
                else:
                    source_qual = module_name

                # Extract called function name
                called_name = _get_text(function_node, source_code)

                # Resolve to qualified name if possible
                target_qual = symbol_registry.get(called_name, called_name)

                edges.append(CodeEdge(
                    source_id=source_qual,
                    target_id=target_qual,
                    edge_type=EdgeType.CALLS.value,
                    lineno=node.start_point[0] + 1,
                    project_id=project_id
                ))

    return edges


# ============================================================================
# TypeScript/JavaScript Extraction
# ============================================================================

def _extract_ts_js_nodes(
    tree: Tree,
    source_code: str,
    file_path: str,
    project_id: str,
    language: str
) -> List[CodeNode]:
    """Extract TypeScript/JavaScript nodes."""
    nodes: List[CodeNode] = []
    module_name = file_path.replace("/", ".").replace(f".{language}", "").lstrip(".")

    root = tree.root_node

    for node in _traverse(root):
        # Class declarations
        if node.type == "class_declaration":
            name_node = _find_child_by_field(node, "name")
            if name_node:
                class_name = _get_text(name_node, source_code)
                qualified_name = f"{module_name}.{class_name}"

                nodes.append(CodeNode(
                    id=qualified_name,
                    project_id=project_id,
                    file_path=file_path,
                    node_type=NodeType.CLASS.value,
                    name=class_name,
                    signature=f"class {class_name}",
                    lineno=node.start_point[0] + 1
                ))

                # Extract methods
                for child in node.children:
                    if child.type == "method_definition":
                        method_name_node = _find_child_by_field(child, "name")
                        if method_name_node:
                            method_name = _get_text(method_name_node, source_code)
                            method_qualified = f"{qualified_name}.{method_name}"

                            nodes.append(CodeNode(
                                id=method_qualified,
                                project_id=project_id,
                                file_path=file_path,
                                node_type=NodeType.METHOD.value,
                                name=method_name,
                                signature=f"{method_name}()",
                                lineno=child.start_point[0] + 1
                            ))

        # Function declarations
        elif node.type == "function_declaration":
            name_node = _find_child_by_field(node, "name")
            if name_node:
                func_name = _get_text(name_node, source_code)
                qualified_name = f"{module_name}.{func_name}"

                nodes.append(CodeNode(
                    id=qualified_name,
                    project_id=project_id,
                    file_path=file_path,
                    node_type=NodeType.FUNCTION.value,
                    name=func_name,
                    signature=f"function {func_name}()",
                    lineno=node.start_point[0] + 1
                ))

    return nodes


def _extract_ts_js_edges(
    tree: Tree,
    source_code: str,
    file_path: str,
    project_id: str,
    symbol_registry: Dict[str, str]
) -> List[CodeEdge]:
    """Extract TypeScript/JavaScript edges."""
    edges: List[CodeEdge] = []
    module_name = file_path.replace("/", ".").replace(".ts", "").replace(".js", "").lstrip(".")

    root = tree.root_node

    for node in _traverse(root):
        # Import declarations
        if node.type == "import_statement":
            source_node = _find_child_by_type(node, "string")
            if source_node:
                imported = _get_text(source_node, source_code).strip('"').strip("'")
                edges.append(CodeEdge(
                    source_id=module_name,
                    target_id=imported,
                    edge_type=EdgeType.IMPORTS.value,
                    lineno=node.start_point[0] + 1,
                    project_id=project_id
                ))

        # Class heritage (extends)
        elif node.type == "class_declaration":
            name_node = _find_child_by_field(node, "name")
            heritage_node = _find_child_by_type(node, "class_heritage")

            if name_node and heritage_node:
                class_name = _get_text(name_node, source_code)
                source_qual = f"{module_name}.{class_name}"

                # Find extends clause
                for child in heritage_node.children:
                    if child.type == "extends_clause":
                        type_node = _find_child_by_type(child, "identifier")
                        if type_node:
                            base_name = _get_text(type_node, source_code)
                            target_qual = symbol_registry.get(base_name, base_name)

                            edges.append(CodeEdge(
                                source_id=source_qual,
                                target_id=target_qual,
                                edge_type=EdgeType.INHERITS.value,
                                lineno=node.start_point[0] + 1,
                                project_id=project_id
                            ))

        # Function calls
        elif node.type == "call_expression":
            function_node = _find_child_by_field(node, "function")
            if function_node:
                enclosing = _find_enclosing_definition(node)
                if enclosing:
                    source_qual = _get_qualified_name(enclosing, source_code, module_name)
                else:
                    source_qual = module_name

                called_name = _get_text(function_node, source_code)
                target_qual = symbol_registry.get(called_name, called_name)

                edges.append(CodeEdge(
                    source_id=source_qual,
                    target_id=target_qual,
                    edge_type=EdgeType.CALLS.value,
                    lineno=node.start_point[0] + 1,
                    project_id=project_id
                ))

    return edges


# ============================================================================
# Helper Functions
# ============================================================================

def _traverse(node: "TSNode") -> List["TSNode"]:
    """Depth-first traversal of tree-sitter AST."""
    nodes = [node]
    for child in node.children:
        nodes.extend(_traverse(child))
    return nodes


def _get_text(node: "TSNode", source_code: str) -> str:
    """Extract text for a tree-sitter node."""
    return source_code[node.start_byte:node.end_byte]


def _find_child_by_field(node: "TSNode", field_name: str) -> Optional["TSNode"]:
    """Find child node by field name."""
    for child in node.children:
        if node.child_by_field_name(field_name) == child:
            return child
    return node.child_by_field_name(field_name)


def _find_child_by_type(node: "TSNode", node_type: str) -> Optional["TSNode"]:
    """Find first child node of given type."""
    for child in node.children:
        if child.type == node_type:
            return child
    return None


def _extract_docstring(node: "TSNode", source_code: str) -> Optional[str]:
    """Extract docstring from Python function/class."""
    for child in node.children:
        if child.type == "block":
            # First statement in block
            for stmt in child.children:
                if stmt.type == "expression_statement":
                    for expr in stmt.children:
                        if expr.type == "string":
                            return _get_text(expr, source_code).strip('"').strip("'")
    return None


def _extract_function_params(node: "TSNode", source_code: str) -> str:
    """Extract function parameters as string."""
    params_node = _find_child_by_field(node, "parameters")
    if params_node:
        return _get_text(params_node, source_code).strip("()").strip()
    return ""


def _find_enclosing_definition(node: "TSNode") -> Optional["TSNode"]:
    """Find enclosing function/class definition for a node."""
    current = node.parent
    while current:
        if current.type in ("function_definition", "class_definition",
                           "method_definition", "function_declaration"):
            return current
        current = current.parent
    return None


def _get_qualified_name(node: "TSNode", source_code: str, module_name: str) -> str:
    """Get qualified name for a definition node."""
    parts = [module_name]

    # Walk up to collect class/function names
    current = node
    while current and current.type != "module":
        if current.type in ("class_definition", "function_definition", "method_definition"):
            name_node = _find_child_by_field(current, "name")
            if name_node:
                parts.insert(1, _get_text(name_node, source_code))
        current = current.parent

    return ".".join(parts)
