# Thai Fuel Market Dashboard + Auto-refresh Pipeline

โจทย์ธุรกิจ: ความต้องการน้ำมันสำเร็จรูปแต่ละชนิดในไทยเปลี่ยนไปอย่างไร และชนิดไหนที่กำลังหดตัวจนกระทบแผนการผลิตของโรงกลั่น

**Live dashboard:** https://kakutacintheocean.github.io/Thai-fuel-market-dashboard/

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
│   └── analysis_queries.sql              GROUP BY / JOIN / LAG() สำหรับ YoY, MoM, shrinking products, data quality guard
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

## Data quality finding: ยอดส่งออกต่ำผิดปกติ

ระหว่างทำ query เทียบยอดส่งออก (DOEB) กับยอดใช้ในประเทศ (EPPO) พบว่าสัดส่วนส่งออกต่อการใช้ในประเทศออกมาอยู่ที่ประมาณ **0.01 ถึง 0.02%** ของทุกเดือนที่เทียบได้ ซึ่งต่ำกว่าความเป็นจริงของการส่งออกน้ำมันสำเร็จรูปไทยมาก

สิ่งที่ตรวจสอบแล้ว:
- หน่วยแปลงถูกต้องตามที่ label ในไฟล์ดิบระบุไว้ตรงๆ (`UNIT = "พันลิตรต่อเดือน"` แปลงเป็นล้านลิตรด้วยการหาร 1,000) ไม่ใช่บั๊กในโค้ด
- ปี พ.ศ.→ค.ศ. แปลงถูกต้อง (ลองสุ่มเช็คหลายแถวแล้ว ตรงกับช่วงปีที่สมเหตุสมผล)
- ตัวเลขดิบในไฟล์ (ก่อนแปลงหน่วยใดๆ) อยู่ที่หลักร้อยถึงพันกว่าต่อเดือนเท่านั้น ไม่ใช่หลักแสน/ล้านแบบที่ควรจะเป็นถ้าเป็นยอดส่งออกทั้งประเทศจริง

สิ่งที่ยังไม่รู้: dataset นี้ (`vw_opendata_039_e_fuel_sum_data_view`) อาจเป็นยอดเฉพาะกลุ่มผู้ค้าบางราย หรือเฉพาะบางหมวดสินค้า ไม่ใช่ยอดส่งออกน้ำมันสำเร็จรูปทั้งประเทศตามชื่อ dataset ที่ระบุ ยังไม่ได้ติดต่อ DOEB เพื่อยืนยัน metadata

**ผลที่ตามมา:** ตัวเลขนี้ไม่ถูกนำไปแสดงเป็น KPI บน dashboard (เอาการ์ด "สัดส่วนส่งออก/การใช้ในประเทศ" ออกแล้ว) ส่วน query ที่ JOIN สองตารางนี้ (query 4 ใน `sql/analysis_queries.sql`) ยังเก็บไว้ในไฟล์ เพราะโครงสร้างการ join ถูกต้องและพร้อมใช้งานทันทีที่ยืนยัน metadata กับ DOEB ได้ แค่ผลลัพธ์ปัจจุบันยังไม่นำไปแสดงจนกว่าจะยืนยันได้

## SQL (`sql/analysis_queries.sql`)

6 query ใน `sql/analysis_queries.sql`:
1. Monthly consumption by product + MoM/YoY growth (`LAG()` window function)
2. Yearly `GROUP BY` + YoY on annual totals
3. Shrinking-product detector (3+ เดือนติดต่อกันที่ YoY ติดลบ) ตอบคำถามธุรกิจตรงๆ
4. `JOIN` total consumption กับ total export รายเดือน (ผลลัพธ์ยังไม่ผ่านการยืนยัน ดูหัวข้อ Data quality finding ด้านบน)
5. KPI snapshot ของเดือนล่าสุด
6. Data quality guard: เช็คว่ามีชื่อผลิตภัณฑ์ที่ pipeline ไม่รู้จักหลุดเข้ามาไหม (รันแล้วได้ 0 แถว ณ วันที่เขียนนี้ แปลว่าข้อมูลตอนนี้ map ครบ)

ทดสอบรันจริงกับ `fuel_market.db` แล้วทุก query (ดู query 3, ผลจริง ณ ก.ค. 2026: **LPG, Jet Fuel, Diesel, Kerosene** กำลังอยู่ใน streak หดตัว).

## Power BI

ดู [`powerbi/POWERBI_GUIDE.md`](powerbi/POWERBI_GUIDE.md) สำหรับขั้นตอนตั้งแต่ Get Data ถึง layout 1 หน้า, DAX measures พร้อมวางใน [`powerbi/measures.dax`](powerbi/measures.dax), และพรีวิวหน้าตา dashboard (ข้อมูลจริง, โทนสีแบรนด์ Thaioil) ที่ [`powerbi/dashboard_preview.html`](powerbi/dashboard_preview.html).

## สิ่งที่ pipeline ทำให้

- **1 คำสั่ง:** `python scripts/clean_fuel_data.py` อ่านไฟล์ดิบ 2 ไฟล์ ทำความสะอาด เขียนตารางสะอาดตารางเดียวพร้อมใช้ ไม่ต้องเปิดไฟล์ 2 ไฟล์แยกกันเองแล้วรวมมือ
- **เวลา end-to-end วัดจริง:** ~1.5 วินาที นับจากไฟล์ดิบอยู่ในเครื่องแล้วจนถึงได้ตารางสะอาดพร้อมใช้ (วัดด้วย `time python scripts/clean_fuel_data.py` รวม Python startup, อ่านไฟล์, เขียน CSV + SQLite ทั้งหมด)
- **idempotent:** รันซ้ำกี่ครั้งก็ได้ผลเหมือนเดิมทุกครั้ง
- **ลดความเสี่ยง copy-paste ผิดช่องและแปลงหน่วยผิด** เพราะ logic การแปลงปีและหน่วยอยู่ในโค้ด (`clean_fuel_data.py` บรรทัด `BUDDHIST_YEAR_OFFSET`, `/1000.0`) ความเสี่ยงที่เหลืออยู่คือชื่อผลิตภัณฑ์ใหม่ที่ pipeline ยังไม่รู้จัก ซึ่งมี query 6 (data quality guard) คอยตรวจจับให้

จุดที่พลาดได้จริงที่เจอระหว่างทำโปรเจกต์นี้:
1. ปี พ.ศ. vs ค.ศ. ปนกันระหว่างสองไฟล์ (เผลอรวมตรงๆ ตัวเลขปีจะเพี้ยน 543 ปี)
2. หน่วยพันลิตร vs ล้านลิตร ปนกัน (เผลอรวมตรงๆ ยอดจะเพี้ยน 1000 เท่า)
3. เดือนเป็นชื่อ ("January") ในไฟล์หนึ่ง เป็นเลข (1 ถึง 12) ในอีกไฟล์ ต้อง map เองถ้าทำมือ
4. ชนิดน้ำมันเขียน ALL CAPS ต้องมา normalize ก่อน join/group ไม่งั้น pivot จะแยกเป็นหมวดซ้ำ
