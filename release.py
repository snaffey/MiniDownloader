"""
CLI helper script to trigger a release for MiniDownloader.

Usage:
    python release.py 1.1.0
    python release.py 1.1.0 --push
    python release.py 1.1.0 --dry-run
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).parent / "src" / "version.py"


def run_cmd(cmd: list[str], dry_run: bool = False) -> None:
    print(f"[{'DRY-RUN' if dry_run else 'EXEC'}] {' '.join(cmd)}")
    if not dry_run:
        subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description="Automated Release Trigger for MiniDownloader")
    parser.add_argument("version", help="New version string (e.g., 1.1.0 or v1.1.0)")
    parser.add_argument("--push", action="store_true", help="Push commit and tag to origin automatically")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")

    args = parser.parse_args()
    version = args.version.lstrip("v")

    if not re.match(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9]+)?$", version):
        print(f"Error: Invalid semantic version format '{version}'. Expected format X.Y.Z (e.g., 1.1.0)")
        sys.exit(1)

    print(f"Preparing release v{version}...")

    # 1. Update src/version.py
    if not VERSION_FILE.exists():
        print(f"Error: {VERSION_FILE} not found!")
        sys.exit(1)

    content = VERSION_FILE.read_text(encoding="utf-8")
    new_content = re.sub(
        r'__version__\s*=\s*["\'].*["\']',
        f'__version__ = "{version}"',
        content,
    )

    if content == new_content and not args.dry_run:
        print(f"Notice: src/version.py already set to {version}")
    else:
        print(f"Updating {VERSION_FILE} to version {version}...")
        if not args.dry_run:
            VERSION_FILE.write_text(new_content, encoding="utf-8")

    # 2. Git status check & commit
    run_cmd(["git", "add", "src/version.py"], dry_run=args.dry_run)
    
    commit_msg = f"chore(release): bump version to v{version}"
    try:
        run_cmd(["git", "commit", "-m", commit_msg], dry_run=args.dry_run)
    except subprocess.CalledProcessError:
        print("Nothing to commit (or commit failed). Proceeding to tag...")

    # 3. Create annotated tag
    tag_name = f"v{version}"
    run_cmd(["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"], dry_run=args.dry_run)

    print(f"\n[OK] Release tag {tag_name} created successfully!")

    if args.push:
        print("\nPushing changes and tag to remote origin...")
        run_cmd(["git", "push", "origin", "main"], dry_run=args.dry_run)
        run_cmd(["git", "push", "origin", tag_name], dry_run=args.dry_run)
        print(f"\n[PUSHED] Release {tag_name} pushed! GitHub Actions will now build and publish the release.")
    else:
        print(f"\nTo trigger the automated GitHub Actions CI/CD release build, run:")
        print(f"  git push origin main")
        print(f"  git push origin {tag_name}")
        print(f"Or re-run this script with --push")


if __name__ == "__main__":
    main()
