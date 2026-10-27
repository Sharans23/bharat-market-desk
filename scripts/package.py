"""Build a clean distributable without accounts, caches or development dependencies."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

def release_files(root):
    root = Path(root)
    root_names = {"README.md", "LICENSE", ".gitignore", "connect-kite.cmd", "launch-app.vbs", "launch-app.cmd", "requirements.txt", "Dockerfile", "render.yaml", ".dockerignore"}
    code_roots = {"india_trader", "scripts", "tests"}
    docs_names = {"sources.md", "operations.md", "tax.md", "schemas.md", "upstream-comparison.md", "verification.md", "brokers.md", "live-probe.json", "ui.md", "hosting.md"}
    data_names = {"calendar-2026.json", "charges.json", "default-config.json"}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(p.startswith(".env") or p in {"__pycache__", "credentials", "snapshots", "node_modules", "test-results", "playwright-report", ".ui-test-data"} for p in rel.parts) or path.suffix in {".dpapi", ".fernet", ".pyc", ".lock"}:
            continue
        allowed = len(rel.parts) == 1 and path.name in root_names
        allowed |= rel.parts[0] in code_roots and path.suffix == ".py"
        allowed |= rel.parts[0] == "skills" and (path.name == "SKILL.md" or path.name == "run.py")
        allowed |= rel.parts[0] == ".claude-plugin" and path.name in {"plugin.json", "marketplace.json"}
        allowed |= rel.parts[0] == "docs" and path.name in docs_names
        allowed |= rel.parts[0] == "data" and path.name in data_names
        allowed |= rel.parts[0] == "examples" and path.suffix == ".json"
        if rel.parts[0] == "ui":
            allowed |= len(rel.parts) == 2 and path.name in {"package.json", "package-lock.json", "index.html", "vite.config.js", "playwright.config.js", "THIRD-PARTY-NOTICES.txt"}
            allowed |= len(rel.parts) >= 3 and rel.parts[1] in {"src", "dist", "e2e"} and path.suffix in {".js", ".jsx", ".css", ".html", ".svg"}
        if allowed:
            yield path


def main():
    root = Path(__file__).resolve().parents[1]
    target = root.parent / "india-trader.zip"
    files = list(release_files(root))
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, Path("india-trader") / path.relative_to(root))
    with ZipFile(target) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Archive integrity failure: {bad}")
    checksum = sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(checksum + "  " + target.name + "\n", encoding="ascii")
    print(f"Packaged {len(files)} files: {target}")
    print(f"SHA256: {checksum}")


if __name__ == "__main__":
    main()
