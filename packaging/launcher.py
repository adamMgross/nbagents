import sys
from pathlib import Path

if Path(sys.argv[0]).name == "nba":
    from nbalake.explore.cli import main
else:
    from nbalake.cli import main

main()
