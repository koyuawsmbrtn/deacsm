#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ACSM/EPUB DRM Handler GUI
A PyQt-based GUI for managing Adobe DRM-protected ACSM and EPUB files.
"""

import sys
import os
import json
import zipfile
import tempfile
import getpass
from pathlib import Path

# Set the Qt platform to xcb
os.environ['QT_QPA_PLATFORM'] = 'xcb'

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QProgressBar,
    QTextEdit, QFileDialog, QMessageBox, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QFont

# Add calibre-plugin to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'calibre-plugin'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dedrm'))

from libadobe import createDeviceKeyFile, update_account_path, VAR_VER_SUPP_CONFIG_NAMES
from libadobeAccount import createDeviceFile, createUser, signIn, exportAccountEncryptionKeyDER, getAccountUUID
from libadobeFulfill import buildRights, fulfill
from libpdf import patch_drm_into_pdf
import zipfile as zf
from lxml import etree

# Import decryption libraries
try:
    from ineptepub import decryptBook
except ImportError:
    decryptBook = None


class WorkerThread(QThread):
    """Worker thread for long-running operations"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, task_type, *args):
        super().__init__()
        self.task_type = task_type
        self.args = args
        
    def run(self):
        try:
            if self.task_type == "login":
                self._login_adobe(*self.args)
            elif self.task_type == "fulfill":
                self._fulfill_acsm(*self.args)
            elif self.task_type == "decrypt":
                self._decrypt_epub(*self.args)
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")
    
    def _login_adobe(self, email, password, version):
        """Login to Adobe and export keys"""
        from libadobeAccount import activateDevice
        
        self.progress.emit("Creating device files...")
        config_dir = Path.home() / '.deacsm'
        config_dir.mkdir(exist_ok=True)
        
        # Work in config directory instead of temp directory
        old_cwd = os.getcwd()
        try:
            os.chdir(config_dir)
            update_account_path(str(config_dir))
            
            createDeviceKeyFile()
            success = createDeviceFile(True, version)
            if not success:
                self.finished.emit(False, "Failed to create device file")
                return
            
            self.progress.emit("Creating user account...")
            success, resp = createUser(version, None)
            if not success:
                self.finished.emit(False, f"Failed to create user: {resp}")
                return
            
            self.progress.emit("Signing in...")
            success, resp = signIn("AdobeID", email, password)
            if not success:
                self.finished.emit(False, f"Failed to sign in: {resp}")
                return
            
            self.progress.emit("Activating device...")
            success, resp = activateDevice(version)
            if not success:
                self.finished.emit(False, f"Failed to activate device: {resp}")
                return
            
            self.progress.emit("Exporting keys...")
            key_filename = "adobekey.der"
            export_path = exportAccountEncryptionKeyDER(key_filename)
            
            self.finished.emit(True, f"Successfully authorized as {email}")
        finally:
            os.chdir(old_cwd)
    
    def _fulfill_acsm(self, acsm_path, key_path):
        """Fulfill ACSM file"""
        from libadobe import sendHTTPRequest_DL2FILE
        import time
        import shutil
        
        self.progress.emit("Reading ACSM file...")
        acsm_path = Path(acsm_path)
        config_dir = Path.home() / '.deacsm'
        old_cwd = os.getcwd()
        
        try:
            os.chdir(config_dir)
            update_account_path(str(config_dir))
            
            self.progress.emit("Fulfilling book...")
            success, replyData = fulfill(str(acsm_path))
            
            if not success:
                self.finished.emit(False, f"Fulfillment failed: {replyData}")
                return
            
            # Parse the fulfillment response
            adobe_fulfill_response = etree.fromstring(replyData)
            NSMAP = {"adept": "http://ns.adobe.com/adept"}
            adNS = lambda tag: '{%s}%s' % ('http://ns.adobe.com/adept', tag)
            adDC = lambda tag: '{%s}%s' % ('http://purl.org/dc/elements/1.1/', tag)
            
            try:
                download_url = adobe_fulfill_response.find("./%s/%s/%s" % (adNS("fulfillmentResult"), adNS("resourceItemInfo"), adNS("src"))).text
                license_token_node = adobe_fulfill_response.find("./%s/%s/%s" % (adNS("fulfillmentResult"), adNS("resourceItemInfo"), adNS("licenseToken")))
            except:
                self.finished.emit(False, "Failed to parse fulfillment response")
                return
            
            rights_xml_str = buildRights(license_token_node)
            if rights_xml_str is None:
                self.finished.emit(False, "Failed to build rights.xml")
                return
            
            # Get book name
            try:
                metadata_node = adobe_fulfill_response.find("./%s/%s/%s" % (adNS("fulfillmentResult"), adNS("resourceItemInfo"), adNS("metadata")))
                book_name = metadata_node.find("./%s" % (adDC("title"))).text
            except:
                book_name = "Book"
            
            # Download the book
            self.progress.emit("Downloading book...")
            filename_tmp = book_name + ".tmp"
            
            ret = sendHTTPRequest_DL2FILE(download_url, filename_tmp)
            if ret != 200:
                self.finished.emit(False, f"Download failed with error {ret}")
                return
            
            # Check file type
            with open(filename_tmp, "rb") as f:
                book_content = f.read(10)
            
            if book_content.startswith(b"PK"):
                filetype = ".epub"
            elif book_content.startswith(b"%PDF"):
                filetype = ".pdf"
            else:
                filetype = ".bin"
            
            filename = book_name + filetype
            shutil.move(filename_tmp, filename)
            
            if filetype == ".epub":
                # Store EPUB rights/encryption
                with zf.ZipFile(filename, "a") as zpf:
                    zpf.writestr("META-INF/rights.xml", rights_xml_str)
                
                self.progress.emit(f"File fulfilled: {filename}")
                self.finished.emit(True, f"Successfully fulfilled: {filename}")
                return
            elif filetype == ".pdf":
                self.progress.emit("Patching PDF encryption...")
                adobe_fulfill_response = etree.fromstring(rights_xml_str)
                NSMAP = {"adept": "http://ns.adobe.com/adept"}
                adNS = lambda tag: '{%s}%s' % ('http://ns.adobe.com/adept', tag)
                resource = adobe_fulfill_response.find("./%s/%s" % (adNS("licenseToken"), adNS("resource"))).text
                
                os.rename(filename, "tmp_" + filename)
                ret = patch_drm_into_pdf("tmp_" + filename, rights_xml_str, filename, resource)
                os.remove("tmp_" + filename)
                
                if ret:
                    self.finished.emit(True, f"Successfully fulfilled: {filename}")
                else:
                    self.finished.emit(False, f"Failed to patch PDF: {filename}")
            else:
                self.finished.emit(False, "Unsupported file type")
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")
        finally:
            os.chdir(old_cwd)
    
    def _decrypt_epub(self, epub_path, key_path, output_path):
        """Decrypt EPUB file"""
        if decryptBook is None:
            self.finished.emit(False, "ineptepub module not available")
            return
        
        self.progress.emit("Reading key file...")
        try:
            with open(key_path, 'rb') as f:
                userkey = f.read()
        except Exception as e:
            self.finished.emit(False, f"Failed to read key file: {str(e)}")
            return
        
        self.progress.emit("Decrypting EPUB...")
        try:
            result = decryptBook(userkey, str(epub_path), str(output_path))
            if result == 0:
                self.finished.emit(True, f"Successfully decrypted to: {output_path}")
            elif result == 1:
                self.finished.emit(False, f"EPUB is DRM-free")
            elif result == 2:
                self.finished.emit(False, f"Failed to decrypt: wrong key")
            else:
                self.finished.emit(False, f"Decryption failed with error code {result}")
        except Exception as e:
            self.finished.emit(False, f"Decryption error: {str(e)}")


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
        
        # Auth type selection
        auth_group = QButtonGroup()
        self.radio_adobe = QRadioButton("Adobe Account")
        self.radio_anonymous = QRadioButton("Anonymous (No Account)")
        auth_group.addButton(self.radio_adobe)
        auth_group.addButton(self.radio_anonymous)
        self.radio_adobe.setChecked(True)
        
        layout.addWidget(QLabel("Authentication Method:"))
        layout.addWidget(self.radio_adobe)
        layout.addWidget(self.radio_anonymous)
        layout.addSpacing(10)
        
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
        self.radio_adobe.toggled.connect(self.on_auth_type_changed)
        self.on_auth_type_changed()
        
    def on_auth_type_changed(self):
        is_adobe = self.radio_adobe.isChecked()
        self.email_input.setEnabled(is_adobe)
        self.password_input.setEnabled(is_adobe)
        self.version_combo.setEnabled(is_adobe)
    
    def accept(self):
        if self.radio_adobe.isChecked():
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
        else:
            self.result_data = {'type': 'anonymous'}
        
        super().accept()


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
        
        from libadobeAccount import activateDevice
        
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
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save EPUB as",
            str(acsm_path.stem) + ".epub",
            "EPUB Files (*.epub)"
        )
        
        if not output_path:
            return
        
        self.log(f"Processing ACSM: {acsm_path.name}")
        self.status_label.setText("Processing ACSM...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)  # Indeterminate progress
        self.process_btn.setEnabled(False)
        
        worker = WorkerThread("fulfill", str(acsm_path), str(self.key_file))
        worker.progress.connect(self.log)
        worker.finished.connect(self.on_process_complete)
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


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
