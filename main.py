import sys

from worktrace.ui.cli import app, launch_desktop


if __name__ == "__main__":
    if len(sys.argv) == 1:
        launch_desktop()
    else:
        app()
