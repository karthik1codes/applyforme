"""Jake-style academic resume (single-column, Times, black rules) as self-contained .tex / HTML.

Matches the dashboard resume editor preview/export. No browser print chrome in the PDF itself
(\\pagestyle{empty}); users should also disable Headers & footers when printing HTML.
"""
from __future__ import annotations

import re

from ..models import Profile, ResumeDoc

_TEX_ESC = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\u2013": "--",
    "\u2014": "---",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": "``",
    "\u201d": "''",
}


def _tex(s: object) -> str:
    return "".join(_TEX_ESC.get(c, c) for c in str(s))


def _href(url: str, label: str) -> str:
    safe = url.replace("\\", "").replace("%", r"\%").replace("#", r"\#")
    return rf"\href{{{safe}}}{{{_tex(label)}}}"


def _date_range(start: str, end: str) -> str:
    s, e = (start or "").strip(), (end or "").strip()
    if s and e:
        return f"{_tex(s)} -- {_tex(e)}"
    return _tex(s or e)


def _bold_lead_bullet(raw: str) -> str:
    """Lead: rest → \\textbf{Lead:} rest (for LaTeX items)."""
    m = re.match(r"^([^:—\-]{2,48})\s*[:—\-]\s+(.+)$", raw.strip())
    if m:
        return rf"\textbf{{{_tex(m.group(1).strip())}:}} {_tex(m.group(2))}"
    return _tex(raw)


def _skill_lines(profile: Profile, doc: ResumeDoc) -> list[str]:
    cats = getattr(profile, "skill_categories", None) or []
    lines: list[str] = []
    for c in cats:
        label = str(c.get("label") or c.get("name") or "").strip()
        items = c.get("items")
        if isinstance(items, list):
            items_s = ", ".join(str(i) for i in items if i)
        else:
            items_s = str(items or "").strip()
        if label or items_s:
            lines.append(f"{label}: {items_s}" if label else items_s)
    if not lines and doc.skills:
        lines.append("Skills: " + ", ".join(doc.skills))
    return lines


def _contact_tex(profile: Profile) -> str:
    p = profile.personal
    parts: list[str] = []
    if p.get("email"):
        parts.append(_href("mailto:" + p["email"], p["email"]))
    if p.get("phone"):
        parts.append(_tex(p["phone"]))
    website = p.get("website") or p.get("portfolio")
    if website:
        label = (profile.resume or {}).get("portfolio_label") or "Portfolio"
        parts.append(_href(website, str(label)))
    if p.get("github"):
        parts.append(_href(p["github"], "GitHub"))
    if p.get("linkedin"):
        parts.append(_href(p["linkedin"], "LinkedIn"))
    if p.get("twitter"):
        parts.append(_href(p["twitter"], "Twitter"))
    return r" $|$ ".join(parts)


def render_elegant_latex(doc: ResumeDoc, profile: Profile) -> str:
    p = profile.personal
    name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    contact = _contact_tex(profile)

    show_summary = bool((profile.resume or {}).get("show_summary")) and bool(doc.summary.strip())
    summary_tex = ""
    if show_summary:
        summary_tex = rf"""
\resumeSection{{Professional Summary}}
{_tex(doc.summary)}
"""

    edu_blocks: list[str] = []
    for x in profile.education:
        school = str(x.get("school") or "")
        location = str(x.get("location") or "")
        degree = str(x.get("degree") or "")
        details = str(x.get("details") or x.get("gpa") or x.get("program") or x.get("field") or "")
        dates = str(x.get("dates") or x.get("year") or "")
        degree_line = "; ".join(t for t in (degree, details) if t)
        edu_blocks.append(
            rf"""\resumeSubheading{{{_tex(school)}}}{{{_tex(location)}}}{{{_tex(degree_line)}}}{{{_tex(dates)}}}"""
        )
    education = "\n".join(edu_blocks)

    skill_items = "\n".join(
        rf"  \item \textbf{{{_tex(line.split(':', 1)[0].strip())}:}} {_tex(line.split(':', 1)[1].strip())}"
        if ":" in line
        else rf"  \item {_tex(line)}"
        for line in _skill_lines(profile, doc)
    )

    # Prefer tailored roles; fill location from profile experience when missing
    loc_by_company = {
        str(x.get("company") or ""): str(x.get("location") or "")
        for x in (profile.experience or [])
    }
    exp_blocks: list[str] = []
    for r in doc.experience:
        loc = (r.location or loc_by_company.get(r.company, "")).strip()
        bullets = "\n".join(rf"    \item {_bold_lead_bullet(b)}" for b in r.bullets) or r"    \item "
        exp_blocks.append(
            rf"""\resumeSubheading{{{_tex(r.company)}}}{{{_tex(loc)}}}{{{_tex(r.title)}}}{{{_date_range(r.start, r.end)}}}
  \resumeItemListStart
{bullets}
  \resumeItemListEnd"""
        )
    experience = "\n\n".join(exp_blocks)

    proj_blocks: list[str] = []
    for x in getattr(profile, "projects", None) or []:
        pname = str(x.get("name") or x.get("title") or "").strip()
        if not pname:
            continue
        tagline = str(x.get("tagline") or x.get("description") or "").strip()
        links = str(x.get("links") or "").strip()
        title = f"{pname} -- {tagline}" if tagline else pname
        bullets_raw = x.get("bullets") or x.get("highlights") or []
        if isinstance(bullets_raw, str):
            bullets_raw = [bullets_raw]
        bullets = "\n".join(rf"    \item {_bold_lead_bullet(str(b))}" for b in bullets_raw if str(b).strip())
        bullets = bullets or r"    \item "
        proj_blocks.append(
            rf"""\resumeProjectHeading{{\textbf{{{_tex(title)}}}}}{{{_tex(links)}}}
  \resumeItemListStart
{bullets}
  \resumeItemListEnd"""
        )
    projects = "\n\n".join(proj_blocks)

    honors = getattr(profile, "honors", None) or []
    honors_tex = "\n".join(rf"  \item {_tex(h)}" for h in honors if str(h).strip())

    custom_tex_parts: list[str] = []
    for s in getattr(profile, "custom_sections", None) or []:
        title = str(s.get("title") or "").strip()
        if not title:
            continue
        bullets_raw = s.get("bullets") or s.get("items") or []
        if isinstance(bullets_raw, str):
            bullets_raw = [bullets_raw]
        items = "\n".join(rf"  \item {_bold_lead_bullet(str(b))}" for b in bullets_raw if str(b).strip())
        custom_tex_parts.append(
            rf"""
\resumeSection{{{_tex(title)}}}
\begin{{itemize}}[leftmargin=1.15em,itemsep=1pt,topsep=2pt,parsep=0pt]
{items}
\end{{itemize}}
"""
        )

    education_tex = education or r"\textit{See profile}"
    skill_tex = skill_items or r"  \item See profile"

    return rf"""% Generated by applyforme — Jake-style academic resume (single-column).
\documentclass[10pt,letterpaper]{{article}}
\usepackage[left=0.55in,top=0.45in,right=0.55in,bottom=0.45in]{{geometry}}
\usepackage[T1]{{fontenc}}
\usepackage{{mathptmx}}
\usepackage{{xcolor}}
\usepackage[hidelinks]{{hyperref}}
\usepackage{{enumitem}}
\pagestyle{{empty}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0pt}}
\setlist[itemize]{{leftmargin=1.15em,itemsep=1pt,topsep=2pt,parsep=0pt}}

\newcommand{{\resumeSection}}[1]{{%
  \vspace{{8pt}}%
  {{\scshape\bfseries\large #1}}\\[-2pt]%
  \hrule height 0.6pt%
  \vspace{{4pt}}%
}}
\newcommand{{\resumeSubheading}}[4]{{
  \vspace{{1pt}}\textbf{{#1}} \hfill #2\\
  \textit{{#3}} \hfill #4\vspace{{-2pt}}
}}
\newcommand{{\resumeProjectHeading}}[2]{{
  \vspace{{1pt}}#1 \hfill #2\vspace{{-2pt}}
}}
\newcommand{{\resumeItemListStart}}{{\begin{{itemize}}}}
\newcommand{{\resumeItemListEnd}}{{\end{{itemize}}\vspace{{-4pt}}}}

\begin{{document}}

\begin{{center}}
  {{\Huge\bfseries {_tex(name)}}}\\[4pt]
  {{\small {contact}}}
\end{{center}}
{summary_tex}
\resumeSection{{Education}}
{education_tex}

\resumeSection{{Skills}}
\begin{{itemize}}
{skill_tex}
\end{{itemize}}

\resumeSection{{Experience}}
{experience}

""" + (
        rf"""
\resumeSection{{Projects}}
{projects}
"""
        if projects
        else ""
    ) + (
        rf"""
\resumeSection{{Honors and Awards}}
\begin{{itemize}}
{honors_tex}
\end{{itemize}}
"""
        if honors_tex
        else ""
    ) + "".join(custom_tex_parts) + r"""
\end{document}
"""


def render_elegant_html(doc: ResumeDoc, profile: Profile) -> str:
    """HTML twin of the Jake-style resume (print: disable browser Headers & footers)."""
    import html as H

    p, e = profile.personal, H.escape
    name = e(f"{p.get('first_name', '')} {p.get('last_name', '')}".strip())

    contact_parts: list[str] = []
    if p.get("email"):
        contact_parts.append(e(p["email"]))
    if p.get("phone"):
        contact_parts.append(e(p["phone"]))
    website = p.get("website") or p.get("portfolio")
    if website:
        label = e(str((profile.resume or {}).get("portfolio_label") or "Portfolio"))
        contact_parts.append(f'<a href="{e(website)}">{label}</a>')
    if p.get("github"):
        contact_parts.append(f'<a href="{e(p["github"])}">GitHub</a>')
    if p.get("linkedin"):
        contact_parts.append(f'<a href="{e(p["linkedin"])}">LinkedIn</a>')
    if p.get("twitter"):
        contact_parts.append(f'<a href="{e(p["twitter"])}">Twitter</a>')
    contact = ' <span class="sep">|</span> '.join(contact_parts)

    def fmt_bullet(raw: str) -> str:
        m = re.match(r"^([^:—\-]{2,48})\s*[:—\-]\s+(.+)$", raw.strip())
        if m:
            return f"<strong>{e(m.group(1).strip())}:</strong> {e(m.group(2))}"
        return e(raw)

    edu = ""
    for x in profile.education:
        school = e(str(x.get("school") or ""))
        location = e(str(x.get("location") or ""))
        degree = str(x.get("degree") or "")
        details = str(x.get("details") or x.get("gpa") or x.get("program") or x.get("field") or "")
        dates = e(str(x.get("dates") or x.get("year") or ""))
        degree_line = e("; ".join(t for t in (degree, details) if t))
        edu += (
            f"<div class='block'><div class='row'><strong>{school}</strong><span>{location}</span></div>"
            f"<div class='row'><em>{degree_line}</em><span>{dates}</span></div></div>"
        )

    skills = "".join(
        f"<li><strong>{e(line.split(':', 1)[0].strip())}:</strong> {e(line.split(':', 1)[1].strip())}</li>"
        if ":" in line
        else f"<li>{e(line)}</li>"
        for line in _skill_lines(profile, doc)
    )

    loc_by_company = {
        str(x.get("company") or ""): str(x.get("location") or "")
        for x in (profile.experience or [])
    }
    roles = ""
    for r in doc.experience:
        loc = e((r.location or loc_by_company.get(r.company, "")).strip())
        dates = e(" – ".join(t for t in (r.start, r.end) if t))
        bullets = "".join(f"<li>{fmt_bullet(b)}</li>" for b in r.bullets if b.strip())
        roles += (
            f"<div class='block'><div class='row'><strong>{e(r.company)}</strong><span>{loc}</span></div>"
            f"<div class='row'><em>{e(r.title)}</em><span>{dates}</span></div>"
            f"<ul>{bullets}</ul></div>"
        )

    projects = ""
    for x in getattr(profile, "projects", None) or []:
        pname = str(x.get("name") or x.get("title") or "").strip()
        if not pname:
            continue
        tagline = str(x.get("tagline") or "").strip()
        title = e(f"{pname} – {tagline}" if tagline else pname)
        links = e(str(x.get("links") or ""))
        bullets_raw = x.get("bullets") or x.get("highlights") or []
        if isinstance(bullets_raw, str):
            bullets_raw = [bullets_raw]
        bullets = "".join(f"<li>{fmt_bullet(str(b))}</li>" for b in bullets_raw if str(b).strip())
        projects += (
            f"<div class='block'><div class='row'><strong>{title}</strong><span>{links}</span></div>"
            f"<ul>{bullets}</ul></div>"
        )

    honors = getattr(profile, "honors", None) or []
    honors_html = "".join(f"<li>{e(str(h))}</li>" for h in honors if str(h).strip())

    custom = ""
    for s in getattr(profile, "custom_sections", None) or []:
        title = str(s.get("title") or "").strip()
        if not title:
            continue
        bullets_raw = s.get("bullets") or s.get("items") or []
        if isinstance(bullets_raw, str):
            bullets_raw = [bullets_raw]
        items = "".join(f"<li>{fmt_bullet(str(b))}</li>" for b in bullets_raw if str(b).strip())
        custom += f"<div class='section'><h2>{e(title.upper())}</h2><ul>{items}</ul></div>"

    show_summary = bool((profile.resume or {}).get("show_summary")) and bool(doc.summary.strip())
    summary = (
        f"<div class='section'><h2>PROFESSIONAL SUMMARY</h2><p>{e(doc.summary)}</p></div>"
        if show_summary
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<title>&#8203;</title>
<style>
@page {{ size: letter; margin: 0.5in 0.6in; }}
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0; padding: 0;
  font-family: "Times New Roman", Times, "Liberation Serif", Georgia, serif;
  font-size: 10.5pt; color: #000; background: #fff; line-height: 1.25;
}}
@media print {{
  a {{ color: #000; text-decoration: none; }}
}}
.page {{ max-width: 8in; margin: 0 auto; }}
h1 {{ text-align: center; font-size: 22pt; font-weight: 700; margin: 0 0 4px; }}
.contact {{ text-align: center; font-size: 10pt; margin: 0 0 10px; }}
.contact a {{ color: #000; text-decoration: underline; }}
.contact .sep {{ margin: 0 0.35em; }}
.section {{ margin-top: 8px; }}
.section h2, h2 {{
  font-size: 11pt; font-weight: 700; letter-spacing: 0.03em;
  margin: 8px 0 4px; padding-bottom: 1px;
  border-bottom: 1px solid #000; text-transform: uppercase;
}}
.block {{ margin: 4px 0 6px; }}
.row {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }}
.row span {{ white-space: nowrap; font-size: 10pt; }}
ul {{ margin: 2px 0 0 1.15em; padding: 0; }}
li {{ margin: 1px 0; }}
p {{ margin: 2px 0; }}
</style></head>
<body><div class="page">
  <h1>{name}</h1>
  <div class="contact">{contact}</div>
  {summary}
  <div class="section"><h2>EDUCATION</h2>{edu or '<p>—</p>'}</div>
  <div class="section"><h2>SKILLS</h2><ul>{skills}</ul></div>
  <div class="section"><h2>EXPERIENCE</h2>{roles}</div>
  {f'<div class="section"><h2>PROJECTS</h2>{projects}</div>' if projects else ''}
  {f'<div class="section"><h2>HONORS AND AWARDS</h2><ul>{honors_html}</ul></div>' if honors_html else ''}
  {custom}
</div>
<script>try {{ document.title = "\\u200b"; }} catch (err) {{}}</script>
</body></html>"""
