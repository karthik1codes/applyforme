import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";

/** Set AUTH_DISABLED=1 to skip Google (local single-user). Also true when Google keys are missing. */
export const authDisabled = () => process.env.AUTH_DISABLED === "1" || !process.env.GOOGLE_CLIENT_ID;

const googleReady = !!(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET);

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    ...(googleReady
      ? [
          Google({
            clientId: process.env.GOOGLE_CLIENT_ID!,
            clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
          }),
        ]
      : [
          // Dev-only fallback so the app boots without Google keys.
          Credentials({
            id: "local",
            name: "Local",
            credentials: {},
            authorize: async () => ({ id: "local", name: "Local user", email: "local@localhost" }),
          }),
        ]),
  ],
  pages: { signIn: "/" },
  session: { strategy: "jwt" },
  callbacks: {
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
  trustHost: true,
  secret: process.env.AUTH_SECRET || process.env.NEXTAUTH_SECRET || "dev-only-change-me",
});