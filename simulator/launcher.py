"""PyInstaller entry point (absolute import so the frozen exe resolves the package)."""

import sys

from campus_sec_sim.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
