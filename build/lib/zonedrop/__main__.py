"""Allow running as python3 -m zonedrop."""
import sys
from zonedrop.cli import main
sys.exit(main(sys.argv[1:]))
