"""
signer.py

Functions to be used during `sign` (sign function)
and `verify` (on_verify) operations.
"""
####################
# Standard libraries
####################
import hashlib
import base64

#################
# Local libraries
#################
from utils.constants import (
    KSIGNER_COMPRESSED_PUBKEY_PREPEND,
    KSIGNER_UNCOMPRESSED_PUBKEY_PREPEND,
)
from utils.log import build_logger
from utils.qr import make_qr_code
from cli.scanner import Scanner


class Signer:
    """
    Signer is the class
    that manages the `sign` command
    """

    def __init__(self, **kwargs):
        self.file = kwargs.get("file")
        self.owner = kwargs.get("owner")
        self.uncompressed = kwargs.get("uncompressed")

        self.loglevel = kwargs.get("loglevel")
        self.log = build_logger(__name__, self.loglevel)
        self.scanner = Scanner(loglevel=self.loglevel)

    def sign(self):
        """
        (1) Read a file;
        (2) Save in a .sha256.txt file;
        (3) Requires the user loads a xpriv key on his/her device:
            (a) load a 12/24 words key;
            (b) with or without BIP39 password;
        (4) sign a message:
            (a) once loaded the xpriv key, user goes
            to Sign > Message feature on his/her device
            (b) show a qrcode on device;
            (c) this function will generate a qrcode on computer;
            (d) once shown, the user will be prompted to scan it with device;
            (e) once scanned, the device will show some qrcodes:
                (i) the signature as a qrcode;
                (ii) the public key;
            (f) once above qrcodes are scanned, the computer
                will generate a publickey certificate, in a compressed
                or uncompressed format, in name of an owner.
        """
        self._show_warning_messages()
        data = self.hash_file()
        self.save_hash_file(data)
        self._print_qrcode(data)
        sig = self.scan_sig()
        self.save_signature(sig)

    def _show_warning_messages(self):
        """
        Shows warning messages before hash
        """
        self.log.debug("Showing warning messages to sign")

        # Shows some message
        print("")
        print("To sign this file with Krux: ")
        print(" (a) load a 12/24 words key with or without password;")
        print(" (b) use the Sign->Message feature;")
        print(" (c) and scan this QR code below.")
        print("")

    def hash_file(self) -> str:
        """
        Creates a hash file before sign
        """
        self.log.debug("Opening %s", self.file)

        with open(self.file, "rb") as f_sig:
            self.log.debug("Reading bytes...")
            _bytes = f_sig.read()
            self.log.debug("Hashing...")
            data = hashlib.sha256(_bytes).hexdigest()
            self.log.debug("Hash (data=%s)", data)
            return data

    def save_hash_file(self, data):
        """
        Save the hash file in sha256sum format
        """
        # Saves a hash file
        __hash_file__ = f"{self.file}.sha256sum.txt"
        self.log.debug("Saving %s", __hash_file__)

        with open(__hash_file__, mode="w", encoding="utf-8") as hash_file:
            content = f"{data} {self.file}"
            self.log.debug("%s content (data=%s)", __hash_file__, content)
            hash_file.write(content)
            self.log.debug("%s saved", __hash_file__)

    def _print_qrcode(self, data):
        """
        Print QRCode to console
        """
        # Prints the QR code
        self.log.debug("Creating QRCode (data=%s)", data)
        __qrcode__ = make_qr_code(data=data)
        print(f"{__qrcode__}")

    def scan_sig(self):
        """
        Make signature file from scanning qrcode
        """
        # Scans the signature QR code
        self.log.debug("Creating signature")
        return self.scanner.scan_signature()

    def save_signature(self, signature):
        """
        Save the signature data into file
        """
        # Saves a signature
        signature_file = f"{self.file}.sig"
        self.log.debug("Saving %s", signature_file)

        with open(signature_file, "wb") as sig_file:
            sig_file.write(signature)
            self.log.debug("Signature saved on %s", signature_file)

    def make_pubkey_certificate(self):
        """
        Make public key file from scanning qrcode
        """
        # Scans the public KeyboardInterruptardInterrupt
        self.log.debug("Creating public key certificate")
        pubkey = self.scanner.scan_public_key()

        # Create PEM data
        # Save PEM data to a file
        # with filename as owner's name
        # Choose if will be compressed or uncompressed
        if self.uncompressed:
            self.log.debug("Make it uncompressed key")
            __public_key_data__ = "".join(
                [KSIGNER_UNCOMPRESSED_PUBKEY_PREPEND, pubkey.upper()]
            )
        else:
            self.log.debug("Make it compressed key")
            __public_key_data__ = "".join(
                [KSIGNER_COMPRESSED_PUBKEY_PREPEND, pubkey.upper()]
            )

        # Convert pubkey data to bytes
        self.log.debug("Converting public key to bytes")
        __public_key_data_bytes__ = bytes.fromhex(__public_key_data__)
        self.log.debug("pubkey data bytes: %s", __public_key_data_bytes__)
        
        self.log.debug("Encoding bytes to base64 format")
        __public_key_data_b64__ = base64.b64encode(__public_key_data_bytes__)
        self.log.debug("encoded base64 pubkey: %s", __public_key_data_b64__)
        
        self.log.debug("Decoding bas64 to utf8")
        __public_key_data_b64_utf8__ = __public_key_data_b64__.decode("utf8")
        self.log.debug("decoded base64 utf8: %s", __public_key_data_b64_utf8__)

        __public_key_name__ = f"{self.owner}.pem"

        with open(__public_key_name__, mode="w", encoding="utf-8") as pb_file:
            self.log.debug("Saving %s", __public_key_name__)
            pb_file.write(str(__public_key_data_b64_utf8__))
            self.log.debug("%s saved", __public_key_name__)
