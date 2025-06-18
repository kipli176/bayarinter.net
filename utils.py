import requests

def kirim_tagihan(no_hp, nama, jumlah_tagihan, bulan):
    WA_API_URL = "http://194.163.184.129:3001/send-message"
    WA_HEADERS = {"Content-Type": "application/json"}

    # Format rupiah
    rupiah = f"Rp {jumlah_tagihan:,.0f}".replace(",", ".")

    message = (
        f"📢 Halo {nama},\n\n"
        f"Ini adalah pengingat untuk tagihan internet Anda bulan *{bulan}*.\n"
        f"Jumlah tagihan: *{rupiah}*\n\n"
        f"Silakan lakukan pembayaran tepat waktu untuk menghindari gangguan layanan.\n\n"
        f"Terima kasih.\n(Admin Billing)"
    )

    payload = {"number": no_hp, "message": message}
    try:
        response = requests.post(WA_API_URL, headers=WA_HEADERS, json=payload, timeout=10)
        return response.ok
    except:
        return False
import re

def normalize_nomor_hp(nomor):
    """
    Normalisasi nomor WhatsApp menjadi format 628xxxxxxxxx.
    Contoh:
        "+62 812-3456-7890" → "6281234567890"
        "0812 3456 7890" → "6281234567890"
    """
    # Hapus spasi, strip, tanda plus
    nomor = re.sub(r'[\s\-\+]', '', nomor)

    # Ganti awalan 0 dengan 62
    if nomor.startswith('0'):
        nomor = '62' + nomor[1:]
    elif nomor.startswith('62'):
        pass
    elif nomor.startswith('8'):  # misal: "81234567890"
        nomor = '62' + nomor
    else:
        # fallback, tidak valid
        return ''

    return nomor
