# ACSM/EPUB DRM Handler GUI

A PyQt5-based graphical application for managing Adobe DRM-protected ACSM and EPUB files on Linux. This tool allows you to authorize your Adobe account, fulfill ACSM files to retrieve encrypted eBooks, and decrypt Adobe DRM-protected EPUB files.

## Features

- **Adobe Account Authorization**: Login with your Adobe ID to authorize your device
- **ACSM Fulfillment**: Download and process Adobe Content Server Message (ACSM) files
- **EPUB Decryption**: Decrypt Adobe DRM-protected EPUB files
- **Key Management**: Automatically saves authorization keys to `~/.deacsm/` for persistent access
- **User-Friendly GUI**: Simple PyQt5 interface with progress tracking and detailed logging
- **No Re-authentication Required**: Keys are saved locally, so you only need to authorize once

## Requirements

### System Requirements

- Linux (tested on recent distributions)
- Python 3.7 or higher
- OpenSSL with legacy provider support (see troubleshooting section)

### Python Dependencies

- PyQt5
- lxml
- PyCryptodome (or PyCrypto)
- requests

## Installation

### Step 1: Clone or Download the Repository

```bash
git clone <repository-url>
cd deacsm
```

### Step 2: Install Python Dependencies

Install the required Python packages:

```bash
pip3 install PyQt5 lxml pycryptodomex requests
```

Alternatively, if you prefer using your distribution's package manager:

#### Debian/Ubuntu:
```bash
sudo apt-get install python3-pyqt5 python3-lxml python3-crypto python3-requests
```

#### Fedora:
```bash
sudo dnf install python3-qt5 python3-lxml python3-pycryptodome python3-requests
```

#### Arch:
```bash
sudo pacman -S python-pyqt5 python-lxml python-pycryptodome python-requests
```

### Step 3: Ensure OpenSSL Legacy Provider is Enabled

If you're using OpenSSL 3.x, the legacy provider (which includes RC2 support needed for EPUB decryption) must be enabled. See the **Troubleshooting** section below for detailed instructions.

## Usage

### Running the Application

```bash
python3 gui.pyw
```

Or make it executable and run directly:

```bash
chmod +x gui.pyw
./gui.pyw
```

### First Time Setup (Authorization)

1. **Launch the application**: `python3 gui.pyw`
2. **Authorization dialog appears**: You'll be prompted to authorize
3. **Choose authentication method**:
   - Select "Adobe Account" to log in with your Adobe ID
   - Or select "Anonymous (No Account)" for basic device registration
4. **Enter your credentials**:
   - Adobe ID (email)
   - Password
   - ADE Version (ADE 3.0 is recommended and selected by default)
5. **Click "Authorize"**: The application will create device files and export your encryption key
6. **Success**: Your keys are saved to `~/.deacsm/` and you won't need to authorize again

### Processing ACSM Files

1. Click **"Process File (ACSM/EPUB)"**
2. Select your `.acsm` file
3. Choose where to save the fulfilled EPUB file
4. The application will:
   - Fulfill the ACSM file via Adobe servers
   - Download the encrypted EPUB
   - Add the necessary encryption metadata
   - Save the file to your chosen location

### Decrypting EPUB Files

1. Click **"Process File (ACSM/EPUB)"**
2. Select your encrypted `.epub` file
3. Choose where to save the decrypted EPUB
4. The application will:
   - Read your authorization key
   - Decrypt the EPUB file
   - Save the DRM-free version

### Re-authorizing (Switching Accounts)

To authorize a different Adobe account:

1. Click **"Re-authorize Account"**
2. Follow the authorization dialog steps
3. Your new credentials will replace the old ones

## File Locations

All authorization data is stored in your home directory:

```
~/.deacsm/
├── devicesalt          # Device key material
├── device.xml          # Device information
├── activation.xml      # Adobe activation data
└── adobekey.der        # Your exported encryption key
```

**Important**: Keep these files safe! They contain your unique device identification and encryption keys.

## Troubleshooting

### Error: "OpenSSL has been compiled without RC2 support"

#### The Cause

Adobe uses outdated algorithms such as RC2 for its activation protocols. Modern operating systems now compile OpenSSL by default without RC2 support (or disable it in the "Default-Provider" configuration) because RC2 is considered insecure. The Python library oscrypto, which the plugin uses, attempts to access this function and fails.

#### Solution: Enable OpenSSL Legacy Provider

##### Option 1: Using Environment Variable (Quick Fix)

```bash
export OPENSSL_CONF=/etc/ssl/openssl.cnf
python3 gui.pyw
```

##### Option 2: Modify OpenSSL Configuration (Permanent Fix - Recommended)

Edit your OpenSSL configuration file:

```bash
sudo nano /etc/ssl/openssl.cnf
```

Find the section that looks like this (usually near the beginning or end):

```ini
[provider_sect]
default = default_sect
legacy = legacy_sect

[default_sect]
activate = 1

[legacy_sect]
activate = 1
```

If this section doesn't exist, add it at the end of the file. If the legacy provider is commented out, uncomment it.

After editing, save the file (Ctrl+X, then Y, then Enter in nano).

Verify the fix works:

```bash
python3 gui.pyw
```

##### Option 3: Local OpenSSL Configuration

If you don't have sudo access or prefer a local configuration:

1. Copy the OpenSSL config to your home directory:

```bash
cp /etc/ssl/openssl.cnf ~/.openssl.cnf
```

2. Edit your copy:

```bash
nano ~/.openssl.cnf
```

3. Add the legacy provider section (see above)

4. Run the application with the custom config:

```bash
OPENSSL_CONF=~/.openssl.cnf python3 gui.pyw
```

### Error: "Qt platform plugin 'wayland' could not be found"

This occurs on Wayland-based desktop environments. The application is configured to use X11 automatically, but if you still encounter this:

```bash
QT_QPA_PLATFORM=xcb python3 gui.pyw
```

### Error: "Cannot import module 'ineptepub'"

Make sure the `dedrm` directory is in the same location as `gui.pyw`:

```bash
ls -la dedrm/ineptepub.py
```

If the file exists, check that the path is correct. Both `calibre-plugin/` and `dedrm/` directories should be in the same parent directory as `gui.pyw`.

### Error: "Failed to sign in: Invalid username or password"

- Double-check your Adobe ID and password
- Ensure you have an active Adobe ID account
- Try logging in to the official Adobe website first to confirm your credentials work
- Some regions may have authentication restrictions

### EPUB Decryption Returns "DRM-free" Status

The EPUB file you're trying to decrypt doesn't have Adobe DRM protection. It's already DRM-free and can be read directly without decryption.

### EPUB Decryption Returns "Wrong key" Error

The key file doesn't match the EPUB file:
- The EPUB was purchased with a different Adobe account
- The key file is corrupted
- Try re-authorizing with the correct Adobe account

## Architecture

The application consists of:

- **gui.pyw**: Main PyQt5 application with UI components
- **WorkerThread**: Background thread for long-running operations (login, fulfillment, decryption)
- **LoginDialog**: Authorization dialog
- **MainWindow**: Main application window with file processing controls

### External Modules Used

- **libadobe.py**: Adobe DRM device key and signature handling
- **libadobeAccount.py**: Adobe account authentication
- **libadobeFulfill.py**: ACSM fulfillment process
- **ineptepub.py**: EPUB decryption implementation
- **libpdf.py**: PDF DRM patching

## Security Notes

1. **Key Storage**: Your encryption keys are stored in `~/.deacsm/`. This directory should have restricted permissions (typically `700`).

2. **Password Handling**: Passwords are only used during initial authorization and are not stored by this application.

3. **Network Requests**: The ACSM fulfillment process communicates with Adobe servers. Your device information and authorization data are sent during this process.

4. **DRM Rights**: This tool respects Adobe's DRM implementation. It only decrypts files you have authorized access to through your Adobe account.

## Legal Notice

This tool is provided for personal use to decrypt content you have legally purchased. Ensure compliance with local copyright laws and Adobe's Terms of Service. The authors are not responsible for misuse of this software.

## License

Please refer to the LICENSE file included in this repository. Do note that this project includes code from other open-source projects, each with their own licenses.

## Contributing

If you encounter issues or have suggestions, please open an issue or submit a pull request.

## Credits

This application uses code and techniques from:
- Leseratte10's ACSM Calibre Plugin
- Apprentice Alf's DeDRM Tools
- Various open-source DRM analysis projects

## Special Thanks

Special thanks to **Leseratte10** for the ACSM Calibre Plugin and **noDRM and apprenticeharper** for the DeDRM tools, which made this project possible.

## Support

For issues specific to this GUI:
- Check the troubleshooting section above
- Review the log output in the application for detailed error messages
- Ensure all dependencies are correctly installed

For issues with the underlying DRM libraries:
- Refer to the original project repositories
- Check for updates to these libraries
