#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ACSM/EPUB DRM Handler GUI
A PyQt-based GUI for managing Adobe DRM-protected ACSM and EPUB files.
"""

import sys
import os

if os.name == 'nt':
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = "windows"
else:
    os.environ['QT_QPA_PLATFORM'] = 'xcb'

from PyQt5.QtWidgets import QApplication

# Add calibre-plugin to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'calibre-plugin'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dedrm'))

from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
