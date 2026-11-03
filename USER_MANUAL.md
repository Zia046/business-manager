# Business Manager - User Manual (Roman Urdu)

## 1. Pehli dafa software kholna
1. Software kholein. **Registration** screen aayegi: Company Name, Address, Phone, Email, Logo, Login ID, Password likhein aur **Save & Continue** dabayen.
2. Ye information sirf aap ke computer par save hoti hai: **D:\BusinessManagerData** (agar D: drive na ho to C: mai). Poora data **encrypted** hota hai.
3. Uske baad har dafa **Login** screen aayegi. Ghalat ID ya password par "Invalid Login ID or Password" aata hai. 5 ghalat koshishon ke baad 5 minute ke liye lock ho jata hai.

> **Password kisi ko na batayen aur bhoolain nahi.** Password ke baghair data wapas nahi aa sakta.

## 2. Home screen
Upar date aur time, beech mai logo aur company ka naam, neeche 7 bade buttons:
Sale Invoice (F2) | Stock Purchase (F3) | Cash Recovery (F4) | Stock Report | Outstanding / Baqayajat | Sale Summary | Profit Loss Report.
Upar menu bar mai 6 menus hain: New Account, Sale/Purchase, Payments/Receipts, Account Transactions, Reports, Utilities.

## 3. Sab se pehle ye add karein (New Account menu)
- **Customers / Supplier:** Add New dabayen. ID computer khud banata hai. Opening Balance mai purana hisaab likhein (customer ka +ve = customer ne dene hain; supplier ka +ve = aap ne dene hain).
- **Products:** naam, category, #tags (jaise `#mobile #samsung`), sale price, opening stock, low-stock level. Mobile ke liye "Track IMEI" tick karein.
- **Company Information Edit:** naam, address, phone, logo badalna.

## 4. Sale Invoice (F2)
1. Customer: Walk-in pehle se select hai. Saved customer chunna ho to likhna shuru karein. Naya customer: **New Customer**.
2. Product search box mai naam, #tag, ID ya milta-julta spelling likhein, **Enter** dabayen ya list par double-click karein.
3. Table mai **Qty, Price, Discount** par click kar ke badal sakte hain. Stock se zyada qty par laal warning aati hai.
4. Neeche: invoice discount, **Paid now** (baqi udhaar ho jata hai, sirf saved customer ko), Grand Total.
5. **Show Profit / Loss** tick karein to is invoice ka nafa/nuqsan dikhta hai. Ye bill par print **nahi** hota.
6. **Note** mai likha hua bill ke neeche print hota hai.
7. **Save** ya **Save & Print (Ctrl+P)**. Print size: A4 ya 80mm. PDF khulta hai, wahan se printer chunein.

## 5. Stock Purchase (F3)
Supplier chunein, products add karein (ya **+ New Product**). **Purchase price har dafa khud type karni hoti hai** (khud nahi bharti). Paid now mai jo abhi diya wo likhein, baqi supplier ka udhaar ban jata hai. Save par stock khud barh jata hai.

## 6. Payments / Receipts menu
- **Cash Received from Customer** (home ka Cash Recovery): customer ka udhaar kam hota hai, receipt print hoti hai.
- **Payment to Supplier**, **Payment to Customer** (refund), **Expenses** (category, raqam, note).
- Sab cash book mai khud likha jata hai.

## 7. Returns (Sale/Purchase menu)
Customer/Supplier chunein, phir purana invoice/purchase chunein. Jitni qty wapas karni ho "Return Qty" mai likhein. Stock aur hisaab khud theek ho jata hai.

## 8. Account Transactions
**Cash Book** (date filter, opening/closing balance), **Balance Sheet**, **Vouchers** (list, print, naya banana).

## 9. Reports menu
Har report mai date filter, search, aur **Excel / CSV / Print-PDF** button hai.
Customer Transactions (customer chunein), Cash Received, Profit Loss, Invoice Wise Sale Summary, Stock Position (kam stock laal), Products Ledger (product chunein), All Customer Balance, Invoice Print, Products.
- **Invoice Print:** purana invoice chunein -> Print A4 / Print 80mm / **View-Edit** / **Cancel Invoice** (cancel par stock wapas aur hisaab theek ho jata hai).

## 10. Utilities
- **Backup:** *Backup Now* ya *USB / Other Folder*. "Automatic backup" tick ho to har dafa program band karne par khud backup banta hai.
- **Restore Backup:** backup file chunein. Restore se pehle purane data ki safety copy khud ban jati hai. Restore ke baad program band hota hai; dobara kholein aur **us waqt wala password** (jab backup bana tha) use karein.
- **Change Password / Username:** purana password chahiye.

## 11. Zaroori mashwaray
- Roz ya hafte mai backup **USB mai bhi** rakhein. Computer kharab ho jaye to D: drive ka data bhi ja sakta hai.
- Data folder (D:\BusinessManagerData) ko kabhi delete na karein.
- Naye computer par data le jane ke liye: purane computer ka backup file le jayen, naye computer par software khol kar Registration mai kuch bhi likhein, phir Utilities > Restore Backup.

---

## Naye features (update)

- **Login:** ab har dafa sirf Password poochta hai. Username yaad rehta hai ("Login with a different Login ID" se badal sakte hain).
- **Categories:** New Account > Categories mein nai category add/delete karein. Default: Mobile Phone, Accessories, Contagious, Disposable, Other.
- **Product banate waqt category zaroori hai.** Mobile Phone category mein Single ya Double IMEI chunna parta hai. Mobile ka stock sirf Stock Purchase se aata hai (IMEI ke saath).
- **IMEI qaidey:** sirf numbers, kam az kam 10 aur ziada se ziada 100 digits; double IMEI mein dono number alag hone chahiye.
- **Sale Invoice:** mobile bechte waqt IMEI dobara type karna parta hai; bill par IMEI chhapti hai. Enter dabane se window band nahi hoti.
- **Stock Purchase:** bill automatically Paid save hota hai.
- **Outstanding:** sirf customers ke baqayajat.
- **Utilities > Reset Database:** data chun kar mitayen. Wajah, current password aur 2 dafa tasdeeq zaroori. Mitane se pehle safety backup khud ban jata hai.

### Cash Recovery (naya)
Customer chunte hi uska pichle 1 mahine ka khata aur current balance khul jata hai. Nayi recovery likh kar **Save** ya **Save & Print Voucher** dabayein: balance kam ho jata hai aur khata dobara dikhta hai.

### Sale Invoice - kayi bill ek saath
Window ke upar Minimize/Maximize ke button hain. Minimize kar ke home se dobara **Sale Invoice** dabayein to naya bill khulta hai. Har bill ko khulte waqt apna number mil jata hai aur wahi number save hota hai. Agar koi bill bina save kiye band ho jaye to uska number agle naye bill ko (usi tarikh mein) mil jata hai.

### Software ka rabta
Front page par "Developed by Burhan Nexus, 03475093446, ziaullah.046@gmail.com" hamesha nazar aata hai (badla ya mitaya nahi ja sakta). Har bill/voucher par chhoti line: "To buy this software, contact: 03475093446".

## Installation aur Licence (naya)

**Install:** `BusinessManager-Setup.exe` chalayein. Wizard mein Next dabate jayein; Desktop aur Start Menu shortcut ke options pehle se tick hain. Install ke baad "Start Business Manager now" tick kar ke Finish karein. Software **Settings > Apps** mein se uninstall bhi hota hai (aap ka data D:\BusinessManagerData mehfooz rehta hai).

**Activation:** pehli dafa software "Machine Code" dikhata hai. Ye code Burhan Nexus (03475093446) ko bhejein. Wahan se aap ko Activation Key milegi; usay paste kar ke Activate dabayein. Key sirf usi computer par chalti hai.

**Owner ke liye (key banana):** `KeyGenerator.exe` (GitHub Actions ke artifact `KeyGenerator` mein) aur `license_private.key` ek hi folder mein rakhein. Customer ka Machine Code paste karein, muddat chunein, Generate dabayein, aur Key customer ko bhej dein. `license_private.key` kisi ko na dein aur 2 jagah backup rakhein; ye kho gayi to nayi keys nahi ban sakengi.

## Printer Settings (naya)
**Utilities > Printer Settings** mein:
- **Thermal printer** chunein (receipt ke liye) aur **A4 printer** chunein (invoice/voucher ke liye). "Windows default printer" chunne se bill seedha print hota hai, PDF window nahi khulti. "Ask every time" chunne se pehle jaisa PDF khulta hai.
- **Thermal paper width:** 80 mm ya 58 mm roll.
- **Sale invoice prints as:** Thermal ya A4 (Sale Invoice window mein har bill par badal bhi sakte hain).
- **Test Print** se printer jaanch lein. Printer ka driver pehle Windows mein install hona chahiye, phir **Refresh Printers** dabayein.
Agar seedha print na ho sake to bill PDF mein khul jata hai, bill zaya nahi hota.

## IMEI Search, Daily Closing, Home cards (naya)
- **Reports > IMEI Search / History:** IMEI ke 3+ digits likh kar Enter dabayein. Phone kis se kharida, kab bika, kis customer ko, kis rate par, sab nazar aata hai (warranty ya complaint ke liye).
- **Reports > Daily Closing:** har din ke bills, sale, cash in/out, kharche aur net cash. Ek din ke liye From aur To mein wohi tarikh rakhein.
- **Home page cards:** aaj ki sale, cash in hand, customers ke baqayajat, low-stock items aur stock mein phones. Ye har 20 second mein khud update hote hain.

## Qist, Repair, Labels, WhatsApp, Backup (naya)

**Installments (Qist)** - Sale/Purchase menu:
- *New Plan:* customer chunein, raqam (poora baqaya ya kisi bill ka credit), kitni qist aur pehli tarikh likhein. Neeche schedule dikhta hai.
- Customer jab bhi **Cash Recovery** mein paisay deta hai to wo khud sab se purani qist mein jama ho jate hain. Alag se kuch karna nahi.
- *View Schedule* se har qist ka haal (Paid / LATE / Pending). Qist late ho to surkh rang.
- Reports > **Qist Due List** mein sab ki baqi qistein, kitni late. Home par "Qist Overdue" card bhi hai.

**Repair Jobs** - Sale/Purchase menu: phone repair ke liye job banayein (naam, phone, model, kharabi, andaza, advance), **Print Slip** se parchi. Status: Received, In repair, Ready. **Deliver** par final charges, parts ki qeemat aur wasool hone wali raqam likhein. Advance aur payment cash book mein jate hain; delivered jobs ka munafa Profit Loss Report mein "Repair income" ke taur par aata hai. Job cancel karne par advance wapas ho jata hai.

**Barcode / Price Labels** - Reports menu: products chunein, har ke labels ki tadad likhein, A4 sticker sheet ya label printer roll (50x30 mm) chunein. Product mein "Barcode" bhar sakte hain, warna 6 digit ID barcode banta hai. Scanner se barcode scan karne par Sale Invoice mein product khud mil jata hai.

**Price List** - Reports menu: category wise rate list, Print / PDF ya Excel mein.

**WhatsApp Reminder:** Outstanding, Qist Due List, Cash Recovery aur Qist screens mein "WhatsApp Reminder" dabayein: WhatsApp khulta hai aur message pehle se likha hota hai (customer ka phone number save hona chahiye). Bas Send dabana hai. Repair jobs mein "Phone Ready" ka message bhi hai.

**Staff accounts / Audit Log / Excel import / Warranty:** Utilities > Staff Accounts (owner), Utilities > Audit Log (kisne kya badla), New Account > Import from Excel, aur product mein "Warranty" (bill par chhapti hai, IMEI Search mein bhi dikhti hai).

**Backup:** ab software chalte huye bhi har 2 ghante baad (agar data badla ho) khud backup banata hai, aur band hone par bhi. Utilities > Backup mein **Check Latest Backup** se jaanch, aur **USB drives found** se USB chun kar har backup ki copy USB mein bhi. Home par "Last Backup" card 2 din se purana ho to surkh ho jata hai.

## Dashboard (naya)
Menu bar mein sab se pehle **Dashboard** (aur **Home**) ka button hai; F5 dabane se bhi Dashboard khulta hai. Home par bhi upar "Dashboard" button hai. Agar 90 second tak koi kaam na ho (mouse/keyboard) to software khud Dashboard khula chhor deta hai (koi window khuli ho to nahi chhedta).

Dashboard mein: upar logo aur dukan ki maloomat; aaj/mahine ki sale, phones, low stock, qist, repairs, cash aur baqayajat ke cards; **Daily, Weekly, Monthly, Yearly sale ke graph**; neeche **Profit / Loss graph** (hara = munafa, surkh = nuqsan); sab se ziada bikne wali cheezein, kam stock aur qist due ki list; dayein taraf ghari aur calendar. Sab se neeche "Developed by Burhan Nexus, mobile aur email" hamesha nazar aata hai (sirf label hai, badla ya mitaya nahi ja sakta).
Staff ko cash, baqayajat, munafa aur profit graph nazar nahi aate.
