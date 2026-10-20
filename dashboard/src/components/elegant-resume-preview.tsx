"use client";

import type { ReactNode } from "react";
import type { ResumeEditorDoc } from "@/lib/resume-doc";

/** Jake-style academic resume preview (matches PDF/HTML export). */
export function ElegantResumePreview({ doc }: { doc: ResumeEditorDoc }) {
  const name = `${doc.first_name} ${doc.last_name}`.trim() || "Your Name";
  const contact: ReactNode[] = [];
  if (doc.email) contact.push(<span key="e">{doc.email}</span>);
  if (doc.phone) contact.push(<span key="p">{doc.phone}</span>);
  if (doc.website) {
    contact.push(
      <a key="w" href={doc.website} className="underline">
        {doc.portfolio_label || "Portfolio"}
      </a>,
    );
  }
  if (doc.github) {
    contact.push(
      <a key="g" href={doc.github} className="underline">
        GitHub
      </a>,
    );
  }
  if (doc.linkedin) {
    contact.push(
      <a key="l" href={doc.linkedin} className="underline">
        LinkedIn
      </a>,
    );
  }

  return (
    <div
      className="mx-auto max-w-[8in] bg-white px-8 py-6 text-black shadow-sm"
      style={{ fontFamily: '"Times New Roman", Times, Georgia, serif', fontSize: "10.5pt", lineHeight: 1.25 }}
    >
      <h1 className="m-0 text-center text-[22pt] font-bold tracking-tight">{name}</h1>
      {contact.length > 0 && (
        <div className="mt-1 mb-2.5 flex flex-wrap items-center justify-center gap-x-0 text-center text-[10pt]">
          {contact.map((c, i) => (
            <span key={i} className="inline-flex items-center">
              {i > 0 && <span className="mx-1.5">|</span>}
              {c}
            </span>
          ))}
        </div>
      )}

      {doc.show_summary && doc.summary.trim() && (
        <Section title="Professional summary">
          <p className="m-0">{doc.summary}</p>
        </Section>
      )}

      {doc.education.some((e) => e.school || e.degree) && (
        <Section title="Education">
          {doc.education.map((e, i) => (
            <div key={i} className="mb-1.5">
              <Row left={<strong>{e.school || "School"}</strong>} right={e.location} />
              <Row
                left={<em>{[e.degree, e.details].filter(Boolean).join("; ")}</em>}
                right={e.dates}
              />
            </div>
          ))}
        </Section>
      )}

      {doc.skill_categories.some((c) => c.label || c.items) && (
        <Section title="Skills">
          <ul className="m-0 list-disc pl-5">
            {doc.skill_categories
              .filter((c) => c.label || c.items)
              .map((c, i) => (
                <li key={i} className="my-0.5">
                  <strong>{c.label}:</strong> {c.items}
                </li>
              ))}
          </ul>
        </Section>
      )}

      {doc.experience.some((r) => r.company || r.title) && (
        <Section title="Experience">
          {doc.experience.map((r, i) => (
            <div key={i} className="mb-2">
              <Row left={<strong>{r.company || "Company"}</strong>} right={r.location} />
              <Row
                left={<em>{r.title}</em>}
                right={[r.start, r.end].filter(Boolean).join(" – ")}
              />
              <ul className="mt-0.5 mb-0 list-disc pl-5">
                {r.bullets.filter((b) => b.trim()).map((b, j) => (
                  <li key={j} className="my-0.5">
                    <Bullet text={b} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      )}

      {doc.projects.some((p) => p.name) && (
        <Section title="Projects">
          {doc.projects.map((p, i) => (
            <div key={i} className="mb-2">
              <Row
                left={
                  <strong>
                    {p.name}
                    {p.tagline ? ` – ${p.tagline}` : ""}
                  </strong>
                }
                right={p.links}
              />
              <ul className="mt-0.5 mb-0 list-disc pl-5">
                {p.bullets.filter((b) => b.trim()).map((b, j) => (
                  <li key={j} className="my-0.5">
                    <Bullet text={b} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      )}

      {doc.honors.some((h) => h.trim()) && (
        <Section title="Honors and awards">
          <ul className="m-0 list-disc pl-5">
            {doc.honors.filter((h) => h.trim()).map((h, i) => (
              <li key={i} className="my-0.5">
                {h}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {doc.custom_sections
        .filter((s) => s.title.trim())
        .map((s, i) => (
          <Section key={i} title={s.title}>
            <ul className="m-0 list-disc pl-5">
              {s.bullets.filter((b) => b.trim()).map((b, j) => (
                <li key={j} className="my-0.5">
                  <Bullet text={b} />
                </li>
              ))}
            </ul>
          </Section>
        ))}
    </div>
  );
}

function Bullet({ text }: { text: string }) {
  const m = text.match(/^([^:—-]{2,40}):\s+(.+)$/);
  if (m) {
    return (
      <>
        <strong>{m[1].trim()}:</strong> {m[2]}
      </>
    );
  }
  return <>{text}</>;
}

function Row({ left, right }: { left: ReactNode; right?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <div className="min-w-0">{left}</div>
      {right ? <span className="shrink-0 whitespace-nowrap text-[10pt]">{right}</span> : null}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-2">
      <h2 className="m-0 mb-1 border-b border-black pb-px text-[11pt] font-bold tracking-wide uppercase">
        {title}
      </h2>
      {children}
    </section>
  );
}
