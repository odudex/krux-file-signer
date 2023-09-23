# The MIT License (MIT)

# Copyright (c) 2021-2023 Krux contributors

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
This python script is a tool to create air-gapped signatures of files using Krux.
The script can also converts hex publics exported from Krux to PEM public keys so
signatures can be verified using openssl.

Requirements:
    - opencv, qrcode
    pip install opencv-python qrcode

    - This script also calls a openssl bash command, 
    so it is required to have verification functionality
 """

####################
# Standart libraries
####################
import argparse
import hashlib
import subprocess
import base64
import time
from io import StringIO

#######################
# Thrid party libraries
#######################
import cv2
from qrcode import QRCode

# PUBKEY pre-String:
# ASN.1 STRUCTURE FOR PUBKEY (uncompressed and compressed):
#   30  <-- declares the start of an ASN.1 sequence
#   56  <-- length of following sequence (dez 86)
#   30  <-- length declaration is following
#   10  <-- length of integer in bytes (dez 16)
#   06  <-- declares the start of an "octet string"
#   07  <-- length of integer in bytes (dez 7)
#   2a 86 48 ce 3d 02 01 <-- Object Identifier: 1.2.840.10045.2.1
#                            = ecPublicKey, ANSI X9.62 public key type
#   06  <-- declares the start of an "octet string"
#   05  <-- length of integer in bytes (dez 5)
#   2b 81 04 00 0a <-- Object Identifier: 1.3.132.0.10
#                      = secp256k1, SECG (Certicom) named eliptic curve
#   03  <-- declares the start of an "octet string"
#   42  <-- length of bit string to follow (66 bytes)
#   00  <-- Start pubkey??
#
# example for setup of 'pre' public key strings above:
#   openssl ecparam -name secp256k1 -genkey -out ec-priv.pem
#   openssl ec -in ec-priv.pem -pubout -out ec-pub.pem
#   openssl ec -in ec-priv.pem -pubout -conv_form compressed -out ec-pub_c.pem
#   cat ec-pub.pem
#   cat ec-pub_c.pem
#   echo "MFYwEAYHKoZIzj0CAQYFK4EEAAoDQgAEAd+5gxspjAfO7HA8qq0/    \
#         7NbHrtTA3z9QNeI5TZ8v0l1pMJ1+mkg3d6zZVUXzMQZ/Y41iID+JAx/ \
#         sQrY+wqVU/g==" | base64 -D - > ec-pub_uc.hex
#   echo "MDYwEAYHKoZIzj0CAQYFK4EEAAoDIgACAd+5gxspjAfO7HA8qq0/7Nb \
#         HrtTA3z9QNeI5TZ8v0l0=" | base64 -D - > ec-pub_c.hex
#   hexdump -C ec-pub_uc.hex
#   hexdump -C ec-pub_c.hex
#
# @see https://github.com/selfcustody/krux/blob/a63dc4ae917afc7ecd7773e6a4b13c23ea2da4d3/krux#L139
# @see https://github.com/pebwindkraft/trx_cl_suite/blob/master/tcls_key2pem.sh#L134
UNCOMPRESSED_PUBKEY_PREPEND = "3056301006072A8648CE3D020106052B8104000A034200"
COMPRESSED_PUBKEY_PREPEND = "3036301006072A8648CE3D020106052B8104000A032200"

parser = argparse.ArgumentParser(
    prog="krux-file-signer",
    description="".join(
        [
            "This python script is a tool to create air-gapped signatures of files using Krux. ",
            "The script can also converts hex publics exported from Krux to PEM public keys so ",
            "signatures can be verified using openssl.",
        ]
    ),
)

subparsers = parser.add_subparsers(help="sub-command help", dest="command")

# Sign command
signer = subparsers.add_parser("sign", help="sign a file")
signer.add_argument("-f", "--file", dest="file_to_sign", help="path to file to sign")

signer.add_argument(
    "-o",
    "--owner",
    dest="file_owner",
    help="the owner's name of public key certificate, i.e, the .pem file (default: 'pubkey')",
    default="pubkey",
)

signer.add_argument(
    "-u",
    "--uncompressed",
    dest="uncompressed_pub_key",
    action="store_true",
    help="flag to create a uncompreesed public key (default: False)",
)

signer.add_argument(
    "-l",
    "--verbose-log",
    dest="verbose",
    action="store_true",
    help="verbose output (default: False)",
    default=False,
)

# Verify command
verifier = subparsers.add_parser("verify", help="verify signature")
verifier.add_argument("-f", "--file", dest="verify_file", help="path to file to verify")

verifier.add_argument(
    "-s", "--sig-file", dest="sig_file", help="path to signature file"
)

verifier.add_argument("-p", "--pub-file", dest="pub_file", help="path to pubkey file")


def _now() -> str:
    return time.strftime("%X %x %Z")


def verbose_log(v_data):
    """Prints verbose data preceded by current time"""
    print(f"[{_now()}] {v_data}")


def make_qr_code(**kwargs) -> str:
    """
    Builds the ascii data to QR code

    Kwargs:
        :param data
            The data to be encoded in qrcode
        :param verbose
            Apply verbose or not
    """
    qr_data = kwargs.get("data")
    verbose = kwargs.get("verbose")

    qr_code = QRCode()

    if verbose:
        verbose_log(f"Adding (data={qr_data})")

    qr_code.add_data(qr_data)
    qr_string = StringIO()
    qr_code.print_ascii(out=qr_string, invert=True)
    return qr_string.getvalue()


def scan(**kwargs) -> str:
    """Opens a scan window and uses cv2 to detect and decode a QR code, returning its data"""
    verbose = kwargs.get("versbose")

    if verbose:
        verbose_log("Opening camera")
    vid = cv2.VideoCapture(0)

    if verbose:
        verbose_log("Setup QRCodeDetector")

    detector = cv2.QRCodeDetector()
    qr_data = None
    while True:
        # Capture the video frame by frame
        # use some dummy vars (__+[a-zA-Z0-9]*?$)
        # to avoid the W0612 'Unused variable' pylint message
        _ret, frame = vid.read()
        if verbose:
            verbose_log(f"reading (_ret={_ret}, frame={frame})")

        qr_data, bbox, straight_qrcode = detector.detectAndDecode(frame)

        if verbose:
            verbose_log(
                f"reading (qr_data={qr_data}, bbox={bbox}, straight_qrcode={straight_qrcode})"
            )

        # Verify null data
        if verbose:
            verbose_log(f"len(qr_data) = {len(qr_data)}")

        if len(qr_data) > 0:
            break

        # Display the resulting frame
        if verbose:
            verbose_log(f"Showing (frame={frame})")
        cv2.imshow("frame", frame)

        # the 'q' button is set as the
        # quitting button you may use any
        # desired button of your choice
        if cv2.waitKey(1) & 0xFF == ord("q"):
            if verbose:
                verbose_log("quiting...")
            break

    # After the loop release the cap object
    vid.release()

    # Destroy all the windows
    cv2.destroyAllWindows()

    return qr_data


def verify(**kwargs):
    """Uses openssl to verify
    if(verboset:
    vverbose_log('qhe signature and public key"""
    print("Verifying signature:")

    file2verify = kwargs.get("filename")
    pub_key_file = kwargs.get("pubkey")
    sig_file = kwargs.get("sigfile")
    verbose = kwargs.get("verbose")

    __command__ = " ".join(
        [
            f"openssl sha256 <{file2verify} -binary",
            "|",
            f"openssl pkeyutl -verify -pubin -inkey {pub_key_file}",
            f"-sigfile {sig_file}",
        ]
    )
    try:
        if verbose:
            print(__command__)
        subprocess.run(__command__, check=True, shell=True)
    except subprocess.CalledProcessError as __exc__:
        raise subprocess.CalledProcessError(
            "Invalid command", cmd=__command__
        ) from __exc__


def open_and_hash_file(**kwargs) -> str:
    """ "
    Read file from --file argument on `sign` command and return its hash

    Kwargs:
        :param path
            The path of file to be hashed
        :param verbose
            Apply verbose or not
    """
    __filename__ = kwargs.get("path")
    __verbose__ = kwargs.get("verbose")

    try:
        with open(__filename__, "rb") as file_to_sign:
            _bytes = file_to_sign.read()  # read file as bytes
            __readable_hash__ = hashlib.sha256(_bytes).hexdigest()

            # Prints the hash of the file
            if __verbose__:
                verbose_log(f"Hash of {__filename__}: {__readable_hash__}")
            return __readable_hash__
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Unable to read target file: {args.file_to_sign}"
        ) from exc


def save_hashed_file(**kwargs):
    """
    Appends '.sha256.txt' to `**kwargs<path>`
    and creates its hashed file with `data` content

    Kwargs:
        :param data
            The data to hashed
        :param path
            The <path>.sha256.txt
        :param verbose
            Apply verbose or not
    """
    __data__ = kwargs.get("data")
    __path__ = kwargs.get("path")
    verbose = kwargs.get("verbose")

    __hash_file__ = f"{__path__}.sha256sum.txt"

    if verbose:
        verbose_log(f"Saving a hash file: {__hash_file__}")

    with open(__hash_file__, mode="w", encoding="utf-8") as hash_file:
        hash_file.write(f"{__data__} {__hash_file__}")


def scan_and_save_signature(**kwargs):
    """
    Scan with camera the generated signatue

    Kwargs:
        :param verbose
    """
    verbose = kwargs.get("verbose")

    _ = input(f"[{_now()}] Press enter to scan signature")

    if verbose:
        verbose_log("Scanning...")

    signature = scan()
    binary_signature = base64.b64decode(signature.encode())

    if verbose:
        verbose_log(f"Signature: {binary_signature}")

    # Saves a signature file
    signature_file = f"{args.file_to_sign}.sig"
    verbose_log("Saving a signature file:" + signature_file)
    with open(signature_file, "wb") as sig_file:
        sig_file.write(binary_signature)


def scan_public_key(**kwargs) -> str:
    """
    Scan with camera the generated public key

    Kwargs:
        :param verbose
    """

    verbose = kwargs.get("verbose")

    _ = input(f"[{_now()}] Press enter to scan public key")

    if verbose:
        verbose_log("Scanning...")

    public_key = scan()

    if verbose:
        verbose_log(f"Public key: {public_key}")

    return public_key


def scan_and_create_public_key_certificate(**kwargs):
    """
    Create public key certifficate file (.pem)

    Kwargs:
        :param pubkey
            The generated public key
        :param uncompressed
            Flag to create a uncompressed public key certificate
        :param owner
            Owner of public key certificate
        :param verbose
            Apply verbose or not
    """

    hex_pubkey = kwargs.get("pubkey")
    uncompressed = kwargs.get("uncompressed")
    owner = kwargs.get("owner")
    verbose = kwargs.get("verbose")

    if uncompressed:
        if verbose:
            verbose_log("Creating uncompressed public key certificate")
        __public_key_data__ = f"{UNCOMPRESSED_PUBKEY_PREPEND}{hex_pubkey}"
    else:
        if verbose:
            verbose_log("Creating compressed public key certificate")
        __public_key_data__ = f"{COMPRESSED_PUBKEY_PREPEND}{hex_pubkey}"

    public_key_base64 = base64.b64encode(bytes.fromhex(__public_key_data__)).decode(
        "utf-8"
    )
    __pem_pub_key__ = "\n".join(
        ["-----BEGIN PUBLIC KEY-----", public_key_base64, "-----END PUBLIC KEY-----"]
    )

    if verbose:
        verbose_log(__pem_pub_key__)

    __pub_key_file__ = f"{owner}.pem"
    if verbose:
        verbose_log(f"Saving public key file: {__pub_key_file__}")
    with open(__pub_key_file__, mode="w", encoding="utf-8") as pem_file:
        pem_file.write(__pem_pub_key__)


args = parser.parse_args()

# If the sign command was given
if args.command == "sign" and args.file_to_sign is not None:
    # read file
    file_hash = open_and_hash_file(path=args.file_to_sign, verbose=args.verbose)

    # Saves a hash file
    save_hashed_file(data=file_hash, path=args.file_to_sign, verbose=args.verbose)

    # Shows some message
    verbose_log("To sign this file with Krux: ")
    verbose_log(" (a) load a 24 words key;")
    verbose_log(" (b) use the Sign->Message feature;")
    verbose_log(" (c) and scan this QR code below.")

    # Prints the QR code
    __qrcode__ = make_qr_code(data=file_hash, verbose=args.verbose)
    print(f"\n{__qrcode__}")

    # Scans the signature QR code and saves it
    scan_and_save_signature(verbose=args.verbose)

    # Scans the public KeyboardInterrupt
    pubkey = scan_public_key(verbose=args.verbose)

    # Create PEM data
    # Save PEM data to a file
    # with filename as owner's name
    scan_and_create_public_key_certificate(
        pubkey=pubkey,
        uncompressed=args.uncompressed_pub_key,
        owner=args.file_owner,
        verbose=args.verbose,
    )

# Else if the verify command was given
elif (
    args.command == "verify"
    and args.verify_file is not None
    and args.sig_file is not None
    and args.pub_file is not None
):
    verify(filename=args.verify_file, pubkey=args.pub_file, sigfile=args.sig_file)
# If command was not found
else:
    parser.print_help()
