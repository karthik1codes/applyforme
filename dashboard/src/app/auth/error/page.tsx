import Link from "next/link";

export const dynamic = "force-dynamic";

function authBase() {
  return (process.env.AUTH_URL || process.env.NEXTAUTH_URL || process.env.APP_URL || "http://localhost:3000").replace(
    /\/$/,
    "",
  );
}

const MESSAGES: Record<string, string> = {
  Configuration:
    "Google sign-in could not finish (often a lost login cookie behind the tunnel, or AUTH_URL / Google redirect URI mismatch). Clear site cookies for this hostname and try Start applying again.",
  AccessDenied: "Google denied access for this account.",
  Verification: "The sign-in link expired. Start again from the landing page.",
  OAuthCallback: "Google returned an error during callback. Check the redirect URI in Google Cloud Console.",
  Default: "Sign-in failed. Try again from the landing page.",
};

export default async function AuthErrorPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const key = error && MESSAGES[error] ? error : "Default";
  const detail = MESSAGES[key];
  const base = authBase();
  const redirectUri = `${base}/api/auth/callback/google`;

  return (
    <main className="flex min-h-svh flex-col items-center justify-center bg-black px-6 text-white">
      <div className="w-full max-w-md rounded-2xl border border-white/15 bg-zinc-900 px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">Sign-in error</h1>
        <p className="mt-3 text-sm text-white/75">{detail}</p>
        {error ? <p className="mt-2 font-mono text-xs text-white/45">code: {error}</p> : null}
        <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-50">
          <p className="font-medium text-amber-100">For Error 400: redirect_uri_mismatch</p>
          <p className="mt-2 text-white/80">In Google Cloud Console → Credentials → your OAuth client, add exactly:</p>
          <p className="mt-2 break-all font-mono text-[11px] text-white">{redirectUri}</p>
          <p className="mt-2 text-white/70">Authorized JavaScript origin:</p>
          <p className="mt-1 break-all font-mono text-[11px] text-white">{base}</p>
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href="/"
            className="inline-flex min-h-10 items-center justify-center rounded bg-white px-4 text-sm font-medium text-black"
          >
            Back to start
          </Link>
          <a
            href={`/api/auth/signin/google?callbackUrl=${encodeURIComponent("/onboarding")}`}
            className="inline-flex min-h-10 items-center justify-center rounded border border-white/30 px-4 text-sm font-medium"
          >
            Try Google again
          </a>
        </div>
      </div>
    </main>
  );
}
