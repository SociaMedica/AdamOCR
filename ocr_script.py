"""
AdamOCR — استخراج نصوص وحقول وخدمات من فواتير طبية PDF
- PyMuPDF + Tesseract OCR
- regex لاستخراج الحقول (بعد تنظيف RTL/LTR marks)
- fuzzy match مع lookup/*.json (أطباء، أصناف، عمليات)
- JSON output
"""
import os
import re
import json
import shutil
import platform
from difflib import SequenceMatcher

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOOKUP_DIR = os.path.join(BASE_DIR, 'lookup')
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


def load_lookup():
    data = {'doctors': [], 'items': [], 'operations': []}
    for key, filename in [
        ('doctors', 'doctors.json'),
        ('items', 'items.json'),
        ('operations', 'operations.json'),
    ]:
        path = os.path.join(LOOKUP_DIR, filename)
        if os.path.exists(path):
            try:
                # utf-8-sig يتعامل مع BOM
                with open(path, 'r', encoding='utf-8-sig') as f:
                    data[key] = json.load(f)
                print(f'  Loaded {len(data[key])} {key}')
            except Exception as e:
                print(f'  Error loading {filename}: {e}')
        else:
            print(f'  Lookup missing: {path}')
    return data


LOOKUP = load_lookup()


def clean_rtl_marks(text):
    """إزالة RTL/LTR marks والأحرف الخفية اللي بتلخبط regex."""
    if not text:
        return ''
    # U+200E (LTR mark), U+200F (RTL mark), U+202A-U+202E (embedding), U+2066-U+2069 (isolate)
    text = re.sub(r'[\u200E\u200F\u202A-\u202E\u2066-\u2069\u061C]', '', text)
    # تحويل بعض الأحرف العربية الخاصة
    text = text.replace('', '').replace('', '')
    return text


def _normalize_arabic(text):
    if not text:
        return ''
    text = re.sub(r'[\u064B-\u0652]', '', text)
    text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    text = text.replace('ة', 'ه').replace('ى', 'ي')
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()


def _normalize_english(text):
    if not text:
        return ''
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text


def match_doctor(name_from_pdf):
    if not name_from_pdf:
        return None
    norm = _normalize_english(name_from_pdf)
    norm_ar = _normalize_arabic(name_from_pdf)
    best, best_ratio = None, 0.0
    for d in LOOKUP['doctors']:
        eng = _normalize_english(d.get('english_name', ''))
        full_ar = _normalize_arabic(d.get('full_name', ''))
        triple = _normalize_arabic(d.get('triple_name', ''))
        r1 = SequenceMatcher(None, norm, eng).ratio() if eng else 0
        r2 = SequenceMatcher(None, norm_ar, full_ar).ratio() if full_ar else 0
        r3 = SequenceMatcher(None, norm_ar, triple).ratio() if triple else 0
        ratio = max(r1, r2, r3)
        if ratio > best_ratio:
            best_ratio = ratio
            best = d
    if best and best_ratio >= 0.5:
        return {
            'matched_full_name_ar': best['full_name'],
            'matched_english': best['english_name'],
            'similarity': round(best_ratio, 2),
        }
    return None


def match_operation(name_from_pdf):
    if not name_from_pdf:
        return None
    norm = _normalize_arabic(name_from_pdf)
    best, best_ratio = None, 0.0
    for op in LOOKUP['operations']:
        norm_op = _normalize_arabic(op.get('name', ''))
        ratio = SequenceMatcher(None, norm, norm_op).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = op
    if best and best_ratio >= 0.5:
        return {
            'matched_code': best['code'],
            'matched_name': best['name'],
            'similarity': round(best_ratio, 2),
        }
    return None


def match_item(name_from_pdf):
    if not name_from_pdf:
        return None
    norm = _normalize_arabic(name_from_pdf)
    best, best_ratio = None, 0.0
    for it in LOOKUP['items']:
        norm_it = _normalize_arabic(it.get('name', ''))
        ratio = SequenceMatcher(None, norm, norm_it).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = it
    if best and best_ratio >= 0.6:
        return {
            'matched_code': best['code'],
            'matched_name': best['name'],
            'unit': best.get('unit'),
            'similarity': round(best_ratio, 2),
        }
    return None


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
        'patient_name': None, 'national_id': None,
        'doctor_name_raw': None, 'doctor_matched': None,
        'specialty': None, 'admission_date': None, 'discharge_date': None,
        'diagnosis': None, 'hospital_name': None,
        'referral_number': None, 'total_amount': None,
    }

    # الطبيب: الاسم الإنجليزي قبل "إسم الطبيب"
    m = re.search(r'([A-Z][a-zA-Z\s\.]+?)\s+إسم\s+الطبيب', text)
    if m:
        fields['doctor_name_raw'] = m.group(1).strip()
    else:
        # أو بعد "إسم الطبيب:"
        m = re.search(r'إسم\s+الطبيب\s*:?\s*([A-Za-z][a-zA-Z\s\.]+)', text)
        if m:
            fields['doctor_name_raw'] = m.group(1).strip()

    if fields['doctor_name_raw']:
        fields['doctor_matched'] = match_doctor(fields['doctor_name_raw'])

    m = re.search(r'إسم\s+المريض\s*:?\s*([^\n]+)', text)
    if m:
        fields['patient_name'] = m.group(1).strip()

    m = re.search(r'الرقم\s+القومي\s*:?\s*(\d{10,14})', text)
    if m:
        fields['national_id'] = m.group(1)

    m = re.search(r'التخصص\s*:?\s*([^\n]+)', text)
    if m:
        fields['specialty'] = m.group(1).strip()

    # التواريخ (OCR بيحط الوقت قبل التاريخ)
    m = re.search(r'وقت\s+الدخول\s*:?\s*(?:\d{1,2}:\d{2}:\d{2})?\s*(\d{1,2}/\d{1,2}/\d{4})', text)
    if m:
        fields['admission_date'] = m.group(1)
    m = re.search(r'وقت\s+الخروج\s*:?\s*(?:\d{1,2}:\d{2}:\d{2})?\s*(\d{1,2}/\d{1,2}/\d{4})', text)
    if m:
        fields['discharge_date'] = m.group(1)

    # المنشأة: بعد "إسم المنشأ"
    m = re.search(r'إسم\s+المنشأ[هة]?\s*:?\s*([A-Z][a-zA-Z\s\.]+)', text)
    if m:
        fields['hospital_name'] = m.group(1).strip().rstrip('اع').strip()

    # الإحالة
    m = re.search(r'رقم\s+الإحالة\s*:?\s*([A-Z0-9]{8,})', text)
    if m:
        fields['referral_number'] = m.group(1)

    # التشخيص
    m = re.search(r'Primary\s*-\s*([A-Z0-9]+\s*-\s*[A-Z0-9]+[^\n]+?)(?:\s+Secondary|$)', text)
    if m:
        fields['diagnosis'] = m.group(1).strip()

    # الإجمالي
    matches = re.findall(r'الإجمال[ىي]\s+([\d.]+)', text)
    if matches:
        try:
            fields['total_amount'] = float(max(matches, key=lambda x: float(x)))
        except Exception:
            pass

    return fields


def extract_services(original_text):
    text = clean_rtl_marks(original_text)
    services = []

    def extract_section(section_name):
        pattern = rf'{section_name}\s*:?\s*(.*?)(?=خدمات |الصيدلية|الإجمال[ىي]|$)'
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1) if m else ''

    for section in ['الخدمات الآخر', 'الصيدلية', 'خدمات المعمل', 'خدمات الأشعة']:
        section_text = extract_section(section)
        if not section_text:
            continue
        for line in section_text.split('\n'):
            line = line.strip()
            if not line or 'كود الخدمة' in line or 'اسم الخدمة' in line:
                continue
            m = re.search(r'([\u0600-\u06FF][\u0600-\u06FF\s]+?)\s+(\d+)\s+(\d+)\s+(\d+)', line)
            if m:
                name = m.group(1).strip()
                qty = int(m.group(2))
                price = int(m.group(3))
                services.append({
                    'section': section,
                    'name': name,
                    'quantity': qty,
                    'price': price,
                    'matched_operation': match_operation(name),
                    'matched_item': match_item(name),
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