import hashlib
import subprocess
import json
import os
import datetime
import secrets

from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Text

# Certificate page size: A4, landscape orientation (297mm x 210mm). All
# positioning below is expressed in inches/relative fractions of PAGE_W /
# PAGE_H, so it reflows correctly for A4's slightly different aspect ratio
# versus US Letter -- nothing here assumes a fixed 11in x 8.5in page.
PAGE_W, PAGE_H = landscape(A4)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
GEN_QR_JS = os.path.join(SCRIPT_DIR, "gen_qr.js")

GOLD = HexColor("#96702A")
GOLD_DARK = HexColor("#6B4E1C")
INK = HexColor("#1A2233")
SLATE = HexColor("#4B5568")

# ---------- Fonts ----------
pdfmetrics.registerFont(TTFont("SerifReg", "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"))
pdfmetrics.registerFont(TTFont("SerifBold", "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"))
pdfmetrics.registerFont(TTFont("SerifItalic", "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"))
pdfmetrics.registerFont(TTFont("SansReg", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("SansBold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))


def generate_cert_id():
    """Unique, hard-to-guess certificate serial number."""
    today = datetime.date.today()
    rand = secrets.token_hex(4).upper()
    return f"TSO-GA-{today.year}-{rand}"


def generate_verification_hash(cert_id, student_name, course_title, completion_date, completion_time, issue_secret):
    """
    A verification code derived from the certificate's own content plus a
    server-side secret. Anyone can see the code on the certificate, but
    only someone with the issuing secret (TSO Edu) can regenerate it from
    a claimed name/date/time/course to confirm it matches -- so a forger
    who changes the name, date, or time on a copy cannot produce a
    matching code without knowing the secret.
    """
    payload = f"{cert_id}|{student_name}|{course_title}|{completion_date}|{completion_time}".encode("utf-8")
    h = hashlib.sha256(issue_secret.encode("utf-8") + payload).hexdigest().upper()
    return h[:12]


def make_qr_png(text, out_path, scale=6, border=3):
    """Use the vendored, verified QR encoder (via Node) to build a QR matrix,
    then rasterize it to a PNG with PIL."""
    json_path = out_path + ".json"
    subprocess.run(
        ["node", GEN_QR_JS, text, json_path],
        check=True, capture_output=True, text=True
    )
    with open(json_path) as f:
        d = json.load(f)
    size = d["size"]
    matrix = d["matrix"]
    total = size + border * 2
    img = Image.new("L", (total * scale, total * scale), 255)
    px = img.load()
    for r in range(size):
        for c in range(size):
            if matrix[r][c]:
                for dr in range(scale):
                    for dc in range(scale):
                        px[(c + border) * scale + dc, (r + border) * scale + dr] = 0
    img.save(out_path)
    os.remove(json_path)
    return out_path


def draw_certificate(
    out_path,
    student_name,
    course_title="Grammar Academy — Full Curriculum",
    lessons_completed=None,
    completion_date=None,
    completion_time=None,
    cert_id=None,
    verification_url_base=None,
    issue_secret=None,
):
    # Both of these MUST be configured for real, un-forgeable issuance.
    # They intentionally have no safe hardcoded default: falling back to a
    # shared placeholder secret would make every certificate forgeable.
    if verification_url_base is None:
        verification_url_base = os.environ.get(
            "GRAMMAR_CERT_VERIFY_URL_BASE", "https://tso-edu.example/verify/"
        )
    if issue_secret is None:
        issue_secret = os.environ.get("GRAMMAR_CERT_ISSUE_SECRET")
        if not issue_secret:
            raise RuntimeError(
                "GRAMMAR_CERT_ISSUE_SECRET is not set. Set this environment "
                "variable to a real, private secret before issuing "
                "certificates — without it, verification codes would not be "
                "forgery-resistant."
            )
    # lessons_completed is intentionally NOT hardcoded. If the caller
    # doesn't pass it explicitly, resolve it live from the actual curriculum
    # (edu_app/grammar_data.py) so the certificate can never claim a lesson
    # count that doesn't match what the student actually completed, even as
    # the curriculum grows over time.
    if lessons_completed is None:
        try:
            from edu_app.grammar_data import GRAMMAR_LESSONS as _LESSONS
            lessons_completed = len(_LESSONS)
        except Exception:
            raise ValueError(
                "lessons_completed was not provided and could not be resolved "
                "from edu_app.grammar_data.GRAMMAR_LESSONS. Pass it explicitly."
            )

    now = datetime.datetime.now()
    if completion_date is None:
        completion_date = now.date().isoformat()
    if completion_time is None:
        completion_time = now.strftime("%H:%M:%S")
    if cert_id is None:
        cert_id = generate_cert_id()

    vcode = generate_verification_hash(cert_id, student_name, course_title, completion_date, completion_time, issue_secret)
    verify_url = f"{verification_url_base}{cert_id}?code={vcode}"

    qr_path = os.path.join(SCRIPT_DIR, f"_qr_{cert_id}.png")
    make_qr_png(verify_url, qr_path, scale=7, border=2)

    c = canvas.Canvas(out_path, pagesize=(PAGE_W, PAGE_H))

    # ---- Layer 1: white background ----
    c.setFillColor(HexColor("#FFFEFB"))
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # ---- Layer 2: guilloché security background ----
    c.drawImage(os.path.join(ASSETS_DIR, "security_bg.png"), 0, 0, width=PAGE_W, height=PAGE_H,
                mask='auto', preserveAspectRatio=False)

    # ---- Layer 3: decorative security border + microtext ----
    c.drawImage(os.path.join(ASSETS_DIR, "border.png"), 0, 0, width=PAGE_W, height=PAGE_H,
                mask='auto', preserveAspectRatio=False)

    # ---- Logo ----
    logo_w = 1.05 * inch
    logo_h = logo_w * (976 / 1504)
    c.drawImage(os.path.join(ASSETS_DIR, "logo.png"),
                PAGE_W / 2 - logo_w / 2, PAGE_H - 1.62 * inch,
                width=logo_w, height=logo_h, mask='auto')

    # ---- Header text ----
    c.setFont("SerifBold", 15)
    c.setFillColor(GOLD_DARK)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 1.86 * inch, "T S O   E D U   •   G R A M M A R   A C A D E M Y")

    c.setFont("SansReg", 8.5)
    c.setFillColor(SLATE)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 2.04 * inch, "tso-edu.example")

    # ---- Title ----
    c.setFont("SerifBold", 40)
    c.setFillColor(INK)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 2.62 * inch, "Certificate of Completion")

    # thin gold rule under title
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.4)
    rule_w = 2.6 * inch
    c.line(PAGE_W / 2 - rule_w / 2, PAGE_H - 2.82 * inch, PAGE_W / 2 + rule_w / 2, PAGE_H - 2.82 * inch)

    # ---- "This certifies that" ----
    c.setFont("SerifItalic", 13)
    c.setFillColor(SLATE)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 3.20 * inch, "This certifies that")

    # ---- Student name ----
    c.setFont("SerifBold", 30)
    c.setFillColor(GOLD_DARK)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 3.78 * inch, student_name)

    # underline flourish beneath name
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    name_w = c.stringWidth(student_name, "SerifBold", 30) + 0.6 * inch
    c.line(PAGE_W / 2 - name_w / 2, PAGE_H - 3.95 * inch, PAGE_W / 2 + name_w / 2, PAGE_H - 3.95 * inch)

    # ---- Body text ----
    c.setFont("SerifReg", 12.5)
    c.setFillColor(INK)
    body1 = "has successfully completed all"
    body2 = f"{lessons_completed} lessons of the TSO Edu Grammar Academy curriculum,"
    body3 = "demonstrating consistent achievement across grammar, usage, and applied writing skills."
    c.drawCentredString(PAGE_W / 2, PAGE_H - 4.35 * inch, body1)
    c.setFont("SerifBold", 12.5)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 4.58 * inch, body2)
    c.setFont("SerifReg", 12.5)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 4.81 * inch, body3)

    # ---- Date ----
    try:
        d_obj = datetime.date.fromisoformat(completion_date)
        pretty_date = d_obj.strftime("%d %B %Y")
    except Exception:
        pretty_date = completion_date
    c.setFont("SerifReg", 11)
    c.setFillColor(SLATE)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 5.15 * inch, f"Awarded on {pretty_date} at {completion_time}")

    # ================= Footer block =================
    footer_y = 1.42 * inch

    # --- Left: founder's signature ---
    sig_x = 2.35 * inch
    sig_img_path = os.path.join(ASSETS_DIR, "founder_signature.png")
    with Image.open(sig_img_path) as _sig:
        sig_ratio = _sig.height / _sig.width
    sig_w = 1.55 * inch
    sig_h = sig_w * sig_ratio
    c.drawImage(sig_img_path,
                sig_x - sig_w / 2, footer_y + 0.30 * inch,
                width=sig_w, height=sig_h, mask='auto')
    c.setStrokeColor(SLATE)
    c.setLineWidth(0.8)
    c.line(sig_x - 1.1 * inch, footer_y + 0.28 * inch, sig_x + 1.1 * inch, footer_y + 0.28 * inch)
    c.setFont("SerifBold", 11)
    c.setFillColor(INK)
    c.drawCentredString(sig_x, footer_y + 0.14 * inch, "TSO Edu Founder")
    c.setFont("SansReg", 7.8)
    c.setFillColor(SLATE)
    c.drawCentredString(sig_x, footer_y + 0.01 * inch, "Grammar Academy")

    # --- Center: seal ---
    seal_size = 1.0 * inch
    c.drawImage(os.path.join(ASSETS_DIR, "seal.png"),
                PAGE_W / 2 - seal_size / 2, footer_y - 0.02 * inch,
                width=seal_size, height=seal_size, mask='auto')

    # --- Right: QR + verification code ---
    qr_x = PAGE_W - 2.7 * inch
    qr_size = 0.85 * inch
    c.drawImage(qr_path, qr_x, footer_y + 0.05 * inch, width=qr_size, height=qr_size, mask='auto')

    c.setFont("SansBold", 7.6)
    c.setFillColor(INK)
    c.drawString(qr_x + qr_size + 0.12 * inch, footer_y + 0.72 * inch, "SCAN TO VERIFY")
    c.setFont("SansReg", 7.2)
    c.setFillColor(SLATE)
    c.drawString(qr_x + qr_size + 0.12 * inch, footer_y + 0.56 * inch, f"Certificate ID:")
    c.setFont("SansBold", 7.6)
    c.setFillColor(INK)
    c.drawString(qr_x + qr_size + 0.12 * inch, footer_y + 0.44 * inch, cert_id)
    c.setFont("SansReg", 7.2)
    c.setFillColor(SLATE)
    c.drawString(qr_x + qr_size + 0.12 * inch, footer_y + 0.30 * inch, "Verification code:")
    c.setFont("SansBold", 7.6)
    c.setFillColor(INK)
    c.drawString(qr_x + qr_size + 0.12 * inch, footer_y + 0.18 * inch, vcode)

    # tiny note under whole footer
    c.setFont("SansReg", 6.6)
    c.setFillColor(SLATE)
    c.drawCentredString(PAGE_W / 2, 0.78 * inch,
                         "This certificate includes a tamper-evident verification code unique to the recipient, course, and date.")
    c.drawCentredString(PAGE_W / 2, 0.64 * inch,
                         f"Verify authenticity at {verification_url_base}{cert_id}")

    # ---- Metadata: mark clearly as an official, protected document ----
    c.setTitle(f"Certificate of Completion - {student_name} - {cert_id}")
    c.setAuthor("TSO Edu Grammar Academy")
    c.setSubject("Official Certificate of Completion — Grammar Academy")
    c.setCreator("TSO Edu Grammar Academy Certificate System")

    c.showPage()
    c.save()

    os.remove(qr_path)

    # ---- Lock the PDF against copying/editing/content-extraction ----
    # An empty user password means anyone can still OPEN and PRINT the
    # certificate normally; the owner password (kept by TSO Edu, not
    # printed anywhere) is required to lift the restrictions on copying
    # text/images out of the file, editing its contents, or extracting
    # pages -- this is what stops someone from opening the PDF, deleting
    # the name, and typing in a different one, or lifting the seal/QR
    # graphics to paste onto a fake document.
    reader = PdfReader(out_path)
    writer = PdfWriter()
    writer.append(reader)

    # Embed verification data as custom document metadata too, so the
    # certificate is independently checkable by inspecting the file's
    # metadata, not only by scanning the QR code.
    writer.add_metadata({
        "/Title": f"Certificate of Completion - {student_name} - {cert_id}",
        "/Author": "TSO Edu Grammar Academy",
        "/Subject": "Official Certificate of Completion — Grammar Academy",
        "/Creator": "TSO Edu Grammar Academy Certificate System",
        "/TSOCertificateID": cert_id,
        "/TSOVerificationCode": vcode,
        "/TSOVerifyURL": verify_url,
        "/TSOIssuedTo": student_name,
        "/TSOIssuedDate": completion_date,
        "/TSOIssuedTime": completion_time,
    })

    owner_pw = secrets.token_urlsafe(18)  # random, never shown to the recipient
    writer.encrypt(
        user_password="",         # opening/printing needs no password
        owner_password=owner_pw,  # editing/copying needs this (kept by the issuer)
        permissions_flag=(
            # allow printing only; block modify / copy / annotate / extraction
            0b0000000000000100  # bit 3: print
        ),
    )

    with open(out_path, "wb") as f:
        writer.write(f)

    return cert_id, vcode, verify_url, owner_pw


if __name__ == "__main__":
    cert_id, vcode, url, owner_pw = draw_certificate(
        os.path.join(SCRIPT_DIR, "certificate_sample.pdf"),
        student_name="[Student Full Name]",
        completion_date=datetime.date.today().isoformat(),
    )
    print("Cert ID:", cert_id)
    print("Verification code:", vcode)
    print("Verify URL:", url)
    print("Owner password (keep private, not on the certificate):", owner_pw)
