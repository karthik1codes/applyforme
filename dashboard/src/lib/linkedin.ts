import fs from "node:fs";
import path from "node:path";
import { auth, authDisabled } from "@/auth";
import { db } from "@/lib/db";
import { sessionUserId } from "@/lib/onboarding-gate";
import {
  LINKEDIN_SCOPES,
  buildAuthorizeUrl,
  connectFromCode,
  consumeStateRecord,
  createStateRecord,
  deleteConnectionRecord,
  getConnectionRecord,
  linkedinRedirectUri,
  refreshConnectionRecord,
  resolveLinkedInConfig,
  type LinkedInConfig,
  type LinkedInConnection,
} from "@/lib/linkedin-core";

export { LINKEDIN_SCOPES };
export type { LinkedInConnection };

const LEGACY_FILE = path.resolve(process.cwd(), "..", "data", "linkedin_credentials.json");

export type LinkedInCardData = {
  configured: boolean;
  configError: string | null;
  signedIn: boolean;
  connection: LinkedInConnection | null;
  legacyFileExists: boolean;
  redirectUri: string;
};

export { linkedinRedirectUri };

export function linkedinConfigError(env: NodeJS.ProcessEnv = process.env): string | null {
  return resolveLinkedInConfig(env).error;
}

export function linkedinConfigured(): boolean {
  return linkedinConfigError() === null;
}

function configOrThrow(): LinkedInConfig {
  const { config, error } = resolveLinkedInConfig();
  if (!config) throw new Error(error || "LinkedIn is not configured");
  return config;
}

export async function currentLinkedInUserId(): Promise<string | null> {
  if (authDisabled()) return "local";
  const session = await auth();
  if (!session?.user?.email) return null;
  return sessionUserId(session);
}

export function createLinkedInState(userId: string): { state: string } {
  return createStateRecord(db(), userId);
}

export function consumeLinkedInState(state: string, userId: string): boolean {
  return consumeStateRecord(db(), state, userId);
}

export function linkedinAuthorizeUrl(state: string): string {
  const config = configOrThrow();
  return buildAuthorizeUrl({
    clientId: config.clientId,
    redirectUri: config.redirectUri,
    state,
  });
}

export async function connectLinkedInFromCode(
  userId: string,
  code: string,
): Promise<LinkedInConnection> {
  return connectFromCode(db(), userId, configOrThrow(), code);
}

export function getLinkedInConnection(userId: string): LinkedInConnection | null {
  return getConnectionRecord(db(), userId);
}

export async function refreshLinkedInConnection(userId: string): Promise<LinkedInConnection> {
  return refreshConnectionRecord(db(), userId, configOrThrow());
}

export function disconnectLinkedIn(userId: string): void {
  deleteConnectionRecord(db(), userId);
}

export function legacyLinkedInFileExists(): boolean {
  try {
    return fs.existsSync(LEGACY_FILE);
  } catch {
    return false;
  }
}

/**
 * Remove the old plaintext email/password file. It is never read, logged, or
 * migrated: a password cannot be turned into an OAuth connection.
 */
export function deleteLegacyLinkedInFile(): boolean {
  try {
    if (!fs.existsSync(LEGACY_FILE)) return false;
    fs.unlinkSync(LEGACY_FILE);
    return true;
  } catch {
    return false;
  }
}

export async function linkedInCardData(): Promise<LinkedInCardData> {
  const configError = linkedinConfigError();
  const userId = await currentLinkedInUserId();
  return {
    configured: configError === null,
    configError,
    signedIn: !!userId,
    connection: userId ? getLinkedInConnection(userId) : null,
    legacyFileExists: legacyLinkedInFileExists(),
    redirectUri: linkedinRedirectUri(),
  };
}
