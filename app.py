import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.protection import init_protection
from gui.main_window import MainWindow


def main():
    if sys.platform == "win32":
        init_protection()

    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()
