"use client";

import Link from "next/link";
import { AsciiFluid } from "@/components/ui/ascii-fluid";
import { DitherScan } from "@/components/ui/dither-scan";
import { GoogleSignIn } from "@/components/landing/google-sign-in";
import { ResumeUpload } from "@/components/landing/resume-upload";

type Props = {
  signedIn: boolean;
  hasResume: boolean;
  userName?: string | null;
  authOff: boolean;
  next?: string;
};

export function LandingHero({ signedIn, hasResume, userName, authOff, next }: Props) {
  return (
    <div className="relative min-h-svh overflow-hidden bg-black text-white">
      {/* Full-bleed dithered highland — the visual plane of the first viewport */}
      <div className="absolute inset-0">
        <DitherScan
          src="/landing-hero.png"
          alt="Sunlit ruins of the Roman Forum under a blue sky"
          passes={4}
          duration={1400}
          pixelSize={6}
          blur={6}
          angle={45}
          loop
          theme="dark"
          colors={["#1a1208", "#ff4c00"]}
          className="!aspect-auto h-full min-h-svh w-full"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/55 to-black/25" />
      </div>

      {/* Cursor fluid sits above the image, under the copy */}
      <AsciiFluid
        cellSize={12}
        force={1}
        dissipation={0.05}
        brush={0.55}
        animate
        theme="dark"
        color="#ff4c00"
        backgroundColor="transparent"
        className="z-[1] opacity-70"
      />

      <header className="relative z-10 flex items-center justify-between px-6 py-5 md:px-10">
        <span className="font-[family-name:var(--font-landing-display)] text-xl font-medium tracking-tight md:text-2xl">
          applyforme
        </span>
        {signedIn || authOff ? (
          <Link href={hasResume ? "/home" : "/onboarding"} className="text-base font-medium underline underline-offset-4">
            Open dashboard
          </Link>
        ) : (
          <Link href="#start" className="text-base font-medium underline underline-offset-4">
            Get started
          </Link>
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

          <div className="mt-8 flex flex-wrap items-center gap-3">
            {!signedIn && !authOff && <GoogleSignIn next={next || "/onboarding"} />}
            {(signedIn || authOff) && !hasResume && <ResumeUpload />}
            {(signedIn || authOff) && hasResume && (
              <Link
                href="/home"
                className="inline-flex min-h-10 min-w-[160px] items-center justify-center rounded border border-transparent bg-white px-4 py-2 text-base font-normal text-black"
              >
                {userName ? `Go to dashboard, ${userName.split(" ")[0]}` : "Go to dashboard"}
              </Link>
            )}
            {!signedIn && !authOff && (
              <Link
                href="#how"
                className="inline-flex min-h-10 min-w-[120px] items-center justify-center rounded border border-white bg-transparent px-4 py-2 text-base font-normal text-white"
              >
                How it works
              </Link>
            )}
            {authOff && (
              <Link
                href="/home"
                className="inline-flex min-h-10 min-w-[120px] items-center justify-center rounded border border-white bg-transparent px-4 py-2 text-base font-normal text-white"
              >
                Open dashboard
              </Link>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
