"""
Behavioral denylist: static scans with no model call.

- test scripts: flag network/proc/exec imports and calls
- patches: flag bare except:pass, swallowed exceptions
- untrusted-only spans: flag URLs and shell strings
"""

import ast
import re
from typing import Sequence

NETWORK_IMPORTS = {"socket", "requests", "urllib", "httplib", "ftplib", "smtplib"}
PROC_IMPORTS = {"subprocess", "os", "shutil", "signal"}
EXEC_IMPORTS = {"eval", "exec", "compile", "__import__", "marshal", "pickle", "shelve"}
DANGEROUS_IMPORTS = NETWORK_IMPORTS | PROC_IMPORTS | EXEC_IMPORTS

DANGEROUS_CALLS = {
    "socket", "socket.socket", "socket.create_connection",
    "subprocess.Popen", "subprocess.call", "subprocess.run", "subprocess.check_output",
    "os.system", "os.popen", "os.execl", "os.execle", "os.execlp", "os.execv",
    "eval", "exec", "compile",
}

EMPTY_OR_COMMENT = re.compile(r"^\s*(?:#.*)?$")
URL_RE = re.compile(r"https?://[^\s\"')]+")
SHELL_STRING_RE = re.compile(r"[`$][({][^}]+[})]")


def has_swallowed_exception(code: str) -> list[str]:
    flags = []
    lines = code.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"except\s*:", stripped):
            flags.append("bare-except")
        elif re.match(r"except\s+.*:", stripped):
            if i + 1 < len(lines) and EMPTY_OR_COMMENT.match(lines[i + 1]):
                flags.append("swallowed-exception")
    return flags


def has_dangerous_imports(code: str) -> list[str]:
    flags = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in NETWORK_IMPORTS:
                        flags.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module in DANGEROUS_IMPORTS:
                    for alias in node.names:
                        if alias.name != "":
                            flags.append(f"from {node.module} import {alias.name}")
    except SyntaxError:
        for name in DANGEROUS_IMPORTS:
            if name in code:
                flags.append(f"raw-import: {name}")
    return flags


def has_dangerous_calls(code: str) -> list[str]:
    flags = []
    for call in DANGEROUS_CALLS:
        pattern = re.compile(rf"\b{re.escape(call)}\s*\(")
        if pattern.search(code):
            flags.append(f"call: {call}")
    return flags


def has_urls(code: str) -> list[str]:
    return [f"url: {m}" for m in URL_RE.findall(code)]


def has_shell_strings(code: str) -> list[str]:
    return [f"shell-string: {m}" for m in SHELL_STRING_RE.findall(code)]


def scan_test(code: str) -> list[str]:
    flags = []
    flags.extend(has_dangerous_imports(code))
    flags.extend(has_dangerous_calls(code))
    flags.extend(has_urls(code))
    flags.extend(has_shell_strings(code))
    return flags


def scan_patch(diff: str) -> list[str]:
    flags = []
    added = "\n".join(
        line[1:] for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    flags.extend(has_swallowed_exception(added))
    flags.extend(has_urls(added))
    flags.extend(has_shell_strings(added))
    return flags