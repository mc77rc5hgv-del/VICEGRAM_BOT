import io

import qrcode


def config_to_qr_png(config_text: str) -> io.BytesIO:
    img = qrcode.make(config_text)
    buf = io.BytesIO()
    buf.name = "med-vpn-qr.png"
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
