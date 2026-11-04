"""
AdamOCR — استخراج نصوص وحقول وخدمات من فواتير طبية PDF
- PyMuPDF + Tesseract OCR
- استخراج: بيانات المريض + doctor_name_raw + services (اسم عربي + كمية فقط)
"""
import os
import re
import json
import shutil
import platform

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, 'input_pdfs')
OUTPUT_DIR = os.path.join(BASE_DIR, 'results')


def _setup_tesseract():
    try:
        import pytesseract
        if shutil.which('tesseract'):
            return
        if platform.system() == 'Windows':
            for c in [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                os.path.expanduser(r'~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'),
            ]:
                if os.path.exists(c):
                    pytesseract.pytesseract.tesseract_cmd = c
                    user_tessdata = os.path.expanduser(r'~\tessdata')
                    if os.path.exists(os.path.join(user_tessdata, 'ara.traineddata')):
                        os.environ['TESSDATA_PREFIX'] = user_tessdata
                    return
    except Exception as e:
        print(f'  tesseract setup error: {e}')


_setup_tesseract()


def clean_rtl_marks(text):
    if not text:
        return ''
    text = re.sub(r'[\u200E\u200F\u202A-\u202E\u2066-\u2069\u061C]', '', text)
    text = text.replace('', '').replace('', '')
    return text


def extract_text_pymupdf(pdf_path):
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        text = ''.join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception as e:
        print(f'  PyMuPDF error: {e}')
        return ''


def extract_text_ocr(pdf_path):
    try:
        import pymupdf
        from PIL import Image
        import pytesseract
        import io
        doc = pymupdf.open(pdf_path)
        text = ''
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes('png')))
            page_text = pytesseract.image_to_string(img, lang='ara+eng')
            text += f'\n--- صفحة {i + 1} ---\n' + page_text
        doc.close()
        return text
    except Exception as e:
        print(f'  OCR error: {e}')
        return ''


def is_text_usable(text):
    if not text or len(text.strip()) < 100:
        return False
    arabic = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    letters = sum(1 for c in text if c.isalpha())
    if letters == 0:
        return False
    return arabic / letters > 0.15


def extract_header_fields(original_text):
    text = clean_rtl_marks(original_text)
    fields = {
        'patient_name': None, 'national_id': None, 'doctor_name_raw': None,
        'specialty': None, 'admission_date': None, 'discharge_date': None,
        'diagnosis': None, 'hospital_name': None, 'referral_number': None,
        'total_amount': None,
    }

    m = re.search(r'([A-Z][a-zA-Z\s\.]+?)\s+إسم\s+الطبيب', text)
    if m:
        fields['doctor_name_raw'] = m.group(1).strip()
    else:
        m = re.search(r'إسم\s+الطبيب\s*:?\s*([A-Za-z][a-zA-Z\s\.]+)', text)
        if m:
            fields['doctor_name_raw'] = m.group(1).strip()

    m = re.search(r'إسم\s+المريض\s*:?\s*([^\n]+)', text)
    if m:
        fields['patient_name'] = m.group(1).strip()

    m = re.search(r'الرقم\s+القومي\s*:?\s*(\d{10,14})', text)
    if m:
        fields['national_id'] = m.group(1)

    m = re.search(r'التخصص\s*:?\s*([^\n]+)', text)
    if m:
        fields['specialty'] = m.group(1).strip()

    m = re.search(r'وقت\s+الدخول\s*:?\s*(?:\d{1,2}:\d{2}:\d{2})?\s*(\d{1,2}/\d{1,2}/\d{4})', text)
    if m:
        fields['admission_date'] = m.group(1)
    m = re.search(r'وقت\s+الخروج\s*:?\s*(?:\d{1,2}:\d{2}:\d{2})?\s*(\d{1,2}/\d{1,2}/\d{4})', text)
    if m:
        fields['discharge_date'] = m.group(1)

    m = re.search(r'إسم\s+المنشأ[هة]?\s*:?\s*([A-Z][a-zA-Z\s\.]+)', text)
    if m:
        fields['hospital_name'] = m.group(1).strip().rstrip('اع').strip()

    m = re.search(r'رقم\s+الإحالة\s*:?\s*([A-Z0-9]{8,})', text)
    if m:
        fields['referral_number'] = m.group(1)

    m = re.search(r'Primary\s*-\s*([A-Z0-9]+\s*-\s*[A-Z0-9]+[^\n]+?)(?:\s+Secondary|$)', text)
    if m:
        fields['diagnosis'] = m.group(1).strip()

    matches = re.findall(r'الإجمال[ىي]\s+([\d.]+)', text)
    if matches:
        try:
            fields['total_amount'] = float(max(matches, key=lambda x: float(x)))
        except Exception:
            pass

    return fields


UNITS = [
    'عدد', 'قطعة', 'قطعه', 'دزينة', 'دزينه', 'علبة', 'علبه',
    'أمبول', 'امبول', 'فيال', 'سم', 'مجم', 'ملجم', 'جرام', 'كيس',
    'زجاجة', 'زجاجه', 'بكرة', 'بكره', 'متر', 'لتر', 'زوج',
    'شريط', 'شريطه', 'أنبوبة', 'انبوبة', 'باكو', 'باكيت',
    'صندوق', 'صندوقه', 'حبة', 'حبه', 'قرص', 'اقراص', 'كبسولة',
    'pac', 'pack', 'pcs', 'tab', 'tabs', 'cap', 'caps', 'ml', 'mg', 'g', 'kg',
    'piece', 'pieces', 'amp', 'vial', 'box', 'bottle', 'drop', 'drops',
    'unit', 'units', 'dose', 'doses',
]
UNITS_PATTERN = '|'.join(re.escape(u) for u in UNITS)

HEADER_KEYWORDS = [
    'كود الخدمة', 'اسم الخدمة', 'الكمية', 'سعر الوحدة',
    'حصة المريض', 'حصة التأمين', 'الإجمالي', 'الإجمالى',
    'نوع المريض', 'صفحة', 'Page of', 'مريض خارجى', 'مريض داخلى', 'مريض طوارئ',
    'BLIPBILL', 'فاتورة', 'الهيئة العامة', 'مستشفى الحياة',
    'UNIVERSAL HEALTH', 'إسم المريض', 'إسم المنشأ', 'الرقم القومي',
    'التخصص', 'رقم الإحالة', 'Visit Type', 'Bill Date', 'Primary',
    'Secondary', 'تاريخ', 'وقت', 'Inpatient',
]


def _clean_line(line):
    line = re.sub(r'[-—~_]+', ' ', line)
    line = re.sub(r'\.{2,}', ' ', line)
    line = re.sub(r'[^\w\s\./()\u0600-\u06FF]', ' ', line)
    line = re.sub(r'\s+', ' ', line).strip()
    return line


def extract_services(original_text):
    text = clean_rtl_marks(original_text)
    services = []
    seen_names = set()

    def extract_section(section_names):
        for sn in section_names:
            pattern = rf'{sn}\s*:?\s*(.*?)(?=خدمات |الصيدلية|الإجمال[ىي]|$)'
            m = re.search(pattern, text, re.DOTALL)
            if m:
                return m.group(1)
        return ''

    section_groups = [
        (['الخدمات الآخر', 'الخدمات الأخرى', 'الخدمات الاخرى', 'الخدمات الاخر'], 'الخدمات الأخرى'),
        (['الصيدلية', 'صيدلية'], 'الصيدلية'),
        (['خدمات المعمل', 'معمل'], 'خدمات المعمل'),
        (['خدمات الأشعة', 'أشعة', 'اشعة'], 'خدمات الأشعة'),
    ]

    for patterns, display_name in section_groups:
        section_text = extract_section(patterns)
        if not section_text:
            continue

        for raw_line in section_text.split('\n'):
            line = raw_line.strip()
            if not line:
                continue
            if any(kw in line for kw in HEADER_KEYWORDS):
                continue

            line_clean = _clean_line(line)
            if not line_clean:
                continue

            m = re.search(
                r'(.+?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*$',
                line_clean
            )
            if not m:
                continue

            prefix = m.group(1).strip()

            prefix = re.sub(r'^[\w\.\-\s/]{10,}?(?=[\u0600-\u06FF])', '', prefix).strip()
            prefix = re.sub(r'^[\d\.\-\s]+', '', prefix).strip()
            prefix = re.sub(r'\b\d{5,}\b.*$', '', prefix).strip()
            prefix = re.sub(
                rf'\s+(?:{UNITS_PATTERN})\s+\d+(?:\.\d+)?\s*$',
                '', prefix, flags=re.IGNORECASE
            ).strip()
            prefix = re.sub(
                rf'\s+(?:{UNITS_PATTERN})\s*$',
                '', prefix, flags=re.IGNORECASE
            ).strip()

            qty_m = re.search(r'(\d+)\s*$', prefix)
            if not qty_m:
                continue
            qty = int(qty_m.group(1))

            name = prefix[:qty_m.start()].strip()
            name = re.sub(r'\s+', ' ', name).strip()
            name = re.sub(r'[-—~_.]+$', '', name).strip()
            name = re.sub(r'^[-—~_.]+', '', name).strip()

            if not name or len(name) < 5:
                continue
            if qty <= 0 or qty > 10000:
                continue

            key = f'{display_name}|{name}|{qty}'
            if key in seen_names:
                continue
            seen_names.add(key)

            services.append({
                'section': display_name,
                'raw_name': name,
                'qty': qty,
            })

    return services


def process_pdf(pdf_path):
    filename = os.path.basename(pdf_path)
    print(f'Processing: {filename}')
    text = extract_text_pymupdf(pdf_path)
    used_ocr = False
    if not is_text_usable(text):
        print('  Text not usable, falling back to OCR...')
        text = extract_text_ocr(pdf_path)
        used_ocr = True

    fields = extract_header_fields(text)
    services = extract_services(text)

    result = {
        'filename': filename,
        'used_ocr': used_ocr,
        'text_length': len(text),
        'fields': fields,
        'services': services,
        'raw_text': text,
    }

    output_name = os.path.splitext(filename)[0] + '.json'
    output_path = os.path.join(OUTPUT_DIR, output_name)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'  Saved: {output_path} ({len(text)} chars, OCR={used_ocr}, services={len(services)})')
    return result


def main():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pdfs = sorted(f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.pdf')) if os.path.exists(INPUT_DIR) else []
    if not pdfs:
        print(f'No PDFs found in {INPUT_DIR}/')
        return
    print(f'Found {len(pdfs)} PDF(s)')
    for pdf in pdfs:
        try:
            process_pdf(os.path.join(INPUT_DIR, pdf))
        except Exception as e:
            print(f'Error processing {pdf}: {e}')
    print('Done.')


if __name__ == '__main__':
    main()