import { NextResponse } from "next/server";
import { auth, authDisabled } from "@/auth";
import { importResumeIntoProfile } from "@/lib/import-resume";
import { saveResume, upsertUser } from "@/lib/users";

export const runtime = "nodejs";
export const maxDuration = 120;

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user?.email && !authDisabled()) {
    return NextResponse.json({ error: "Sign in required" }, { status: 401 });
  }

  const form = await req.formData();
  const file = form.get("resume");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "Missing resume file" }, { status: 400 });
  }

  const userId = (session?.user as { id?: string } | undefined)?.id || session?.user?.email || "local";
  const email = session?.user?.email || "local@localhost";
  upsertUser({ id: userId, email, name: session?.user?.name, image: session?.user?.image });

  try {
    const buf = Buffer.from(await file.arrayBuffer());
    const saved = saveResume(userId, file.name, buf);

    // Parse full resume into profile.yaml so Profile fields + Tailor PDFs update immediately.
    const imported = importResumeIntoProfile(saved.path);

    return NextResponse.json({
      ok: true,
      name: saved.publicName,
      imported: imported.ok,
      roles: imported.roles,
      skills: imported.skills,
      education: imported.education,
      projects: imported.projects,
      honors: imported.honors,
      importMessage: imported.message,
    });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : "Upload failed" }, { status: 400 });
  }
}
