import click
from rich.console import Console
import os
import sys
import requests
import nelgraph

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()

def _check_for_updates():
    try:
        # Check PyPI version dynamically (timeout after 2s to prevent CLI blocking)
        res = requests.get("https://pypi.org/pypi/nelgraph/json", timeout=2)
        latest = res.json()["info"]["version"]
        from nelgraph import __version__
        if latest != __version__:
            console.print(
                f"[yellow]Update available: {__version__} → {latest}[/yellow]\n"
                f"Run: [bold]pip install --upgrade nelgraph[/bold]"
            )
    except Exception:
        pass

@click.group()
def main():
    """nelgraph — Codebase Knowledge Graph & Semantic Search CLI"""
    _check_for_updates()



@main.command()
@click.option("--key", help="OpenRouter API key")
@click.option("--path", default=".", help="Path to codebase (default: current dir)")
def init(key, path):
    """
    Khởi tạo GraphRAG cho project hiện tại.
    Tạo .env, start Neo4j Docker, parse + enrich toàn bộ codebase.
    """
    abs_path = os.path.abspath(path).replace("\\", "/")
    
    # Confirm if docker is running
    if not os.environ.get("NELGRAPH_NO_PROMPT"):
        if not click.confirm("Bạn đã bật Docker chưa?", default=True):
            console.print("[red]Vui lòng bật Docker trước khi khởi tạo.[/red]")
            sys.exit(1)
    
    # Load env from target path if exists
    from dotenv import load_dotenv
    env_path = os.path.join(abs_path, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
        
    api_key = key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        api_key = click.prompt("OpenRouter API key", hide_input=True)
        
    # Write or update .env in target directory
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    has_key = False
    has_path = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("OPENROUTER_API_KEY="):
            new_lines.append(f"OPENROUTER_API_KEY={api_key}\n")
            has_key = True
        elif line.strip().startswith("CODEBASE_PATH="):
            new_lines.append(f"CODEBASE_PATH={abs_path}\n")
            has_path = True
        else:
            new_lines.append(line)
            
    if not has_key:
        new_lines.append(f"OPENROUTER_API_KEY={api_key}\n")
    if not has_path:
        new_lines.append(f"CODEBASE_PATH={abs_path}\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        
    console.print(f"[green]✓ Configured {env_path}[/green]")
    
    # Programmatically configure nelgraph
    nelgraph.configure(codebase_path=abs_path, openrouter_api_key=api_key)
    
    # Run full initialization pipeline
    nelgraph.run_init()

@main.command()
@click.option("--silent", is_flag=True, help="Run silently without printing to stdout")
def sync(silent):
    """Sync thủ công — parse files đã thay đổi kể từ lần sync cuối."""
    if silent:
        # Redirect stdout/stderr to devnull
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')
        
    # Run sync pipeline
    nelgraph.run_sync()

@main.command()
def status():
    """Xem trạng thái graph hiện tại."""
    # Run status helper
    from nelgraph.initialize_graph import run_status
    run_status()

@main.command("install-hook")
def install_hook_cmd():
    """Cài đặt Git post-commit hook thủ công."""
    from nelgraph.updater.git_hook import install_hook
    installed = install_hook()
    if installed:
        console.print("[green]✓ Git post-commit hook installed successfully.[/green]")
    else:
        console.print("[red]✗ Failed to install Git post-commit hook. Make sure the target directory is a Git repository.[/red]")


@main.command()
def viz():
    """Khởi chạy dashboard NelGraph trực quan (Web UI)."""
    from nelgraph.initialize_graph import run_viz
    run_viz()


@main.command()
@click.pass_context
def help(ctx):
    """Hiển thị hướng dẫn sử dụng chi tiết."""
    click.echo(ctx.parent.get_help())

if __name__ == "__main__":
    main()
