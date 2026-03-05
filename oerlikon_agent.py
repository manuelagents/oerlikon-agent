#!/usr/bin/env python3
"""
Oerlikon Competitor Intelligence Agent
Benötigt: pip install feedparser
"""

import feedparser
import smtplib
import json
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
# KONFIGURATION (via GitHub Secrets gesetzt)
# ─────────────────────────────────────────────
EMAIL_ABSENDER    = os.environ["EMAIL_ABSENDER"]
EMAIL_PASSWORT    = os.environ["EMAIL_PASSWORT"]
EMAIL_EMPFAENGER  = os.environ["EMAIL_EMPFAENGER"]
SEEN_FILE         = "seen_items.json"
STUNDEN_LOOKBACK  = 48

# ─────────────────────────────────────────────
# COMPETITORS
# ─────────────────────────────────────────────
COMPETITORS = [
    {
        "name": "Bodycote",
        "info": "🇬🇧 UK | BOY:LSE",
        "feeds": [
            "https://news.google.com/rss/search?q=Bodycote&hl=de&gl=DE&ceid=DE:de",
            "https://news.google.com/rss/search?q=Bodycote+earnings+OR+acquisition&hl=en&gl=US&ceid=US:en",
        ],
    },
    {
        "name": "Kennametal",
        "info": "🇺🇸 USA | KMT:NYSE",
        "feeds": [
            "https://news.google.com/rss/search?q=Kennametal&hl=de&gl=DE&ceid=DE:de",
            "https://news.google.com/rss/search?q=Kennametal+earnings+OR+CEO+OR+acquisition&hl=en&gl=US&ceid=US:en",
        ],
    },
    {
        "name": "Morgan Advanced Materials",
        "info": "🇬🇧 UK | MGAM:LSE",
        "feeds": [
            "https://news.google.com/rss/search?q=%22Morgan+Advanced+Materials%22&hl=en&gl=US&ceid=US:en",
        ],
    },
    {
        "name": "Ionbond",
        "info": "🇨🇭 CH / 🇯🇵 JP | IHI Group",
        "feeds": [
            "https://news.google.com/rss/search?q=Ionbond+coating&hl=de&gl=DE&ceid=DE:de",
        ],
    },
    {
        "name": "CemeCon AG",
        "info": "🇩🇪 DE | Privat",
        "feeds": [
            "https://news.google.com/rss/search?q=CemeCon+coating&hl=de&gl=DE&ceid=DE:de",
        ],
    },
    {
        "name": "Platit AG",
        "info": "🇨🇭 CH | Privat",
        "feeds": [
            "https://news.google.com/rss/search?q=Platit+PVD&hl=de&gl=DE&ceid=DE:de",
        ],
    },
]

# ─────────────────────────────────────────────
# EVENT-ERKENNUNG
# ─────────────────────────────────────────────
EVENT_TYPEN = {
    "🔴 M&A / Übernahme":  ["acquisition","acquires","merger","Übernahme","übernimmt","takeover","buys"],
    "🟡 Neues Produkt":    ["launch","launches","new product","Innovation","Neuheit","introduces","product launch"],
    "🔵 Finanzergebnisse": ["results","earnings","revenue","profit","Quartal","Ergebnis","Umsatz","annual report"],
    "🟠 Führungswechsel":  ["CEO","CFO","COO","CTO","appoints","resigns","appointment","Vorstand","Geschäftsführer"],
    "🟢 Partnerschaft":    ["partnership","agreement","collaboration","joint venture","Kooperation","Vereinbarung"],
    "⚪ Pressemitteilung": ["press release","announces","Pressemitteilung","gibt bekannt","announcement"],
}

def erkenne_event(title, summary=""):
    text = (title + " " + summary).lower()
    for typ, keywords in EVENT_TYPEN.items():
        if any(k.lower() in text for k in keywords):
            return typ
    return "📰 Allgemeine News"

# ─────────────────────────────────────────────
# FEEDS PRÜFEN
# ─────────────────────────────────────────────
def lade_gesehen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return json.load(f)
    return {}

def speichere_gesehen(data):
    with open(SEEN_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def pruefe_feeds():
    gesehen = lade_gesehen()
    neue_events = []
    grenze = datetime.utcnow() - timedelta(hours=STUNDEN_LOOKBACK)

    for comp in COMPETITORS:
        for url in comp["feeds"]:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:15]:
                    uid = entry.get("id") or entry.get("link", "")
                    if not uid or uid in gesehen:
                        continue

                    pub = entry.get("published_parsed")
                    if pub:
                        pub_dt = datetime(pub[0], pub[1], pub[2], pub[3], pub[4], pub[5])
                        if pub_dt < grenze:
                            continue

                    title   = entry.get("title", "(Kein Titel)")
                    link    = entry.get("link", "")
                    summary = entry.get("summary", "")[:400]
                    datum   = entry.get("published", "")[:16]

                    neue_events.append({
                        "competitor": comp["name"],
                        "info":       comp["info"],
                        "typ":        erkenne_event(title, summary),
                        "titel":      title,
                        "link":       link,
                        "summary":    summary,
                        "datum":      datum,
                    })
                    gesehen[uid] = datetime.utcnow().isoformat()

            except Exception as e:
                print(f"⚠️  Fehler bei {comp['name']}: {e}")

    speichere_gesehen(gesehen)
    return neue_events

# ─────────────────────────────────────────────
# EMAIL ERSTELLEN
# ─────────────────────────────────────────────
FARBEN = {
    "🔴": "#dc3545",
    "🟡": "#ffc107",
    "🔵": "#0d6efd",
    "🟠": "#fd7e14",
    "🟢": "#198754",
    "⚪": "#6c757d",
    "📰": "#6c757d",
}

def erstelle_html(events):
    # Gruppiere nach Competitor
    by_comp = {}
    for e in events:
        by_comp.setdefault(e["competitor"], []).append(e)

    inhalt = ""
    for comp_name, evs in by_comp.items():
        inhalt += f"""
        <div style="margin:24px 0 8px;padding:10px 14px;background:#003366;color:white;
                    border-radius:5px;font-size:15px">
            <strong>{comp_name}</strong>
            <span style="opacity:0.7;font-size:12px;margin-left:8px">{evs[0]['info']}</span>
        </div>"""
        for e in evs:
            farbe = FARBEN.get(e["typ"][0], "#6c757d")
            inhalt += f"""
            <div style="border:1px solid #dee2e6;border-radius:6px;padding:14px;margin:8px 0;
                        border-left:4px solid {farbe};background:#fff">
                <div style="margin-bottom:8px">
                    <span style="background:{farbe};color:white;padding:2px 10px;
                                 border-radius:12px;font-size:11px;font-weight:bold">{e['typ']}</span>
                    <span style="float:right;color:#adb5bd;font-size:11px">{e['datum']}</span>
                </div>
                <p style="margin:4px 0 6px">
                    <strong>
                        <a href="{e['link']}" style="color:#003366;text-decoration:none">{e['titel']}</a>
                    </strong>
                </p>
                {"<p style='margin:4px 0;color:#6c757d;font-size:13px;line-height:1.5'>" + e['summary'] + "</p>" if e['summary'] else ""}
                <a href="{e['link']}"
                   style="display:inline-block;margin-top:8px;padding:4px 12px;
                          background:#003366;color:white;border-radius:4px;
                          text-decoration:none;font-size:12px">Artikel lesen →</a>
            </div>"""

    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;
                 padding:20px;background:#f8f9fa;color:#212529">
        <div style="background:#003366;color:white;padding:22px;
                    border-radius:8px 8px 0 0;text-align:center">
            <h1 style="margin:0;font-size:22px">🔍 Oerlikon Competitor Intelligence</h1>
            <p style="margin:6px 0 0;opacity:0.75;font-size:13px">
                {datetime.now().strftime('%d.%m.%Y %H:%M')} Uhr &nbsp;|&nbsp;
                {len(events)} neue{'s Event' if len(events)==1 else ' Events'} gefunden
            </p>
        </div>
        <div style="background:#f8f9fa;padding:20px;border-radius:0 0 8px 8px">
            {inhalt}
        </div>
        <p style="text-align:center;color:#adb5bd;font-size:11px;margin-top:14px">
            Oerlikon Competitor Intelligence Agent &nbsp;•&nbsp; Automatisch generiert &nbsp;•&nbsp; 24/7
        </p>
    </body>
    </html>"""

# ─────────────────────────────────────────────
# EMAIL SENDEN
# ─────────────────────────────────────────────
def sende_email(events):
    if not events:
        print("✅ Keine neuen Events – kein Alert gesendet.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔍 Competitor Alert: {len(events)} neue Events | {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    msg["From"]    = EMAIL_ABSENDER
    msg["To"]      = EMAIL_EMPFAENGER
    msg.attach(MIMEText(erstelle_html(events), "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_ABSENDER, EMAIL_PASSWORT)
        server.sendmail(EMAIL_ABSENDER, EMAIL_EMPFAENGER, msg.as_string())

    print(f"✅ Email mit {len(events)} Events erfolgreich gesendet!")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%d.%m.%Y %H:%M')}] 🔍 Starte Competitor-Check...")
    events = pruefe_feeds()
    print(f"→ {len(events)} neue Event(s) gefunden.")
    sende_email(events)
