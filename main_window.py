#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main window for ACSM/EPUB DRM Handler GUI
"""

import os
import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QTextEdit, QFileDialog, QMessageBox, QPushButton, QDialog
)
from PyQt5.QtGui import QFont

# Add calibre-plugin to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'calibre-plugin'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dedrm'))

from worker import WorkerThread
from dialogs import LoginDialog


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ACSM/EPUB DRM Handler")
        self.setGeometry(100, 100, 800, 600)

        self.config_dir = Path.home() / '.deacsm'
        self.config_dir.mkdir(exist_ok=True)
        self.key_file = None

        self.init_ui()
        self.check_authorization()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()

        # Title
        title = QLabel("ACSM/EPUB DRM Handler")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Status
        layout.addWidget(QLabel("Status:"))
        self.status_label = QLabel("Idle")
        layout.addWidget(self.status_label)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Output log
        layout.addWidget(QLabel("Log:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(300)
        layout.addWidget(self.log_text)

        # Buttons
        button_layout = QHBoxLayout()

        self.process_btn = QPushButton("Process File (ACSM/EPUB)")
        self.process_btn.clicked.connect(self.process_file)
        button_layout.addWidget(self.process_btn)

        self.reauth_btn = QPushButton("Re-authorize Account")
        self.reauth_btn.clicked.connect(self.show_login_dialog)
        button_layout.addWidget(self.reauth_btn)

        layout.addLayout(button_layout)

        central_widget.setLayout(layout)

    def check_authorization(self):
        """Check if user is already authorized"""
        key_files = list(self.config_dir.glob("adobekey*.der"))
        if key_files:
            self.key_file = key_files[0]
            self.log(f"Found authorization: {self.key_file.name}")
            self.status_label.setText(f"Authorized: {self.key_file.name}")
            self.process_btn.setEnabled(True)
        else:
            self.log("No authorization found. Please authorize first.")
            self.status_label.setText("Not authorized")
            self.process_btn.setEnabled(False)
            self.show_login_dialog()

    def show_login_dialog(self):
        """Show login dialog"""
        dialog = LoginDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.result_data
            if data['type'] == 'adobe':
                self.authorize_adobe(data['email'], data['password'], data['version'])

    def authorize_adobe(self, email, password, version):
        """Authorize with Adobe account"""
        self.log("Starting authorization...")
        self.status_label.setText("Authorizing...")
        self.process_btn.setEnabled(False)

        worker = WorkerThread("login", email, password, version)
        worker.progress.connect(self.log)
        worker.finished.connect(self.on_authorization_complete)
        self.worker = worker
        worker.start()

    def on_authorization_complete(self, success, message):
        """Handle authorization completion"""
        if success:
            self.log(message)
            self.status_label.setText(message)
            self.check_authorization()
            QMessageBox.information(self, "Success", message)
        else:
            self.log(message)
            self.status_label.setText("Authorization failed")
            QMessageBox.critical(self, "Error", message)

    def on_process_complete(self, success, message):
        """Handle file processing completion"""
        self.progress_bar.setVisible(False)
        self.process_btn.setEnabled(True)

        if success:
            self.log(message)
            self.status_label.setText("Ready")
            QMessageBox.information(self, "Success", message)
        else:
            self.log(message)
            self.status_label.setText("Processing failed")
            QMessageBox.critical(self, "Error", message)

    def on_acsm_fulfilled(self, success, message):
        """Handle ACSM fulfillment completion - then ask where to save"""
        if not success:
            self.progress_bar.setVisible(False)
            self.process_btn.setEnabled(True)
            self.log(message)
            self.status_label.setText("Processing failed")
            QMessageBox.critical(self, "Error", message)
            return

        self.log(message)

        # Now ask where to save the fulfilled EPUB
        fulfilled_epub = None
        config_dir = Path.home() / '.deacsm'

        # Find the recently fulfilled EPUB in config directory
        epub_files = sorted(config_dir.glob("*.epub"), key=lambda x: x.stat().st_mtime, reverse=True)
        if epub_files:
            fulfilled_epub = epub_files[0]

        if not fulfilled_epub:
            self.progress_bar.setVisible(False)
            self.process_btn.setEnabled(True)
            self.log("Error: Could not find fulfilled EPUB file")
            self.status_label.setText("Processing failed")
            QMessageBox.critical(self, "Error", "Could not find fulfilled EPUB file")
            return

        # Ask user where to save
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save fulfilled EPUB as",
            str(fulfilled_epub),
            "EPUB Files (*.epub)"
        )

        if not output_path:
            self.progress_bar.setVisible(False)
            self.process_btn.setEnabled(True)
            self.status_label.setText("Ready")
            return

        # Now decrypt to the chosen location
        self.log(f"Decrypting to: {output_path}")
        self.status_label.setText("Decrypting EPUB...")

        worker = WorkerThread("decrypt", str(fulfilled_epub), str(self.key_file), str(output_path))
        worker.progress.connect(self.log)
        worker.finished.connect(self.on_process_complete)
        self.worker = worker
        worker.start()

    def process_file(self):
        """Process ACSM or EPUB file"""
        if not self.key_file:
            QMessageBox.warning(self, "Error", "No key file found. Please authorize first.")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ACSM or EPUB file",
            "",
            "ACSM/EPUB Files (*.acsm *.epub);;All Files (*)"
        )

        if not file_path:
            return

        file_path = Path(file_path)

        if file_path.suffix.lower() == '.acsm':
            self.process_acsm(file_path)
        elif file_path.suffix.lower() == '.epub':
            self.process_epub(file_path)
        else:
            QMessageBox.warning(self, "Error", "Unsupported file format")

    def process_acsm(self, acsm_path):
        """Process ACSM file"""
        self.log(f"Processing ACSM: {acsm_path.name}")
        self.status_label.setText("Processing ACSM...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)  # Indeterminate progress
        self.process_btn.setEnabled(False)

        # Store ACSM path for later use after fulfillment
        self.current_acsm_path = acsm_path

        worker = WorkerThread("fulfill", str(acsm_path), str(self.key_file))
        worker.progress.connect(self.log)
        worker.finished.connect(self.on_acsm_fulfilled)
        self.worker = worker
        worker.start()

    def process_epub(self, epub_path):
        """Process EPUB file"""
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save decrypted EPUB as",
            f"{epub_path.stem}_decrypted.epub",
            "EPUB Files (*.epub)"
        )

        if not output_path:
            return

        self.log(f"Processing EPUB: {epub_path.name}")
        self.status_label.setText("Decrypting EPUB...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)  # Indeterminate progress
        self.process_btn.setEnabled(False)

        worker = WorkerThread("decrypt", str(epub_path), str(self.key_file), str(output_path))
        worker.progress.connect(self.log)
        worker.finished.connect(self.on_process_complete)
        self.worker = worker
        worker.start()

    def log(self, message):
        """Add message to log"""
        self.log_text.append(message)
        # Auto-scroll to bottom
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )