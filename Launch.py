import webbrowser
from pathlib import Path
import subprocess

BASE_DIR = Path(r"D:\downloby")
BACKEND_DIR = BASE_DIR / "v2"
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
HTML_PATH = BASE_DIR / "frontend" / "spool.html"


def launch_server():
    command = (
        f'"{VENV_PYTHON}" -m uvicorn app:app '
        '--reload --host 0.0.0.0 --port 8000'
    )

    print("Starting server:")
    print(command)

    subprocess.Popen(
        ["cmd.exe", "/k", command],
        cwd=str(BACKEND_DIR)
    )


def open_html():
    webbrowser.open(HTML_PATH.resolve().as_uri())


if __name__ == "__main__":
    launch_server()
    open_html()