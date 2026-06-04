#!/usr/bin/env python3
"""
generate_brief.py
─────────────────
Run by GitHub Actions every weekday at 6 AM IST.
Calls Claude with web search → writes docs/index.html (today's brief)
and docs/archive/YYYY-MM-DD.html (permanent copy).

No external dependencies beyond `anthropic`.
"""

import os, sys, datetime, textwrap, pathlib
import anthropic

API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL   = "claude-sonnet-4-20250514"

# ── Dates ────────────────────────────────────────────────────────────────────

def get_dates():
    today = datetime.date.today()
    prev  = today - datetime.timedelta(days=3 if today.weekday() == 0 else 1)
    return (
        today.strftime("%B %d, %Y"),    # brief_date_human
        prev.strftime("%B %d, %Y"),     # data_date_human
        today.isoformat(),              # brief_date_iso
        prev.isoformat(),               # data_date_iso
    )

# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM = textwrap.dedent("""
You are a senior financial analyst producing the Infinyte Brief — a daily
morning intelligence report for seasoned institutional investors at Infinyte
Capital, primarily focused on India with global context.

OUTPUT: Return a single complete, self-contained HTML file.
- All CSS must be embedded in a <style> tag inside <head>
- No external stylesheets, no CDN links, no JavaScript frameworks
- Minimal vanilla JS only (tab switching)
- The file must render perfectly offline in any browser

DESIGN REQUIREMENTS (premium, editorial, dark-mode aware):
- Font stack: Georgia serif for the wordmark and story headlines;
  -apple-system / system-ui sans for all other text
- Background: #F5F4F0 (light) / #111110 (dark)
- Cards: white (#FFFFFF) with 0.5px #E2DFD8 border, 8px radius
- Six tabs: Markets · Macro & Economy · Policy · Global · Private Markets · On the Radar
- Top snapshot strip: Nifty 50, Sensex, S&P 500, USD/INR, Brent, Gold, India VIX
  — each in a small card with value and % change (green/red)
- Colour-coded category tags on each story (tiny, uppercase, pill shape)
- Footer: source citations + "Infinyte · Confidential"
- Fully responsive (mobile-friendly)
- prefers-color-scheme dark mode via CSS variables

DATA RULES:
- Use web_search to fetch ALL data before writing HTML
- Only include figures from official/verified sources
  (Yahoo Finance, NSE India, TradingEconomics, BSE, CNBC, Business Standard,
  MoSPI, RBI, SEC EDGAR)
- If a number cannot be verified, show — (em dash), never invent data
- Cite sources inline on each story (small muted text below the body)

CONTENT:
Markets tab:   India indices (Nifty, Sensex, India VIX), top 5 movers,
               USD/INR, 10-yr G-Sec yield, FPI flows, 3-4 India market stories
Macro tab:     India CPI, GDP, PMI, rupee context, macro data table, 2-3 stories
Policy tab:    RBI repo/SDF/MSF rates, MPC stance, next decision date, policy news
Global tab:    S&P 500, Nasdaq, Dow, Brent, WTI, Gold, US 10-yr, Fed expectations,
               3-4 global stories (geopolitics, earnings, macro)
Private tab:   India VC context (annual figures), 6 investing themes (AI, fintech,
               climate, defence, quick commerce, health), 2-3 VC stories
Radar tab:     India upcoming events, Global upcoming events, Week Ahead calendar

Return ONLY the raw HTML starting with <!DOCTYPE html>. No markdown. No preamble.
""")

def build_prompt(brief_human, data_human, brief_iso, data_iso):
    return textwrap.dedent(f"""
        Today is {brief_human}. Brief date: {brief_iso}. Data date: {data_iso}.

        Search for and retrieve verified closing data for {data_human}:

        INDIA (search first):
        • Nifty 50 closing level and % change (source: NSE, Yahoo Finance)
        • BSE Sensex closing level and % change
        • India VIX closing level
        • USD/INR exchange rate
        • Top 5 Nifty gainers and losers with % change
        • RBI repo rate and any MPC/policy news
        • India CPI or PMI data if released that day
        • Any government or SEBI policy announcements
        • FPI/FII flows into Indian equities

        GLOBAL:
        • S&P 500, Nasdaq, Dow Jones closing levels and % change
        • Brent crude and WTI oil closing prices and % change
        • Gold spot price (USD/oz) and % change
        • US 10-year Treasury yield
        • US VIX
        • Major earnings results
        • Key macro data (payrolls, CPI, PMI)
        • Significant geopolitical events

        PRIVATE MARKETS (contextual/weekly):
        • Any major India startup funding rounds announced recently
        • VC fund closures or notable PE deals
        • India IPO news

        After searching, write the complete HTML brief. Brief date in masthead: {brief_human}.
        Data date shown as: {data_human} close.
    """)

# ── Claude call (agentic — lets it search multiple times) ─────────────────────

def generate_html(brief_human, data_human, brief_iso, data_iso) -> str:
    client   = anthropic.Anthropic(api_key=API_KEY)
    messages = [{"role": "user", "content": build_prompt(
        brief_human, data_human, brief_iso, data_iso
    )}]

    last_resp = None
    for turn in range(15):                      # max 15 tool-call rounds
        resp = client.messages.create(
            model=MODEL,
            max_tokens=12000,
            system=SYSTEM,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        )
        last_resp = resp
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "end_turn":
            break

        if resp.stop_reason == "tool_use":
            tool_results = [
                {"type": "tool_result", "tool_use_id": b.id, "content": ""}
                for b in resp.content if b.type == "tool_use"
            ]
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    # Extract the HTML from the final text block
    html = ""
    for block in reversed(last_resp.content):
        if hasattr(block, "text") and block.text.strip().startswith("<!"):
            html = block.text.strip()
            break

    if not html:
        # Fallback: grab any text block
        for block in reversed(last_resp.content):
            if hasattr(block, "text"):
                html = block.text.strip()
                break

    return html

# ── File output ───────────────────────────────────────────────────────────────

def save(html: str, brief_iso: str):
    docs    = pathlib.Path("docs")
    archive = docs / "archive"
    docs.mkdir(exist_ok=True)
    archive.mkdir(exist_ok=True)

    # Latest (served by GitHub Pages as the homepage)
    (docs / "index.html").write_text(html, encoding="utf-8")

    # Permanent archive copy
    (archive / f"{brief_iso}.html").write_text(html, encoding="utf-8")

    print(f"[OK] Saved docs/index.html and docs/archive/{brief_iso}.html")

# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    brief_human, data_human, brief_iso, data_iso = get_dates()
    print(f"[INFO] Generating {brief_iso} brief (data: {data_iso})")

    try:
        html = generate_html(brief_human, data_human, brief_iso, data_iso)
        save(html, brief_iso)
        print("[DONE]")
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
