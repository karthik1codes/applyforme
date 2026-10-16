import Link from "next/link";
import { auth, authDisabled } from "@/auth";
import { LandingHero } from "@/components/landing/hero";
import { upsertUser, userHasResume } from "@/lib/users";

export const dynamic = "force-dynamic";

export default async function LandingPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  const session = await auth();
  const userId = (session?.user as { id?: string } | undefined)?.id || session?.user?.email || null;
  if (session?.user?.email && userId) {
    upsertUser({
      id: userId,
      email: session.user.email,
      name: session.user.name,
      image: session.user.image,
    });
  }
  const hasResume = userId
    ? userHasResume(userId)
    : authDisabled()
      ? userHasResume("local")
      : false;

  return (
    <>
      <LandingHero
        signedIn={!!session?.user}
        hasResume={hasResume}
        userName={session?.user?.name}
        authOff={authDisabled()}
        next={next}
      />

      <section id="how" className="relative z-10 border-t border-white/10 bg-black px-6 py-20 md:px-10 md:py-28">
        <div className="mx-auto max-w-5xl">
          <h2 className="font-[family-name:var(--font-landing-display)] text-[clamp(2rem,5vw,3.875rem)] font-medium leading-[1.15] tracking-[-0.02em]">
            From job board to submitted — without the grind
          </h2>
          <p className="mt-4 max-w-2xl font-[family-name:var(--font-landing-body)] text-lg font-medium text-white/75 md:text-xl">
            Sign in, drop your resume, and let the agents discover, score, tailor, and fill applications. You approve every submit.
          </p>
          <ol className="mt-14 grid gap-10 md:grid-cols-3 md:gap-8">
            {[
              { n: "01", t: "Sign in", d: "Continue with Google so your applications stay tied to you." },
              { n: "02", t: "Upload resume", d: "PDF or text. Agents use only what you give them — no invented experience." },
              { n: "03", t: "Let them apply", d: "Watch matches, tailored resumes, and forms that wait for your yes." },
            ].map((s) => (
              <li key={s.n}>
                <span className="font-[family-name:var(--font-landing-body)] text-sm font-medium text-[#ff4c00]">{s.n}</span>
                <h3 className="mt-2 font-[family-name:var(--font-landing-display)] text-[1.8rem] font-medium leading-tight">{s.t}</h3>
                <p className="mt-2 font-[family-name:var(--font-landing-body)] text-base font-medium leading-relaxed text-white/70">{s.d}</p>
              </li>
            ))}
          </ol>
          <div className="mt-14">
            <Link
              href="#start"
              className="inline-flex min-h-10 min-w-[160px] items-center justify-center rounded border border-transparent bg-white px-4 py-2 text-base font-normal text-black"
            >
              Start applying
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
