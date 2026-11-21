import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from volora_misure import gui  # noqa: E402

ap = argparse.ArgumentParser(description="Applicazione di prova per le misure VoLoRa V3")
ap.add_argument("--simulate", action="store_true", help="usa due schede finte (senza hardware)")
gui.main(ap.parse_args().simulate)
