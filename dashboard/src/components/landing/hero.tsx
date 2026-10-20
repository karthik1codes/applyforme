"use client";

import Link from "next/link";
import { GoogleSignIn } from "@/components/landing/google-sign-in";
import { ResumeUpload } from "@/components/landing/resume-upload";
import { logout } from "@/app/actions/auth";

type Props = {
  signedIn: boolean;
  hasResume: boolean;
  onboardingDone: boolean;
  userName?: string | null;
  authOff: boolean;
  next?: string;
  referralCode?: string;
  signedOut?: boolean;
};

export function LandingHero({
  signedIn,
  hasResume,
  onboardingDone,
  userName,
  authOff,
  next,
  referralCode,
  signedOut,
}: Props) {
  const onboardingHref = referralCode
    ? `/onboarding?ref=${encodeURIComponent(referralCode)}`
    : "/onboarding";
  const afterSignIn = next?.startsWith("/onboarding")
    ? next
    : referralCode
      ? `/onboarding?ref=${encodeURIComponent(referralCode)}`
      : "/onboarding";
  const dashHref = onboardingDone ? "/home" : onboardingHref;

  return (
    <div className="relative min-h-svh overflow-hidden bg-black text-white">
      <div className="absolute inset-0">
        {/* eslint-disable-next-line @next/next/no-img-element -- public static hero asset */}
        <img
          src="/landing-hero.png"
          alt="Sunlit ruins of the Roman Forum under a blue sky"
          className="absolute inset-0 h-full min-h-svh w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/55 to-black/25" />
      </div>

      <header className="relative z-10 flex items-center justify-between px-6 py-5 md:px-10">
        <span className="font-[family-name:var(--font-landing-display)] text-xl font-medium tracking-tight md:text-2xl">
          applyforme
        </span>
        {signedIn ? (
          <div className="flex items-center gap-4">
            <Link href={dashHref} className="text-base font-medium underline underline-offset-4">
              {onboardingDone ? "Open dashboard" : "Continue setup"}
            </Link>
            {!authOff ? (
              <form action={logout}>
                <button type="submit" className="text-base font-medium text-white/80 underline underline-offset-4 hover:text-white">
                  Sign out
                </button>
              </form>
            ) : null}
          </div>
        ) : (
          <a href="#start" className="text-base font-medium underline underline-offset-4">
            Start applying
          </a>
        )}
      </header>

      <main className="relative z-10 flex min-h-[calc(100svh-5rem)] flex-col justify-end px-6 pb-16 pt-24 md:px-10 md:pb-24">
        <div id="start" className="max-w-3xl">
          <h1 className="font-[family-name:var(--font-landing-display)] text-[clamp(2.75rem,8vw,5.625rem)] font-medium leading-[1.15] tracking-[-0.025em]">
            applyforme
          </h1>
          <p className="mt-4 max-w-xl font-[family-name:var(--font-landing-body)] text-lg font-medium leading-relaxed text-white/85 md:text-xl md:leading-[1.5]">
            Agents discover roles, tailor your resume, and apply — you stay in control.
          </p>

          {signedOut && !signedIn ? (
            <p className="mt-4 max-w-xl text-sm font-medium text-white/75">
              You&apos;re signed out. Click <span className="text-white">Start applying</span> to sign in with Google and continue onboarding.
            </p>
          ) : null}

          <div className="mt-8 flex flex-wrap items-center gap-3">
            {!signedIn && !authOff && <GoogleSignIn next={afterSignIn} label="Start applying" />}
            {!signedIn && authOff && (
              <Link
                href={onboardingHref}
                className="inline-flex min-h-10 min-w-[160px] items-center justify-center rounded border border-transparent bg-white px-4 py-2 text-base font-normal text-black"
              >
                Start applying
              </Link>
            )}
            {signedIn && !onboardingDone && (
              <Link
                href={onboardingHref}
                className="inline-flex min-h-10 min-w-[160px] items-center justify-center rounded border border-transparent bg-white px-4 py-2 text-base font-normal text-black"
              >
                Continue setup
              </Link>
            )}
            {signedIn && onboardingDone && !hasResume && (
              <ResumeUpload redirectTo="/onboarding?resume=1" />
            )}
            {signedIn && onboardingDone && hasResume && (
              <Link
                href="/home"
                className="inline-flex min-h-10 min-w-[160px] items-center justify-center rounded border border-transparent bg-white px-4 py-2 text-base font-normal text-black"
              >
                {userName ? `Go to dashboard, ${userName.split(" ")[0]}` : "Go to dashboard"}
              </Link>
            )}
            {!signedIn && (
              <Link
                href="#how"
                className="inline-flex min-h-10 min-w-[120px] items-center justify-center rounded border border-white bg-transparent px-4 py-2 text-base font-normal text-white"
              >
                How it works
              </Link>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
