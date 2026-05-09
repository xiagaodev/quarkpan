#!/usr/bin/env python3
from pathlib import Path
from .logger import get_logger

def print_ascii_qr(text: str):
    logger = get_logger(__name__)
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(text)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception as e:
        logger.warning(f"ASCII QR render failed: {e}")

def display_qr_from_url(url: str):
    print_ascii_qr(url)

def display_qr_code(qr_image_path: str):
    logger = get_logger(__name__)
    logger.info("QR code saved, please scan with Quark app")
