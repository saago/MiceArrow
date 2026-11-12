# 🖱️ Mice Arrow

<p dir="rtl" align="right"><strong>יצירה, התאמה והחלפה בין פרופילי סמן ב־Windows</strong></p>

<p dir="rtl" align="right"><a href="README.md">English</a> · <a href="README.he.md">עברית</a></p>

![Windows](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-GPLv3-blue.svg)
[![תמיכה ב־Ko-fi](https://img.shields.io/badge/Support%20me-Ko--fi-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/netanelelhadad)

<p dir="rtl" align="right">
Mice Arrow היא תוכנה ל־Windows ליצירה ולניהול של פרופילי סמן ולהחלת סמנים מותאמים אישית במערכת. אפשר לעצב סמן מתמונת PNG או ICO, לשנות את הגודל והצבע, להוסיף הילה, לקבוע את נקודת הלחיצה ולעבור בין פרופילים ידנית או לפי היישום הפעיל.
</p>

<blockquote dir="rtl" align="right">
<strong>לתשומת לב:</strong> התוכנה משנה את הגדרות הסמן של Windows; היא אינה מזריקה DLL, מתקינה Hooks או מציירת שכבת־על במשחקים. יישומים ומשחקים שמציירים סמן בעצמם עשויים להתעלם מסמן Windows.
</blockquote>

<p dir="rtl" align="right">
נוצר על ידי <strong>נתנאל אלחדד</strong> · <a href="mailto:Nati3210@gmail.com">Nati3210@gmail.com</a>
</p>

<h2 dir="rtl" align="right">✨ תכונות</h2>

<ul dir="rtl" align="right">
<li>🎨 יצירה ושמירה של כמה פרופילי סמן מתמונות PNG/ICO אישיות או מתוך אוסף הסמנים המובנים בתיקיית <code dir="ltr">Pointers</code>.</li>
<li>📏 התאמת גודל הסמן (1%–800%), צבע, שמירת צבעי המקור, נקודת לחיצה והילה אופציונלית.</li>
<li>👁️ תצוגה מקדימה חיה ביחס 1:1, בלי להחיל את השינויים על Windows.</li>
<li>🌀 החלת הסמן על מצבי החץ הרגיל והעבודה ברקע של Windows. במצב עבודה ברקע הסמן המותאם מופיע לצד טבעת מונפשת.</li>
<li>⚡ קיצור מקשים גלובלי למעבר בין פרופילים, שיוך פרופילים ליישומים ומזעור למגש המערכת.</li>
<li>↩️ שחזור הגדרות הסמנים של Windows שנשמרו לפני ההחלה הראשונה.</li>
</ul>

<blockquote dir="rtl" align="right">
<strong>מגבלת גודל:</strong> הסמן, כולל ההילה, חייב להיכנס למידות 256 × 256 פיקסלים. לחצו על התצוגה המקדימה כדי לקבוע את נקודת הלחיצה; זיהוי השפיץ האוטומטי מתעלם משוליים שקופים.
</blockquote>

<h2 dir="rtl" align="right">🚀 הפעלה ב־Windows</h2>

<p dir="rtl" align="right">
אפשר להוריד קובץ הפעלה עצמאי מעמוד GitHub Releases של הפרויקט, אם פורסם בו. לחלופין, אפשר לבנות אותו מקוד המקור לפי ההוראות בהמשך.
</p>

<p dir="rtl" align="right">
להפעלה מקוד המקור, התקינו Python 3.10 ומעלה והפעילו PowerShell בתיקיית הפרויקט:
</p>

```powershell
python -m pip install -r requirements.txt
python mice_arrow.py
```

<h2 dir="rtl" align="right">🧭 שימוש בסיסי</h2>

<ol dir="rtl" align="right">
<li>בחרו <strong>פרופיל חדש</strong> והזינו שם.</li>
<li>בחרו קובץ PNG/ICO, או בחרו תמונה דרך <strong>סמנים מוכנים</strong>.</li>
<li>התאימו את הגודל, הצבע וההילה. סמנו <strong>שמור על הצבעים המקוריים</strong> כדי לשמר את צבעי התמונה.</li>
<li>לחצו על הסמן בתצוגה המקדימה כדי לקבוע את נקודת הלחיצה, או השתמשו בזיהוי האוטומטי של השפיץ.</li>
<li>שמרו את הפרופיל ולחצו על <strong>החלת הסמן במערכת</strong>. בהחלה הראשונה תוצג בקשת אישור והגדרות הסמן הקודמות של Windows יישמרו.</li>
<li>לחצו על <strong>שחזור הסמנים המקוריים</strong> בכל עת כדי לשחזר את ההגדרות שנשמרו.</li>
</ol>

<p dir="rtl" align="right">
בחירת פרופיל שמור מחילה אותו אוטומטית. הפרופיל נשאר מוחל גם לאחר סגירת התוכנה והפעלה מחדש של Windows. לאחר כניסה מחדש ל־Windows או טעינה מחדש של ערכת הסמנים, Windows עשוי לשנות את גודל הסמנים; במקרה כזה יש להחיל את הפרופיל שוב. בדרך כלל אין צורך בהרשאות מנהל.
</p>

<p dir="rtl" align="right">
⌨️ <strong>קיצורי מקשים:</strong> <code dir="ltr">Ctrl+S</code> שומר את הפרופיל הנוכחי · <code dir="ltr">Ctrl+N</code> יוצר פרופיל חדש.
</p>

<h2 dir="rtl" align="right">⚙️ אוטומציה ומגש המערכת</h2>

<p dir="rtl" align="right">פתחו את <strong>אוטומציה והגדרות</strong> כדי להגדיר:</p>

<ul dir="rtl" align="right">
<li>⌨️ <strong>קיצור גלובלי למעבר בין פרופילים:</strong> ברירת המחדל היא <code dir="ltr">Ctrl+Alt+F8</code>; אפשר לבחור גם <code dir="ltr">Ctrl+Shift+F8</code>, <code dir="ltr">Ctrl+Alt+Right</code> או ללא קיצור.</li>
<li>🪟 <strong>פרופיל לכל יישום:</strong> שייכו פרופיל שמור לנתיב המלא של קובץ <code dir="ltr">.exe</code> של יישום. יש להחיל פרופיל ידני פעם אחת לפני הפעלת ההחלפה האוטומטית. יישומים ללא שיוך משתמשים בפרופיל הידני האחרון.</li>
<li>📥 <strong>מגש המערכת:</strong> מזערו את החלון למגש ולחצו לחיצה כפולה על הסמל כדי לפתוח אותו מחדש. בתפריט המגש ניתן לעבור לפרופיל הבא, להשהות את האוטומציה, לשחזר סמנים או לצאת. כברירת מחדל, סגירת החלון יוצאת מהתוכנה; אפשר להגדיר שהיא תמזער למגש במקום זאת.</li>
</ul>

<p dir="rtl" align="right">
האוטומציה וקיצורי המקשים פעילים רק כשהתוכנה פתוחה, גם כשהיא ממוזערת למגש. יציאה מהתוכנה אינה משחזרת את הסמנים אוטומטית. הפעלה אוטומטית עם Windows אינה כלולה.
</p>

<h2 dir="rtl" align="right">📦 בנייה מקוד המקור</h2>

```powershell
python -m pip install -r requirements-build.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

<p dir="rtl" align="right">
קובץ ההפעלה העצמאי ייווצר ב־<code dir="ltr">dist\MiceArrow.exe</code>. אוסף הסמנים המובנה <code dir="ltr">Pointers</code> נארז בתוך קובץ ההפעלה; אין צורך ב־Python במחשב שבו מפעילים אותו.
</p>

<h2 dir="rtl" align="right">🗂️ נתונים ובדיקות</h2>

<p dir="rtl" align="right">נתוני המשתמש נשמרים בתיקייה <code dir="ltr">%APPDATA%\MiceArrow</code>:</p>

<table dir="rtl" align="right">
<thead><tr><th align="right">קובץ</th><th align="right">תוכן</th></tr></thead>
<tbody>
<tr><td><code dir="ltr">profiles.json</code></td><td>פרופילי הסמנים השמורים</td></tr>
<tr><td><code dir="ltr">settings.json</code></td><td>הגדרות האוטומציה, שיוכי היישומים והפרופיל הידני האחרון</td></tr>
<tr><td><code dir="ltr">active.cur</code>, <code dir="ltr">working.ani</code>, <code dir="ltr">cursor_backup.json</code></td><td>סמנים שהוחלו וגיבוי הסמנים המקורי</td></tr>
</tbody>
</table>

<div dir="rtl" align="right">
<p>להפעלת הבדיקות מתיקיית הפרויקט:</p>
</div>

```powershell
python -m unittest discover -s tests
```
