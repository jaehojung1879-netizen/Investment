"""Small shared pin helper for the correction packet and unapproved recorder v2."""
from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime
from importlib.util import resolve_name
from pathlib import Path
from urllib.request import Request, urlopen


def repository_imports(root, entries):
    """Static local import closure, including relative and function-local imports."""
    root, seen, todo = Path(root), set(), list(entries)
    while todo:
        relative = todo.pop()
        path = root / relative
        if relative in seen or not path.is_file():
            continue
        seen.add(relative)
        parts = Path(relative).with_suffix('').parts
        package = '.'.join(parts[:-1])
        modules = []
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                modules.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                name = '.' * node.level + (node.module or '')
                base = resolve_name(name, package) if node.level else name
                modules.append(base)
                modules.extend(base + '.' + a.name for a in node.names if a.name != '*')
        for module in modules:
            bits = module.split('.')
            if bits[0] not in ('pipeline', 'research'):
                continue
            for i in range(1, len(bits) + 1):
                todo.append('/'.join(bits[:i]) + '/__init__.py')
            todo.append('/'.join(bits) + '.py')
    return sorted(seen)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_hashes(root, entries):
    return {p: file_hash(Path(root) / p) for p in repository_imports(root, entries)}


def check_owner_comment(auth, phrase, comment):
    """Verify GitHub account provenance, not a claim about the human at a keyboard."""
    owner = 'jaehojung1879-netizen'
    body = comment.get('body', '')
    ident = auth.get('approvalCommentId')
    if (type(ident) is not int or ident != comment.get('id')
            or comment.get('user', {}).get('login') != owner
            or comment.get('user', {}).get('id') != 238918679
            or not comment.get('issue_url', '').startswith(f'https://api.github.com/repos/{owner}/Investment/issues/')
            or phrase not in [line.strip() for line in body.splitlines()]
            or hashlib.sha256(body.encode()).hexdigest() != auth.get('approvalCommentSha256')):
        raise ValueError('OWNER_COMMENT_SCOPE_OR_PROVENANCE_INVALID')
    def utc(value):
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('OWNER_APPROVAL_TIME_REQUIRES_TIMEZONE')
        return stamp
    if utc(auth.get('authorizedAtUtc')) != utc(comment.get('created_at')):
        raise ValueError('OWNER_APPROVAL_TIME_MUST_MATCH_PUBLIC_COMMENT')


def verify_public_owner_approval(auth, phrase):
    ident = auth.get('approvalCommentId')
    if type(ident) is not int or ident <= 0:
        raise ValueError('EXACT_HASH_PUBLIC_OWNER_APPROVAL_REQUIRED')
    url = f'https://api.github.com/repos/jaehojung1879-netizen/Investment/issues/comments/{ident}'
    request = Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Investment-approval-verifier'})
    with urlopen(request, timeout=20) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError('OWNER_APPROVAL_COMMENT_TOO_LARGE')
    check_owner_comment(auth, phrase, json.loads(raw))
