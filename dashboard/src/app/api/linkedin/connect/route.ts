import { NextResponse } from "next/server";
import {
  createLinkedInState,
  currentLinkedInUserId,
  linkedinAuthorizeUrl,
  linkedinConfigError,
} from "@/lib/linkedin";

export async function GET(request: Request) {
  const userId = await currentLinkedInUserId();
  if (!userId) {
    return NextResponse.redirect(new URL("/?linkedin=signin", request.url));
  }
  const configError = linkedinConfigError();
  if (configError) {
    return NextResponse.redirect(
      new URL(`/settings?linkedin=not_configured&reason=${encodeURIComponent(configError)}`, request.url),
    );
  }
  const { state } = createLinkedInState(userId);
  return NextResponse.redirect(linkedinAuthorizeUrl(state));
}
