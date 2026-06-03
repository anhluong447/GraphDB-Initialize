import re
import git
from config import CODEBASE_PATH


def parse_git_history(path: str = CODEBASE_PATH, max_commits: int = 500) -> list[dict]:
    """
    Parse git history, returns list of commits with:
    - hash, author, author_email, date, message, files_changed
    """
    try:
        repo = git.Repo(path)
    except git.InvalidGitRepositoryError:
        print("[GitParser] No git repo found.")
        return []

    commits = []
    for commit in list(repo.iter_commits())[:max_commits]:
        try:
            files_changed = list(commit.stats.files.keys())
        except Exception:
            files_changed = []

        commits.append({
            "hash": commit.hexsha[:12],
            "full_hash": commit.hexsha,
            "author": commit.author.name,
            "author_email": commit.author.email,
            "date": commit.committed_datetime.isoformat(),
            "message": commit.message.strip(),
            "files_changed": files_changed,
        })

    print(f"[GitParser] Parsed {len(commits)} commits.")
    return commits


def parse_commit_diff(repo_path: str, commit_hash: str) -> dict:
    """
    Parse the unified diff of a specific commit to extract changed line ranges per file.
    Returns dict: {"changed_ranges": {"file_path": [(start, end), ...], ...}}
    """
    try:
        repo = git.Repo(repo_path)
        commit = repo.commit(commit_hash)
    except Exception:
        return {"changed_ranges": {}}

    changed_ranges = {}

    try:
        if commit.parents:
            diffs = commit.diff(commit.parents[0], create_patch=True)
        else:
            # Initial commit: treat all files as fully changed
            diffs = commit.diff(git.NULL_TREE, create_patch=True)

        for diff_item in diffs:
            file_path = diff_item.b_path or diff_item.a_path
            if not file_path:
                continue

            # Parse unified diff hunk headers: @@ -x,y +a,b @@
            patch_text = ""
            try:
                patch_text = diff_item.diff.decode("utf-8", errors="ignore") if diff_item.diff else ""
            except Exception:
                continue

            ranges = []
            for match in re.finditer(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", patch_text):
                start_line = int(match.group(1))
                line_count = int(match.group(2)) if match.group(2) else 1
                end_line = start_line + max(line_count - 1, 0)
                ranges.append((start_line, end_line))

            if ranges:
                changed_ranges[file_path] = ranges

    except Exception as e:
        print(f"[GitParser] Warning: Could not parse diff for {commit_hash[:12]}: {e}")

    return {"changed_ranges": changed_ranges}


def parse_git_blame(file_path: str, repo_path: str = CODEBASE_PATH) -> dict:
    """Returns a map from line number -> author for a file."""
    try:
        repo = git.Repo(repo_path)
        blame = repo.blame("HEAD", file_path)
        blame_map = {}
        line_num = 1
        for commit, lines in blame:
            for _ in lines:
                blame_map[line_num] = commit.author.name
                line_num += 1
        return blame_map
    except Exception:
        return {}
