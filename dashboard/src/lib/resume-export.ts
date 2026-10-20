import type { ResumeEditorDoc } from "@/lib/resume-doc";

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** Format bullet: **Lead:** rest → <strong>Lead:</strong> rest */
function formatBullet(raw: string): string {
  const m = raw.match(/^(\*\*)?([^*:—-]{2,48})(\*\*)?\s*[:—-]\s+(.+)$/);
  if (m) return `<strong>${esc(m[2].replace(/\*\*/g, "").trim())}:</strong> ${esc(m[4])}`;
  const m2 = raw.match(/^([^:—-]{2,40}):\s+(.+)$/);
  if (m2) return `<strong>${esc(m2[1].trim())}:</strong> ${esc(m2[2])}`;
  return esc(raw);
}

function contactLine(doc: ResumeEditorDoc): string {
  const parts: string[] = [];
  if (doc.email) parts.push(esc(doc.email));
  if (doc.phone) parts.push(esc(doc.phone));
  if (doc.website) {
    const label = esc(doc.portfolio_label || "Portfolio");
    parts.push(`<a href="${esc(doc.website)}">${label}</a>`);
  }
  if (doc.github) {
    parts.push(`<a href="${esc(doc.github)}">GitHub</a>`);
  }
  if (doc.linkedin) {
    parts.push(`<a href="${esc(doc.linkedin)}">LinkedIn</a>`);
  }
  return parts.join(" <span class=\"sep\">|</span> ");
}

/** Standalone HTML — Jake-style academic resume. Print has no browser chrome title/url when saved via this file. */
export function resumeDocToHtml(doc: ResumeEditorDoc): string {
  const name = esc(`${doc.first_name} ${doc.last_name}`.trim() || "Your Name");

  const edu = doc.education
    .filter((e) => e.school || e.degree)
    .map((e) => {
      const degreeLine = [e.degree, e.details].filter(Boolean).join("; ");
      return `<div class="block">
  <div class="row"><strong>${esc(e.school)}</strong><span>${esc(e.location)}</span></div>
  <div class="row"><em>${esc(degreeLine)}</em><span>${esc(e.dates)}</span></div>
</div>`;
    })
    .join("");

  const skills = doc.skill_categories
    .filter((c) => c.label.trim() || c.items.trim())
    .map((c) => `<li><strong>${esc(c.label)}:</strong> ${esc(c.items)}</li>`)
    .join("");

  const exp = doc.experience
    .filter((r) => r.company || r.title)
    .map((r) => {
      const dates = [r.start, r.end].filter(Boolean).join(" – ");
      const bullets = r.bullets
        .filter((b) => b.trim())
        .map((b) => `<li>${formatBullet(b)}</li>`)
        .join("");
      return `<div class="block">
  <div class="row"><strong>${esc(r.company)}</strong><span>${esc(r.location)}</span></div>
  <div class="row"><em>${esc(r.title)}</em><span>${esc(dates)}</span></div>
  <ul>${bullets}</ul>
</div>`;
    })
    .join("");

  const projects = doc.projects
    .filter((p) => p.name.trim())
    .map((p) => {
      const title = p.tagline ? `${esc(p.name)} – ${esc(p.tagline)}` : esc(p.name);
      const bullets = p.bullets
        .filter((b) => b.trim())
        .map((b) => `<li>${formatBullet(b)}</li>`)
        .join("");
      return `<div class="block">
  <div class="row"><strong>${title}</strong><span>${esc(p.links)}</span></div>
  <ul>${bullets}</ul>
</div>`;
    })
    .join("");

  const honors = doc.honors
    .filter((h) => h.trim())
    .map((h) => `<li>${esc(h)}</li>`)
    .join("");

  const custom = doc.custom_sections
    .filter((s) => s.title.trim())
    .map((s) => {
      const items = s.bullets
        .filter((b) => b.trim())
        .map((b) => `<li>${formatBullet(b)}</li>`)
        .join("");
      return `<div class="section"><h2>${esc(s.title.toUpperCase())}</h2><ul>${items}</ul></div>`;
    })
    .join("");

  const summary =
    doc.show_summary && doc.summary.trim()
      ? `<div class="section"><h2>PROFESSIONAL SUMMARY</h2><p>${esc(doc.summary)}</p></div>`
      : "";

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>&#8203;</title>
<style>
  /* Hide browser print header/footer as much as CSS allows */
  @page { size: letter; margin: 0.5in 0.6in; }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    font-family: "Times New Roman", Times, "Liberation Serif", Georgia, serif;
    font-size: 10.5pt; color: #000; background: #fff; line-height: 1.25;
  }
  @media print {
    html, body { background: #fff; }
    a { color: #000; text-decoration: none; }
    .no-print { display: none !important; }
  }
  .page { max-width: 8in; margin: 0 auto; }
  h1 {
    text-align: center; font-size: 22pt; font-weight: 700;
    margin: 0 0 4px; letter-spacing: 0.01em;
  }
  .contact {
    text-align: center; font-size: 10pt; margin: 0 0 10px;
  }
  .contact a { color: #000; text-decoration: underline; }
  .contact .sep { margin: 0 0.35em; color: #000; }
  .section { margin-top: 8px; }
  .section h2 {
    font-size: 11pt; font-weight: 700; letter-spacing: 0.03em;
    margin: 0 0 4px; padding-bottom: 1px;
    border-bottom: 1px solid #000; text-transform: uppercase;
  }
  .block { margin: 4px 0 6px; }
  .row { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }
  .row span { white-space: nowrap; font-size: 10pt; }
  ul { margin: 2px 0 0 1.15em; padding: 0; }
  li { margin: 1px 0; }
  p { margin: 2px 0; }
  em { font-style: italic; }
  strong { font-weight: 700; }
</style>
</head>
<body>
<div class="page">
  <h1>${name}</h1>
  <div class="contact">${contactLine(doc)}</div>
  ${summary}
  ${edu ? `<div class="section"><h2>EDUCATION</h2>${edu}</div>` : ""}
  ${skills ? `<div class="section"><h2>SKILLS</h2><ul>${skills}</ul></div>` : ""}
  ${exp ? `<div class="section"><h2>EXPERIENCE</h2>${exp}</div>` : ""}
  ${projects ? `<div class="section"><h2>PROJECTS</h2>${projects}</div>` : ""}
  ${honors ? `<div class="section"><h2>HONORS AND AWARDS</h2><ul>${honors}</ul></div>` : ""}
  ${custom}
</div>
<script>
  // Prefer blank document title so print headers don't show a long name/URL bar text
  try { document.title = "\\u200b"; } catch (e) {}
</script>
</body>
</html>`;
}

export function downloadBlob(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function resumeFileStem(doc: ResumeEditorDoc): string {
  const n = `${doc.first_name}-${doc.last_name}`.trim().replace(/[^\w-]+/g, "-") || "resume";
  return n.toLowerCase();
}
