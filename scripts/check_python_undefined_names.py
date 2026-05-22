from __future__ import annotations

import argparse
import builtins
import pathlib
import symtable


BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__package__"}
IGNORED_NAMES = {"annotations", "__conditional_annotations__"}


def _module_definitions(table: symtable.SymbolTable) -> set[str]:
    definitions: set[str] = set()
    for name in table.get_identifiers():
        symbol = table.lookup(name)
        if symbol.is_imported() or symbol.is_assigned() or symbol.is_namespace() or symbol.is_parameter():
            definitions.add(name)
    return definitions


def _walk_tables(table: symtable.SymbolTable):
    yield table
    for child in table.get_children():
        yield from _walk_tables(child)


def _find_unresolved_names(path: pathlib.Path) -> list[tuple[int, str, str]]:
    text = path.read_text(encoding="utf-8")
    table = symtable.symtable(text, str(path), "exec")
    module_definitions = _module_definitions(table)
    findings: list[tuple[int, str, str]] = []

    for scope in _walk_tables(table):
        for name in scope.get_identifiers():
            if name in BUILTINS or name in IGNORED_NAMES:
                continue
            symbol = scope.lookup(name)
            if not symbol.is_referenced():
                continue
            if scope is table:
                if not (
                    symbol.is_imported()
                    or symbol.is_assigned()
                    or symbol.is_namespace()
                    or symbol.is_parameter()
                ):
                    findings.append((0, name, "module-level reference is not defined/imported"))
            elif symbol.is_global() and name not in module_definitions:
                findings.append((scope.get_lineno(), name, f"unresolved global in {scope.get_name()}"))

    return sorted(set(findings))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Python files for unresolved global names.")
    parser.add_argument("paths", nargs="*", default=["services/api/src"], help="Files or directories to scan.")
    args = parser.parse_args()

    files: list[pathlib.Path] = []
    for raw_path in args.paths:
        path = pathlib.Path(raw_path)
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(item for item in path.rglob("*.py") if "__pycache__" not in item.parts)

    total = 0
    for path in sorted(files):
        try:
            findings = _find_unresolved_names(path)
        except SyntaxError as exc:
            findings = [(exc.lineno or 0, "<syntax>", str(exc))]
        for line, name, message in findings:
            print(f"{path}:{line}: {name}: {message}")
            total += 1

    if total:
        print(f"Found {total} unresolved Python name(s).")
        return 1
    print(f"No unresolved Python names found in {len(files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
