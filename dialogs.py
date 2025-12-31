#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dialog classes for ACSM/EPUB DRM Handler GUI
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox
)


class LoginDialog(QDialog):
    """Dialog for initial Adobe account login"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Authorize Adobe Account")
        self.setModal(True)
        self.init_ui()
        self.result_data = None

    def init_ui(self):
        layout = QVBoxLayout()

        # Email field
        layout.addWidget(QLabel("Adobe ID:"))
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("your.email@example.com")
        layout.addWidget(self.email_input)

        # Password field
        layout.addWidget(QLabel("Password:"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)

        # Version selection
        layout.addWidget(QLabel("ADE Version:"))
        self.version_combo = QComboBox()
        self.version_combo.addItem("ADE 2.0", 1)
        self.version_combo.addItem("ADE 3.0", 2)
        self.version_combo.setCurrentIndex(1)  # Set ADE 3.0 as default
        layout.addWidget(self.version_combo)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("Authorize")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def accept(self):
        email = self.email_input.text().strip()
        password = self.password_input.text()

        if not email or not password:
            QMessageBox.warning(self, "Error", "Please enter email and password")
            return

        self.result_data = {
            'type': 'adobe',
            'email': email,
            'password': password,
            'version': self.version_combo.currentData()
        }

        super().accept()