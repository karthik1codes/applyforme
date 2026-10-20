import Link from "next/link";
import { redirect } from "next/navigation";
import { auth, authDisabled } from "@/auth";
import { LandingHero } from "@/components/landing/hero";
import { isOnboardingCompleteForSession, sessionUserId } from "@/lib/onboarding-gate";
import { upsertUser, userHasResume } from "@/lib/users";

export const dynamic = "force-dynamic";

export default async function LandingPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; ref?: string; signedout?: string }>;
}) {
  const { next, ref, signedout } = await searchParams;
  const session = await auth();
  const userId = session?.user ? sessionUserId(session) : null;
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

  // Per-Gmail: this account must finish onboarding (not another user's yaml).
  const done = await isOnboardingCompleteForSession();
  const afterAuth = ref ? `/onboarding?ref=${encodeURIComponent(ref)}` : "/onboarding";
  const startHref = next?.startsWith("/onboarding") ? next : afterAuth;

  if (session?.user && !done && signedout !== "1") {
    redirect(startHref);
  }

  return (
    <>
      <LandingHero
        signedIn={!!session?.user}
        hasResume={hasResume}
        onboardingDone={done}
        userName={session?.user?.name}
        authOff={authDisabled()}
        next={startHref}
        referralCode={ref}
        signedOut={signedout === "1" && !session?.user}
      />

      <section id="how" className="relative z-10 border-t border-white/10 bg-black px-6 py-20 md:px-10 md:py-28">
        <div className="mx-auto max-w-5xl">
          <h2 className="font-[family-name:var(--font-landing-display)] text-[clamp(2rem,5vw,3.875rem)] font-medium leading-[1.15] tracking-[-0.02em]">
            From job board to submitted — without the grind
          </h2>
          <p className="mt-4 max-w-2xl font-[family-name:var(--font-landing-body)] text-lg font-medium text-white/75 md:text-xl">
            Sign in, tell us a bit about you, drop your resume, and let the agents discover, score, tailor, and fill applications. You approve every submit.
          </p>
          <ol className="mt-14 grid gap-10 md:grid-cols-3 md:gap-8">
            {[
              { n: "01", t: "Sign in", d: "Continue with Google so your applications stay tied to you." },
              { n: "02", t: "Quick onboarding", d: "Where you heard about us, your role, referral, then resume." },
              { n: "03", t: "Dashboard", d: "Watch matches, tailored resumes, and forms that wait for your yes." },
            ].map((s) => (
              <li key={s.n}>
                <span className="font-[family-name:var(--font-landing-body)] text-sm font-medium text-[#ff4c00]">{s.n}</span>
                <h3 className="mt-2 font-[family-name:var(--font-landing-display)] text-[1.8rem] font-medium leading-tight">{s.t}</h3>
                <p className="mt-2 font-[family-name:var(--font-landing-body)] text-base font-medium leading-relaxed text-white/70">{s.d}</p>
              </li>
            ))}
          </ol>
          <div className="mt-14">
            {session?.user ? (
              <Link
                href={done ? "/home" : startHref}
                className="inline-flex min-h-10 min-w-[160px] items-center justify-center rounded border border-transparent bg-white px-4 py-2 text-base font-normal text-black"
              >
                {done ? "Open dashboard" : "Continue setup"}
              </Link>
            ) : (
              <a
                href="#start"
                className="inline-flex min-h-10 min-w-[160px] items-center justify-center rounded border border-transparent bg-white px-4 py-2 text-base font-normal text-black"
              >
                Start applying
              </a>
            )}
          </div>
        </div>
      </section>
    </>
  );
}
