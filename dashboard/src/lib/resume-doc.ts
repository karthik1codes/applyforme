/** Editable master resume — Jake / academic single-column layout. */

export type ResumeExperience = {
  company: string;
  title: string;
  location: string;
  start: string;
  end: string;
  bullets: string[];
};

export type ResumeEducation = {
  school: string;
  degree: string;
  location: string;
  dates: string;
  details: string; // e.g. GPA
};

export type ResumeSkillCategory = {
  label: string;
  items: string;
};

export type ResumeProject = {
  name: string;
  tagline: string;
  links: string;
  bullets: string[];
};

export type ResumeCustomSection = {
  title: string;
  bullets: string[];
};

export type ResumeEditorDoc = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  location: string;
  linkedin: string;
  github: string;
  website: string;
  portfolio_label: string;
  summary: string;
  show_summary: boolean;
  skills: string[]; // flat fallback
  skill_categories: ResumeSkillCategory[];
  experience: ResumeExperience[];
  education: ResumeEducation[];
  projects: ResumeProject[];
  honors: string[];
  custom_sections: ResumeCustomSection[];
};

export function emptyExperience(): ResumeExperience {
  return { company: "", title: "", location: "", start: "", end: "", bullets: [""] };
}

export function emptyEducation(): ResumeEducation {
  return { school: "", degree: "", location: "", dates: "", details: "" };
}

export function emptySkillCategory(): ResumeSkillCategory {
  return { label: "", items: "" };
}

export function emptyProject(): ResumeProject {
  return { name: "", tagline: "", links: "", bullets: [""] };
}

export function emptyCustomSection(): ResumeCustomSection {
  return { title: "", bullets: [""] };
}

function asBullets(v: unknown): string[] {
  if (Array.isArray(v)) return v.map(String);
  if (typeof v === "string" && v.trim()) return [v];
  return [""];
}

export function profileToResumeDoc(p: {
  personal?: Record<string, string>;
  summary?: string;
  skills?: string[];
  experience?: unknown[];
  education?: unknown[];
  projects?: unknown[];
  honors?: unknown[];
  skill_categories?: unknown[];
  custom_sections?: unknown[];
  resume?: { show_summary?: boolean; portfolio_label?: string };
}): ResumeEditorDoc {
  const personal = p.personal || {};
  const experience = (p.experience || []).map((raw) => {
    const x = raw as Record<string, unknown>;
    const bullets = asBullets(x.highlights ?? x.bullets);
    return {
      company: String(x.company || ""),
      title: String(x.title || ""),
      location: String(x.location || ""),
      start: String(x.start || ""),
      end: String(x.end || ""),
      bullets: bullets.length ? bullets : [""],
    };
  });
  const education = (p.education || []).map((raw) => {
    const x = raw as Record<string, unknown>;
    const dates = String(x.dates || x.year || "");
    const degree = String(x.degree || "");
    const details = String(x.details || x.gpa || x.program || x.field || "");
    return {
      school: String(x.school || ""),
      degree,
      location: String(x.location || ""),
      dates,
      details,
    };
  });

  let skill_categories = (p.skill_categories || []).map((raw) => {
    const x = raw as Record<string, unknown>;
    const items = Array.isArray(x.items) ? x.items.map(String).join(", ") : String(x.items || "");
    return { label: String(x.label || x.name || ""), items };
  });
  if (!skill_categories.length && (p.skills || []).length) {
    skill_categories = [{ label: "Skills", items: (p.skills || []).join(", ") }];
  }

  const projects = (p.projects || []).map((raw) => {
    const x = raw as Record<string, unknown>;
    return {
      name: String(x.name || x.title || ""),
      tagline: String(x.tagline || x.description || ""),
      links: String(x.links || ""),
      bullets: asBullets(x.bullets ?? x.highlights),
    };
  });

  const honors = (p.honors || []).map(String);
  const custom_sections = (p.custom_sections || []).map((raw) => {
    const x = raw as Record<string, unknown>;
    return {
      title: String(x.title || ""),
      bullets: asBullets(x.bullets ?? x.items),
    };
  });

  return {
    first_name: personal.first_name || "",
    last_name: personal.last_name || "",
    email: personal.email || "",
    phone: personal.phone || "",
    location: personal.location || "",
    linkedin: personal.linkedin || "",
    github: personal.github || "",
    website: personal.website || personal.portfolio || "",
    portfolio_label: p.resume?.portfolio_label || "Portfolio",
    summary: (p.summary || "").trim(),
    show_summary: p.resume?.show_summary ?? false,
    skills: [...(p.skills || [])],
    skill_categories: skill_categories.length ? skill_categories : [emptySkillCategory()],
    experience: experience.length ? experience : [emptyExperience()],
    education: education.length ? education : [emptyEducation()],
    projects: projects.length ? projects : [],
    honors: honors.length ? honors : [],
    custom_sections: custom_sections.length ? custom_sections : [],
  };
}

export function resumeDocToProfilePatch(doc: ResumeEditorDoc) {
  const flatSkills = doc.skill_categories
    .flatMap((c) => c.items.split(",").map((s) => s.trim()))
    .filter(Boolean);
  return {
    personal: {
      first_name: doc.first_name.trim(),
      last_name: doc.last_name.trim(),
      email: doc.email.trim(),
      phone: doc.phone.trim(),
      location: doc.location.trim(),
      linkedin: doc.linkedin.trim(),
      github: doc.github.trim(),
      website: doc.website.trim(),
    },
    summary: doc.summary.trim(),
    skills: flatSkills.length ? flatSkills : doc.skills.map((s) => s.trim()).filter(Boolean),
    skill_categories: doc.skill_categories
      .filter((c) => c.label.trim() || c.items.trim())
      .map((c) => ({
        label: c.label.trim(),
        items: c.items
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      })),
    experience: doc.experience
      .filter((r) => r.company.trim() || r.title.trim())
      .map((r) => ({
        company: r.company.trim(),
        title: r.title.trim(),
        location: r.location.trim(),
        start: r.start.trim(),
        end: r.end.trim(),
        highlights: r.bullets.map((b) => b.trim()).filter(Boolean),
      })),
    education: doc.education
      .filter((e) => e.school.trim() || e.degree.trim())
      .map((e) => ({
        school: e.school.trim(),
        degree: e.degree.trim(),
        location: e.location.trim(),
        year: e.dates.trim(),
        dates: e.dates.trim(),
        details: e.details.trim(),
        program: e.details.trim(),
      })),
    projects: doc.projects
      .filter((p) => p.name.trim())
      .map((p) => ({
        name: p.name.trim(),
        tagline: p.tagline.trim(),
        links: p.links.trim(),
        bullets: p.bullets.map((b) => b.trim()).filter(Boolean),
      })),
    honors: doc.honors.map((h) => h.trim()).filter(Boolean),
    custom_sections: doc.custom_sections
      .filter((s) => s.title.trim())
      .map((s) => ({
        title: s.title.trim(),
        bullets: s.bullets.map((b) => b.trim()).filter(Boolean),
      })),
    resume: {
      show_summary: doc.show_summary,
      portfolio_label: doc.portfolio_label.trim() || "Portfolio",
    },
  };
}
