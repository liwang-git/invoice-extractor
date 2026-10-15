import json, os
from decimal import Decimal as D

CATEGORIES = ["Software & SaaS", "Professional Services", "Office Supplies",
              "Travel", "Facilities & Utilities", "Telecom"]

cases = []

def case(cid, text, vendor, number, date, items, tax, total, category,
         needs_review=False, reason=None):
    cases.append((cid, text.strip() + "\n", {
        "vendor": vendor,
        "invoice_number": number,
        "invoice_date": date,
        "line_items": [{"description": d, "amount": float(a)} for d, a in items],
        "tax": float(tax),
        "total": None if total is None else float(total),
        "category": category,
        "needs_review": needs_review,
        "review_reason": reason,
    }))

case("inv_001", """
NORTHWIND CLOUD HOSTING
1200 Harbor Way, Suite 400, Seattle WA 98101

INVOICE
Invoice #: NCH-20931
Invoice Date: 2026-09-01
Bill To: Li Wang, Austin TX

Description                         Amount
Compute plan - Standard (Sep)       $420.00
Block storage 500 GB                 $85.50
Priority support                    $120.00

TOTAL DUE                           $625.50
Payment terms: Net 30
""", "Northwind Cloud Hosting", "NCH-20931", "2026-09-01",
    [("Compute plan - Standard (Sep)", D("420.00")),
     ("Block storage 500 GB", D("85.50")),
     ("Priority support", D("120.00"))],
    D("0"), D("625.50"), "Software & SaaS")

case("inv_002", """
Brightline Legal LLP
Attorneys at Law | 88 Congress Ave, Austin, TX 78701

Statement for Services Rendered
Invoice No. BL-4417
Date: September 4, 2026

Legal review - vendor contract (4.5 hrs @ $350/hr) .......... 1,575.00
Filing fees ................................................... 125.00

Amount Due: USD 1,700.00
Please remit within 15 days.
""", "Brightline Legal LLP", "BL-4417", "2026-09-04",
    [("Legal review - vendor contract (4.5 hrs @ $350/hr)", D("1575.00")),
     ("Filing fees", D("125.00"))],
    D("0"), D("1700.00"), "Professional Services")

case("inv_003", """
Paper Trail Office Co.
Order Invoice  #PT-77812
Invoice date: 09/08/2026

Qty  Item                          Line total
10   Printer paper, letter (ream)      64.90
2    Toner cartridge, black           189.98
1    Gel pens, 24-pack                 18.50

Subtotal                              273.38
Sales tax (8.25%)                      22.55
Total                                 295.93
""", "Paper Trail Office Co.", "PT-77812", "2026-09-08",
    [("Printer paper, letter (ream)", D("64.90")),
     ("Toner cartridge, black", D("189.98")),
     ("Gel pens, 24-pack", D("18.50"))],
    D("22.55"), D("295.93"), "Office Supplies")

case("inv_004", """
LONE STAR REGIONAL AIR - Receipt / Invoice
Record locator: K7QF2M      Invoice: LSR-0098834
Issued: Sep 10, 2026
Passenger: WANG/LI

AUS-DEN round trip, economy        $412.40
Same-day change fee                 $75.00

Total charged                      $487.40
""", "Lone Star Regional Air", "LSR-0098834", "2026-09-10",
    [("AUS-DEN round trip, economy", D("412.40")),
     ("Same-day change fee", D("75.00"))],
    D("0"), D("487.40"), "Travel")

case("inv_005", """
Capitol Coworking
Membership Invoice
Invoice: CC-2026-0915
Date of issue: 2026-09-15

- Dedicated desk membership (October)   450.00
- Meeting room, 3 hrs @ 40.00            120.00

Balance due: $570.00
""", "Capitol Coworking", "CC-2026-0915", "2026-09-15",
    [("Dedicated desk membership (October)", D("450.00")),
     ("Meeting room, 3 hrs @ 40.00", D("120.00"))],
    D("0"), D("570.00"), "Facilities & Utilities")

case("inv_006", """
MESA WIRELESS - Business Account Statement
Account: 3381-2290      Bill #: MW-551903
Statement date: 15-Sep-2026

Business plan, 4 lines              240.00
Device installment (12 of 36)        33.33
Regulatory & admin fees              12.67
                                   -------
Subtotal                            286.00
Taxes & surcharges                   23.60
TOTAL AMOUNT DUE                    309.60
""", "Mesa Wireless", "MW-551903", "2026-09-15",
    [("Business plan, 4 lines", D("240.00")),
     ("Device installment (12 of 36)", D("33.33")),
     ("Regulatory & admin fees", D("12.67"))],
    D("23.60"), D("309.60"), "Telecom")

case("inv_007", """
Granite Data Consulting LLC
INVOICE GDC-1042          Date: 2026-09-18

Engagement: Data pipeline assessment

1. Assessment - fixed fee                       6,000.00
2. Reimbursable travel expenses (see attached)    842.17

Total (USD)                                     6,842.17
""", "Granite Data Consulting LLC", "GDC-1042", "2026-09-18",
    [("Assessment - fixed fee", D("6000.00")),
     ("Reimbursable travel expenses (see attached)", D("842.17"))],
    D("0"), D("6842.17"), "Professional Services")

# --- Messy cases ---

case("inv_008", """
Pixelworks Design Studio
hello@pixelworks.example

Invoice PWD-318
Date: 2026-09-22

Logo refresh - concepts and final files     $1,200.00
Two rounds of revisions                       $300.00

Thanks for your business!
""", "Pixelworks Design Studio", "PWD-318", "2026-09-22",
    [("Logo refresh - concepts and final files", D("1200.00")),
     ("Two rounds of revisions", D("300.00"))],
    D("0"), None, "Professional Services",
    needs_review=True, reason="missing_total")

case("inv_009", """
TRAILHEAD SAAS INC.
Invoice TH-88120
Dated: Sept. 24th '26

Annual license, 5 seats @ $180/seat      $900.00
Onboarding & setup                       $250.00

Total: $1,150.00
""", "Trailhead SaaS Inc.", "TH-88120", "2026-09-24",
    [("Annual license, 5 seats @ $180/seat", D("900.00")),
     ("Onboarding & setup", D("250.00"))],
    D("0"), D("1150.00"), "Software & SaaS")

case("inv_010", """
Cedar Park Janitorial Services
Invoice CPJ-7764     Invoice date: 2026-09-30

Weekly office cleaning, 4 visits @ $275     1,100.00
Cleaning supplies                              85.00

TOTAL DUE                                   1,285.00
""", "Cedar Park Janitorial Services", "CPJ-7764", "2026-09-30",
    [("Weekly office cleaning, 4 visits @ $275", D("1100.00")),
     ("Cleaning supplies", D("85.00"))],
    D("0"), D("1285.00"), "Facilities & Utilities",
    needs_review=True, reason="total_mismatch")

out = "evals/cases"
for cid, text, exp in cases:
    d = os.path.join(out, cid)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "invoice.txt"), "w").write(text)
    json.dump(exp, open(os.path.join(d, "expected.json"), "w"), indent=2)
    open(os.path.join(d, "expected.json"), "a").write("\n")

# Self-check: expected flags must match the arithmetic
for cid, text, exp in cases:
    assert exp["category"] in CATEGORIES, cid
    s = sum(D(str(li["amount"])) for li in exp["line_items"]) + D(str(exp["tax"]))
    if exp["total"] is None:
        assert exp["review_reason"] == "missing_total", cid
    elif s != D(str(exp["total"])):
        assert exp["review_reason"] == "total_mismatch", (cid, s, exp["total"])
    else:
        assert not exp["needs_review"], cid
print(f"{len(cases)} cases written and checked")