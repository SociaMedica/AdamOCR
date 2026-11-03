"""
AdamOCR — استخراج نصوص وحقول من فواتير طبية PDF
- يدعم PDF نصي (PyMuPDF) و PDF ممسوح (OCR عبر Tesseract)
- يستخرج حقول الرأس (مريض/طبيب/تاريخ/إجمالي) بـ regex
- يحفظ كل PDF كـ JSON منفصل في results/
"""
import os
import re
import json

INPUT_DIR = 'input_pdfs'
OUTPUT_DIR = 'results'


def extract_text_pymupdf(pdf_path):
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        text = ''.join(page.get_text() for page in doc)
        doc.close()
        return text
    except ImportError:
        print('  PyMuPDF not installed')
        return ''
    except Exception as e:
        print(f'  PyMuPDF error: {e}')
        return ''


def extract_text_ocr(pdf_path):
    try:
        from pdf2image import convert_from_path
        import pytesseract
        images = convert_from_path(pdf_path, dpi=300)
        text = ''
        for img in images:
            text += pytesseract.image_to_string(img, lang='ara+eng')
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


def extract_header_fields(text):
    fields = {
        'patient_name': None,
        'national_id': None,
        'doctor_name': None,
        'specialty': None,
        'admission_date': None,
        'discharge_date': None,
        'diagnosis': None,
        'hospital_name': None,
        'referral_number': None,
        'total_amount': None,
    }

    patterns = {
        'patient_name':   r'إسم المريض\s*:?\s*([^\n]+)',
        'national_id':    r'الرقم القومي\s*:?\s*(\d{10,14})',
        'doctor_name':    r'إسم الطبي\s*:?\s*([^\n]+)',
        'specialty':      r'التخصص\s*:?\s*([^\n]+)',
        'admission_date': r'تاريخ\s*/\s*وقت الدخول\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})',
        'discharge_date': r'تاريخ\s*/\s*وقت الخروج\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})',
        'hospital_name':  r'إسم المنشأ\s*:?\s*([^\n]+)',
        'referral_number': r'رقم الإحالة\s*:?\s*([A-Z0-9]+)',
        'total_amount':   r'الاجمالي\s*:?\s*([\d.,]+)',
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if m:
            fields[key] = m.group(1).strip()

    # التشخيص
    m = re.search(r'Primary\s*-\s*([^\n]+?)(?:\s+Secondary|$)', text)
    if m:
        fields['diagnosis'] = m.group(1).strip()

    # تحويل المبلغ لرقم
    if fields['total_amount']:
        try:
            fields['total_amount'] = float(fields['total_amount'].replace(',', ''))
        except Exception:
            fields['total_amount'] = None

    return fields


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

    result = {
        'filename': filename,
        'used_ocr': used_ocr,
        'text_length': len(text),
        'fields': fields,
        'raw_text': text,
    }

    output_name = os.path.splitext(filename)[0] + '.json'
    output_path = os.path.join(OUTPUT_DIR, output_name)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'  Saved: {output_path} ({len(text)} chars, OCR={used_ocr})')
    return result


def main():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    pdfs = []
    if os.path.exists(INPUT_DIR):
        pdfs = sorted(f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.pdf'))

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