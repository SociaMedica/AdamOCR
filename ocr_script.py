"""
AdamOCR — استخراج نصوص وحقول وخدمات من فواتير طبية PDF
- PyMuPDF لاستخراج النص + تحويل لصور (scanned)
- Tesseract OCR (عربي + إنجليزي)
- regex لاستخراج الحقول والخدمات
- fuzzy match أسماء الخدمات مع seedOperations
- JSON output
"""
import os
import re
import json
import shutil
import platform
from difflib import SequenceMatcher


def _setup_tesseract():
    try:
        import pytesseract
        if shutil.which('tesseract'):
            print(f'  tesseract in PATH: {shutil.which("tesseract")}')
            return
        if platform.system() == 'Windows':
            candidates = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                os.path.expanduser(r'~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'),
            ]
            for c in candidates:
                if os.path.exists(c):
                    pytesseract.pytesseract.tesseract_cmd = c
                    print(f'  tesseract: {c}')
                    user_tessdata = os.path.expanduser(r'~\tessdata')
                    if os.path.exists(os.path.join(user_tessdata, 'ara.traineddata')):
                        os.environ['TESSDATA_PREFIX'] = user_tessdata
                    return
        else:
            print('  Linux: system tesseract')
    except Exception as e:
        print(f'  tesseract setup error: {e}')


_setup_tesseract()

INPUT_DIR = 'input_pdfs'
OUTPUT_DIR = 'results'

# قائمة العمليات من seed_data.dart (لازم تتزامن مع التطبيق)
SEED_OPERATIONS = [
    {'code': 'UHIA-0209', 'name': 'استخدام المثبت الخارجي في الكسور المفتتة', 'price': 27775},
    {'code': 'UHIA-0259', 'name': 'استخراج شرائح صغرى ومسامير من الاطراف', 'price': 20910},
    {'code': 'UHIA-0068', 'name': 'استكشاف البطن', 'price': 10210},
    {'code': 'UHIA-3281', 'name': 'استكشاف الشرايين بالأطراف السفلية', 'price': 24980},
    {'code': 'UHIA-0086', 'name': 'استئصال البواسير', 'price': 7030},
    {'code': 'UHIA-0084', 'name': 'استئصال الزائدة الدودية (اجراء مفتوح)', 'price': 7955},
    {'code': 'UHIA-0691', 'name': 'استئصال اللوزتين', 'price': 5070},
    {'code': 'UHIA-0119', 'name': 'استئصال جذري للغدة الدرقية', 'price': 28225},
    {'code': 'UHIA-0678', 'name': 'استئصال جزئي لقرينات الانف باستخدام المناظير', 'price': 10965},
    {'code': 'UHIA-0038', 'name': 'استئصال جزئي للقولون مع اعادة التوصيل', 'price': 27060},
    {'code': 'UHIA-0306', 'name': 'استئصال حمل خارج الرحم', 'price': 14580},
    {'code': 'UHIA-0110', 'name': 'استئصال ظفر غائر باللحم', 'price': 4585},
    {'code': 'UHIA-3529', 'name': 'استئصال فتق اربي (جانب واحد)', 'price': 9030},
    {'code': 'UHIA-2205', 'name': 'استئصال قناة درقية لسانية', 'price': 9230},
    {'code': 'UHIA-0285', 'name': 'استئصال كلي للرحم', 'price': 19510},
    {'code': 'UHIA-0285-1', 'name': 'استئصال كلي للرحم والمبيضين', 'price': 18980},
    {'code': 'UHIA-2244', 'name': 'استئصال كيس بالمبيض', 'price': 10395},
    {'code': 'UHIA-0319', 'name': 'استئصال كيس بغدة بارثولين', 'price': 5190},
    {'code': 'UHIA-3008', 'name': 'استئصال لحمية خلف الانف بالمنظار', 'price': 13950},
    {'code': 'UHIA-0139', 'name': 'استئصال للورم بالثدي', 'price': 12630},
    {'code': 'UHIA-0685', 'name': 'استئصال ناسور امام الاذن', 'price': 16810},
    {'code': 'UHIA-0092', 'name': 'استئصال ناسور عصعصي', 'price': 7800},
    {'code': 'UHIA-0658', 'name': 'استئصال ورم دموي بالبلعوم الأنفي أو الانف باستخدام المنظار ذو الالياف الضوئية', 'price': 75010},
    {'code': 'UHIA-0304', 'name': 'استئصال ورم ليفي رحمي من البطن', 'price': 14070},
    {'code': 'UHIA-2611', 'name': 'استئصال ورم نسيجي حميد', 'price': 15440},
    {'code': 'UHIA-3369', 'name': 'أشعة تداخلية - أخذ عينة بإبرة رفيعة تحت الموجات الصوتية', 'price': 10130},
    {'code': 'UHIA-3481', 'name': 'أشعة تداخلية - تركيب قسطرة غسيل كلى مؤقتة ماهوكر', 'price': 11570},
    {'code': 'UHIA-3387', 'name': 'أشعة تداخلية - حقن عصب تحت الموجات الصوتية', 'price': 6525},
    {'code': 'UHIA-0088', 'name': 'اصلاح فتق اربي', 'price': 7390},
    {'code': 'UHIA-0501', 'name': 'أكياس دهنية متعددة', 'price': 3390},
    {'code': 'UHIA-0106', 'name': 'الفتحات الخارجية للخراريج السطحية الكبري', 'price': 5445},
    {'code': 'UHIA-0700', 'name': 'المناظير التشخيصية للأنف والبلعوم والحنجرة تحت تخدير موضعي', 'price': 5270},
    {'code': 'UHIA-0323', 'name': 'الولادة الطبيعية (بشق العجان أو بدون)', 'price': 6300},
    {'code': 'UHIA-0696', 'name': 'ايقاف نزيف بعد استئصال اللوزتين', 'price': 45905},
    {'code': 'UHIA-0280', 'name': 'بتر عقلة بأصبع القدم', 'price': 11730},
    {'code': 'UHIA-2760', 'name': 'تثبيت داخلي لكسور مفتتة صعبة', 'price': 32460},
    {'code': 'UHIA-0677', 'name': 'تركيب انابيب تهوية للاذن بالميكروسكوب', 'price': 11970},
    {'code': 'UHIA-2753', 'name': 'تركيب مسمار نخاعي تشابكي لتثبيت كسر أعلى الفخذ', 'price': 27025},
    {'code': 'UHIA-3275', 'name': 'تسليك وصلة شريانيه وريدية طبيعية أو صناعيه للغسيل الكلوي', 'price': 28930},
    {'code': 'UHIA-0310', 'name': 'تصليح سقوط بالمهبل أمامي', 'price': 11210},
    {'code': 'UHIA-0058', 'name': 'تصليح فتق مع تركيب شبكة', 'price': 13000},
    {'code': 'UHIA-0694', 'name': 'تصليح وتثبيت كسر بعظام الانف', 'price': 10010},
    {'code': 'UHIA-0680', 'name': 'تقويم الحاجز الأنفي بالمنظار', 'price': 16310},
    {'code': 'UHIA-2751', 'name': 'تنظيف جرح قريب من العظام', 'price': 18645},
    {'code': 'UHIA-0100', 'name': 'تنظيف قدم سكري', 'price': 6015},
    {'code': 'UHIA-3078', 'name': 'تنظيف لجرح ملتهب', 'price': 8250},
    {'code': 'UHIA-3328', 'name': 'توسيع شرايين طرفيه باستخدام القسطرة و عدد 2 بالونه العادية', 'price': 53180},
    {'code': 'UHIA-0404', 'name': 'توصيل شريان بوريد للغسيل الكلوي', 'price': 15630},
    {'code': 'UHIA-0261', 'name': 'رفع اسلاك معدنية أومسامير', 'price': 15820},
    {'code': 'UHIA-2802', 'name': 'رفع قسطرة وريدية مستديمة للغسيل الكلوي', 'price': 9590},
    {'code': 'UHIA-0660', 'name': 'زرع القوقعة', 'price': 49455},
    {'code': 'UHIA-0091', 'name': 'شرخ شرجي', 'price': 6400},
    {'code': 'UHIA-0108', 'name': 'طهارة الأطفال', 'price': 4105},
    {'code': 'UHIA-0322', 'name': 'عملية ربط عنق الرحم من المهبل للإجهاض المتكرر', 'price': 5530},
    {'code': 'UHIA-2500', 'name': 'فتح خراج بجوار الالية', 'price': 6150},
    {'code': 'UHIA-2501', 'name': 'فتح خراج بجوار الثدي', 'price': 6150},
    {'code': 'UHIA-2502', 'name': 'فتح خراج بجوار الشرج', 'price': 6150},
    {'code': 'UHIA-0318', 'name': 'كحت وتنظيف للرحم', 'price': 5820},
    {'code': 'UHIA-3290', 'name': 'كي الوريد الصافي باستخدام قسطرة الليزر أو التردد الحرارى', 'price': 40205},
    {'code': 'UHIA-0684', 'name': 'كي نزيف بالأنف باستخدام المنظار ذو الالياف الضوئية', 'price': 19700},
    {'code': 'UHIA-3044', 'name': 'منظار جراحي تشخيصي على الحنجرة مع استئصال', 'price': 9780},
    {'code': 'UHIA-0301', 'name': 'ولادة قيصرية لأول مرة', 'price': 10760},
    {'code': 'UHIA-0293', 'name': 'ولادة قيصرية متكررة', 'price': 15720},
]


def _normalize_arabic(text):
    """تطبيع بسيط للنص العربي للمقارنة."""
    if not text:
        return ''
    text = re.sub(r'[\u064B-\u0652]', '', text)  # حركات
    text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    text = text.replace('ة', 'ه').replace('ى', 'ي')
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()


def fuzzy_match_operation(name_from_pdf):
    """إرجاع أفضل تطابق من SEED_OPERATIONS لو التشابه > 0.5."""
    if not name_from_pdf:
        return None
    norm_pdf = _normalize_arabic(name_from_pdf)
    best = None
    best_ratio = 0.0
    for op in SEED_OPERATIONS:
        norm_op = _normalize_arabic(op['name'])
        ratio = SequenceMatcher(None, norm_pdf, norm_op).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = op
    if best and best_ratio >= 0.5:
        return {'matched_code': best['code'], 'matched_name': best['name'], 'similarity': round(best_ratio, 2)}
    return None


def extract_text_pymupdf(pdf_path):
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        text = ''.join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception as e:
        print(f'  PyMuPDF text extraction error: {e}')
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


def extract_header_fields(text):
    fields = {
        'patient_name': None, 'national_id': None, 'doctor_name': None,
        'specialty': None, 'admission_date': None, 'discharge_date': None,
        'diagnosis': None, 'hospital_name': None, 'referral_number': None,
        'total_amount': None,
    }
    # طبيب: الاسم الإنجليزي بعد "إسم الطبيب:"
    m = re.search(r'([A-Z][a-zA-Z\s]+?)\s+إسم الطبيب', text)
    if m:
        fields['doctor_name'] = m.group(1).strip()
    else:
        m = re.search(r'إسم الطبيب\s*:?\s*([A-Za-z][a-zA-Z\s]+)', text)
        if m:
            fields['doctor_name'] = m.group(1).strip()

    # المريض
    m = re.search(r'إسم المريض\s*:?\s*([^\n]+)', text)
    if m:
        fields['patient_name'] = m.group(1).strip()

    # الرقم القومي
    m = re.search(r'الرقم القومي\s*:?\s*(\d{10,14})', text)
    if m:
        fields['national_id'] = m.group(1)

    # التخصص
    m = re.search(r'التخصص\s*:?\s*([^\n]+)', text)
    if m:
        fields['specialty'] = m.group(1).strip()

    # التواريخ (الوقت قبل التاريخ حسب OCR)
    m = re.search(r'وقت الدخول\s*:?\s*(\d{1,2}:\d{2}:\d{2})?\s*(\d{1,2}/\d{1,2}/\d{4})', text)
    if m:
        fields['admission_date'] = m.group(2)
    m = re.search(r'وقت الخروج\s*:?\s*(\d{1,2}:\d{2}:\d{2})?\s*(\d{1,2}/\d{1,2}/\d{4})', text)
    if m:
        fields['discharge_date'] = m.group(2)

    # المنشأة (الاسم الإنجليزي قبل "إسم المنشأه")
    m = re.search(r'([A-Z][a-zA-Z\s]+?)\s+إسم المنشأ', text)
    if m:
        fields['hospital_name'] = m.group(1).strip()
    else:
        m = re.search(r'إسم المنشأه?\s*:?\s*([A-Za-z][a-zA-Z\s]+)', text)
        if m:
            fields['hospital_name'] = m.group(1).strip()

    # الإحالة
    m = re.search(r'رقم الإحالة\s*:?\s*([A-Z0-9]{8,})', text)
    if m:
        fields['referral_number'] = m.group(1)

    # التشخيص
    m = re.search(r'Primary\s*-\s*([A-Z0-9]+\s*-\s*[A-Z0-9]+[^\n]+?)(?:\s+Secondary|$)', text)
    if m:
        fields['diagnosis'] = m.group(1).strip()

    # الإجمالي (آخر "الإجمالى" في النص)
    matches = re.findall(r'الإجمال[ىي]\s+([\d.]+)', text)
    if matches:
        try:
            fields['total_amount'] = float(max(matches, key=lambda x: float(x)))
        except Exception:
            pass

    return fields


def extract_services(text):
    """
    استخراج الخدمات من قسم "الخدمات الأخرى" + "الصيدلية" + "المعمل" + "الأشعة"
    نمط: كود اسم كمية سعر [أرقام]
    """
    services = []

    # اقتطاع الأقسام
    def extract_section(section_name):
        pattern = rf'{section_name}\s*:?\s*(.*?)(?=خدمات |الصيدلية|الإجمال[ىي]|$)'
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1) if m else ''

    for section in ['الخدمات الآخر', 'الصيدلية', 'خدمات المعمل', 'خدمات الأشعة']:
        section_text = extract_section(section)
        if not section_text:
            continue
        # كل سطر فيه 3 أرقام على الأقل (كمية، سعر، ...)
        lines = section_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or 'كود الخدمة' in line or 'اسم الخدمة' in line:
                continue
            # البحث عن نمط: نص عربي + أرقام
            m = re.search(r'([\u0600-\u06FF][\u0600-\u06FF\s]+?)\s+(\d+)\s+(\d+)\s+(\d+)', line)
            if m:
                name = m.group(1).strip()
                qty = int(m.group(2))
                price = int(m.group(3))
                services.append({
                    'section': section,
                    'raw_line': line,
                    'name': name,
                    'quantity': qty,
                    'price': price,
                    'matched_operation': fuzzy_match_operation(name),
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