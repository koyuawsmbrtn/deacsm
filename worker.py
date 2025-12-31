#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Worker thread for long-running operations in ACSM/EPUB DRM Handler
"""

import os
import sys
import zipfile as zf
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal
from lxml import etree

# Add calibre-plugin to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'calibre-plugin'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dedrm'))

# Import decryption libraries
try:
    from ineptepub import decryptBook
except ImportError:
    decryptBook = None

from libadobe import createDeviceKeyFile, update_account_path, VAR_VER_SUPP_CONFIG_NAMES
from libadobeAccount import createDeviceFile, createUser, signIn, exportAccountEncryptionKeyDER, getAccountUUID, activateDevice
from libadobeFulfill import buildRights, fulfill
from libpdf import patch_drm_into_pdf


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