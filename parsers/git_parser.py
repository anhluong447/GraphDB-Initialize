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
            "hash": commit.hexsha[:8],
            "author": commit.author.name,
            "author_email": commit.author.email,
            "date": commit.committed_datetime.isoformat(),
            "message": commit.message.strip(),
            "files_changed": files_changed,
        })

    print(f"[GitParser] Parsed {len(commits)} commits.")
    return commits


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
