"""红线机械检查 —— CHARTER 不靠自觉。

  python tools/lint_redlines.py

检查(违反即退出码 1):
  1. 场景/标本/工具代码不得 import 网络模块 —— 本仓库的一切都只在本机
     进程内对 Challenge/Submission 运作,不产生对外请求;
  2. specimens/ 下的黑盒标本不得 import scenarios.*(防线与场景内部);
  3. data/corpus/converted.jsonl 每行必须带 license 与 source 字段。
"""
import ast
import glob
import json
import os
import sys

NET_MODULES = {"socket", "ssl", "urllib", "urllib.request", "urllib.parse",
               "http", "http.client", "requests", "httpx", "aiohttp", "ftplib",
               "smtplib", "telnetlib", "xmlrpc", "asyncio"}
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_DIRS = ["scenarios", "specimens", "tools"]


def _imports_of(path):
    try:
        tree = ast.parse(open(path, "r", encoding="utf-8").read())
    except SyntaxError as e:
        return [], f"syntax-error: {e}"
    roots = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.append(node.module)
    return roots, None


def _first_root(name):
    return name.split(".")[0]


def main():
    violations = []

    for d in SCAN_DIRS:
        for path in glob.glob(os.path.join(REPO_ROOT, d, "**", "*.py"), recursive=True):
            roots, err = _imports_of(path)
            if err:
                violations.append(f"{path}: {err}")
                continue
            rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
            for r in roots:
                if r in NET_MODULES or r in {"socket", "ssl"}:
                    violations.append(f"{rel}: import {r} —— 红线1:禁止网络模块")
                if d == "specimens" and _first_root(r) == "scenarios":
                    violations.append(f"{rel}: import {r} —— 红线2:黑盒标本不得 import 场景/防线模块")

    corpus = os.path.join(REPO_ROOT, "data", "corpus", "converted.jsonl")
    if os.path.exists(corpus):
        with open(corpus, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    if not rec.get("license") or not rec.get("source"):
                        violations.append(f"data/corpus/converted.jsonl:{i} "
                                          f"缺 license/source 字段(红线3)")
                except Exception as e:
                    violations.append(f"data/corpus/converted.jsonl:{i}: {e}")

    if violations:
        print("红线检查不通过:")
        for v in violations:
            print(f"  ✗ {v}")
        return 1
    print("红线检查通过(网络模块 / 黑盒导入 / 语料字段)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
