import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";

/** Set AUTH_DISABLED=1 to skip Google (local single-user). Also true when Google keys are missing. */
export const authDisabled = () => {
  const flag = (process.env.AUTH_DISABLED || "").trim().toLowerCase();
  if (flag === "1" || flag === "true" || flag === "yes" || flag === "on") return true;
  return !process.env.GOOGLE_CLIENT_ID || !process.env.GOOGLE_CLIENT_SECRET;
};

const googleReady =
  !authDisabled() && !!(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET);

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    ...(googleReady
      ? [
          Google({
            clientId: process.env.GOOGLE_CLIENT_ID!,
            clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
            // Explicit OIDC issuer — openid-client validates callback `iss` against this.
            issuer: "https://accounts.google.com",
            authorization: {
              params: {
                prompt: "select_account",
                access_type: "online",
                response_type: "code",
              },
            },
          }),
        ]
      : [
          Credentials({
            id: "local",
            name: "Local",
            credentials: {},
            authorize: async () => ({ id: "local", name: "Local user", email: "local@localhost" }),
          }),
        ]),
  ],
  pages: {
    signIn: "/",
    error: "/auth/error",
  },
  session: { strategy: "jwt" },
  callbacks: {
    // Allow every Google account (gmail.com, googlemail.com, Workspace, etc.). No domain allowlist.
    async signIn({ account }) {
      if (account?.provider === "google") return true;
      if (account?.provider === "local") return true;
      return true;
    },
    jwt({ token, user }) {
      if (user?.id) token.sub = user.id;
      return token;
    },
    session({ session, token }) {
      if (session.user && token.sub) {
        (session.user as { id?: string }).id = token.sub;
      }
      return session;
    },
  },
  // Let Auth.js pick secure cookie defaults from AUTH_URL (https → Secure).
  // Custom __Host- cookies break behind Cloudflare tunnels (CSRF never sticks).
  trustHost: true,
  secret: process.env.AUTH_SECRET || process.env.NEXTAUTH_SECRET || "dev-only-change-me",
});
