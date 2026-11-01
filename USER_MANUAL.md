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
