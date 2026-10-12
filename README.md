# Thai Fuel Market Dashboard + Auto-refresh Pipeline

โจทย์ธุรกิจ: ความต้องการน้ำมันสำเร็จรูปแต่ละชนิดในไทยเปลี่ยนไปอย่างไร และชนิดไหนที่กำลังหดตัวจนกระทบแผนการผลิตของโรงกลั่น

**Live dashboard:** `https://<username>.github.io/<repo-name>/powerbi/dashboard_preview.html` (แก้ `<username>/<repo-name>` เป็นของจริงหลังเปิด GitHub Pages แล้ว ดูวิธีเปิดด้านล่าง)

## โครงสร้างโปรเจค

```
thai_fuel_dashboard/
├── data/
│   ├── raw/                              ไฟล์ดิบจาก data.go.th (ไม่แตะ)
│   │   ├── dataset_11_15.csv                     EPPO: การใช้น้ำมันสำเร็จรูป (รายเดือน, แยกชนิด)
│   │   └── vw_opendata_039_e_fuel_sum_data_view.csv   DOEB: การส่งออกน้ำมันสำเร็จรูป (รายเดือน, รวม)
│   └── processed/                        ผลลัพธ์จาก pipeline (สร้างใหม่ได้ทุกครั้งที่รันสคริปต์)
│       ├── fact_fuel_monthly.csv
│       ├── fuel_market.db                SQLite, ตาราง fact_fuel_monthly
│       └── dashboard_data.json           ข้อมูลสรุปสำหรับพรีวิว dashboard
├── scripts/
│   └── clean_fuel_data.py                สคริปต์ pipeline หลัก (รันคำสั่งเดียว)
├── sql/
│   └── analysis_queries.sql              GROUP BY / JOIN / LAG() สำหรับ YoY, MoM, shrinking products
├── powerbi/
│   ├── POWERBI_GUIDE.md                  ขั้นตอนสร้าง dashboard ใน Power BI Desktop
│   ├── measures.dax                      DAX measures พร้อมวาง
│   └── dashboard_preview.html            พรีวิว 1 หน้า (ข้อมูลจริงจาก pipeline)
└── README.md
```

## วิธีรัน pipeline

```bash
python scripts/clean_fuel_data.py
```

1 คำสั่ง อ่านไฟล์ดิบ 2 ไฟล์ → ทำความสะอาด → เขียน `fact_fuel_monthly.csv` + `fuel_market.db` ใหม่ทั้งหมด (idempotent, รันซ้ำได้).

## ศัพท์ที่ใช้ซ้ำทั้งโปรเจค: YoY / MoM คืออะไร

- **MoM (Month-over-Month)**: เทียบตัวเลขเดือนนี้กับเดือนก่อนหน้าทันที เช่น ก.ค. เทียบกับ มิ.ย. ใช้ดูความผันผวนระยะสั้น
- **YoY (Year-over-Year)**: เทียบตัวเลขเดือนนี้กับเดือนเดียวกันของปีก่อน เช่น ก.ค. 2026 เทียบกับ ก.ค. 2025 ใช้ดู trend ที่ตัดผลของฤดูกาล (seasonality) ออกไป เพราะเทียบเดือนเดียวกันเป๊ะ

ทั้งสองคำนวณด้วย SQL window function `LAG()` ใน `sql/analysis_queries.sql`: `LAG(x, 1)` ย้อนกลับ 1 แถว (1 เดือน) สำหรับ MoM, `LAG(x, 12)` ย้อนกลับ 12 แถวสำหรับ YoY

## ข้อมูลที่ใช้ (ของจริงจาก data.go.th / catalog.eppo.go.th / data.doeb.go.th)

| ชุดข้อมูล | แหล่ง | ความสกปรกที่เจอจริง |
|---|---|---|
| การใช้น้ำมันสำเร็จรูป (`dataset_11_15.csv`) | สนพ. (EPPO) | เดือนเป็นชื่อเต็มภาษาอังกฤษ ("January"), ชนิดน้ำมันเป็น ALL CAPS |
| การส่งออกน้ำมันสำเร็จรูป (`vw_opendata_039...csv`) | กรมธุรกิจพลังงาน (DOEB) | ปีเป็น **พ.ศ.** (ไฟล์แรกเป็น ค.ศ.), หน่วยเป็น **พันลิตร** (ไฟล์แรกเป็นล้านลิตร), ไม่มีคอลัมน์แยกชนิดน้ำมัน (มีแต่ยอดรวม) |

`scripts/clean_fuel_data.py` แก้ทั้งสองจุดนี้แบบ programmatic (แปลง พ.ศ.→ค.ศ. ด้วย `-543`, แปลงหน่วยด้วย `/1000`, map ชื่อเดือน/ชนิดน้ำมันให้เป็นมาตรฐานเดียวกัน) แล้ว union ทั้งสองแหล่งเข้าตารางเดียว long-format: `fact_fuel_monthly(record_date, year, month, product, metric_type, quantity_million_litres, source_file)`

**หมายเหตุความถูกต้อง:** ยอดส่งออกในไฟล์ DOEB เทียบกับยอดใช้ในประเทศแล้วมีสัดส่วนต่ำกว่าที่คาดไว้มาก (~0.01 ถึง 0.02%) แม้จะแปลงหน่วยตามที่ label ในไฟล์ระบุ (`พันลิตรต่อเดือน`) แล้วก็ตาม สันนิษฐานว่าน่าจะเป็นข้อมูลเฉพาะส่วน ไม่ใช่ยอดส่งออกทั้งประเทศ ควรตรวจสอบ metadata เพิ่มก่อนใช้ตัวเลขนี้นำเสนอจริง (ระบุไว้ตรงๆ แทนการปัดตัวเลขให้ดูสมเหตุสมผล เพราะงาน cleaning ที่ดีต้องรายงานความไม่แน่นอน ไม่ใช่ซ่อนมัน)

## SQL (`sql/analysis_queries.sql`)

5 query ครอบคลุมตามที่โจทย์ต้องการ:
1. Monthly consumption by product + MoM/YoY growth (`LAG()` window function)
2. Yearly `GROUP BY` + YoY on annual totals
3. Shrinking-product detector (3+ เดือนติดต่อกันที่ YoY ติดลบ) ตอบคำถามธุรกิจตรงๆ
4. `JOIN` total consumption กับ total export รายเดือน + export share
5. KPI snapshot ของเดือนล่าสุด

ทดสอบรันจริงกับ `fuel_market.db` แล้วทุก query (ดู query 3, ผลจริง ณ ก.ค. 2026: **LPG, Jet Fuel, Diesel, Kerosene** กำลังอยู่ใน streak หดตัว).

## Power BI

ดู [`powerbi/POWERBI_GUIDE.md`](powerbi/POWERBI_GUIDE.md) สำหรับขั้นตอนตั้งแต่ Get Data ถึง layout 1 หน้า, DAX measures พร้อมวางใน [`powerbi/measures.dax`](powerbi/measures.dax), และพรีวิวหน้าตา dashboard (ข้อมูลจริง, โทนสีแบรนด์ Thaioil) ที่ [`powerbi/dashboard_preview.html`](powerbi/dashboard_preview.html).

## ตัวเลข Before / After

| ตัววัด | ก่อน (ทำมือใน Excel) | หลัง (pipeline) |
|---|---|---|
| เวลาอัปเดตรายงานเดือนใหม่ | **ให้จับเวลาเองตอนทำรอบแรกด้วยมือ** (ดาวน์โหลด 2 ไฟล์ → แปลง พ.ศ./ค.ศ. → แปลงหน่วย → รวมตาราง → รีเฟรช pivot/chart) | **วัดจริงแล้ว:** สคริปต์ประมวลผล 0.085 วินาที (เวลารัน process รวม Python startup ~1.2 วินาที) |
| จำนวนขั้นตอนที่ต้องคลิกเอง | **นับจริงตอนทำมือ** (เปิดไฟล์ 2 ไฟล์ x copy-paste x แปลงหน่วยทีละแถว x rebuild pivot) | **1 คำสั่ง:** `python scripts/clean_fuel_data.py` |
| จุดที่พลาดได้ (copy ผิดช่อง, หน่วยไม่ตรง, พ.ศ./ค.ศ. ปนกัน) | **ระบุเป็นข้อๆ จากที่เจอจริงตอนทำมือ** | **0** เพราะ logic การแปลงปีและหน่วยอยู่ในโค้ด (`clean_fuel_data.py` บรรทัด `BUDDHIST_YEAR_OFFSET`, `/1000.0`), รันซ้ำได้ผลเหมือนเดิมทุกครั้ง |

ช่อง "ก่อน" ตั้งใจเว้นให้คุณจับเวลา/นับจริงจากประสบการณ์ทำมือครั้งแรก เพื่อให้ตัวเลขที่เอาไปพูดสัมภาษณ์เป็นของจริง ไม่ใช่เดา ส่วนด้านล่างนี้คือจุดที่ "พลาดได้" จริงที่เจอระหว่างทำโปรเจคนี้ (ไว้ใช้เป็น checklist เทียบตอนจับเวลา):
1. ปี พ.ศ. vs ค.ศ. ปนกันระหว่างสองไฟล์ (เผลอรวมตรงๆ ตัวเลขปีจะเพี้ยน 543 ปี)
2. หน่วยพันลิตร vs ล้านลิตร ปนกัน (เผลอรวมตรงๆ ยอดจะเพี้ยน 1000 เท่า)
3. เดือนเป็นชื่อ ("January") ในไฟล์หนึ่ง เป็นเลข (1 ถึง 12) ในอีกไฟล์ ต้อง map เองถ้าทำมือ
4. ชนิดน้ำมันเขียน ALL CAPS ต้องมา normalize ก่อน join/group ไม่งั้น pivot จะแยกเป็นหมวดซ้ำ

## เปิด dashboard ให้คนอื่นดูผ่าน GitHub Pages

1. Push repo นี้ขึ้น GitHub ก่อน (branch `main`)
2. ไปที่ repo บน GitHub > **Settings** > เมนูซ้าย **Pages**
3. หัวข้อ "Build and deployment" > Source เลือก **Deploy from a branch**
4. Branch เลือก **main** / **/ (root)** แล้วกด **Save**
5. รอ 1 ถึง 2 นาที ตัว dashboard จะเข้าถึงได้ที่
   `https://<username>.github.io/<repo-name>/powerbi/dashboard_preview.html`
   (แทน `<username>` และ `<repo-name>` ด้วยของจริง แล้วอัปเดตลิงก์บนสุดของไฟล์นี้)
