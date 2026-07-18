import { getChatGPTUser } from "@/app/chatgpt-auth";
import { getRuntimeBindings } from "@/db";
import { ApiError } from "./http";

export type ApiOwner = {
  hash: string;
  displayName: string;
};

export async function requireApiOwner(): Promise<ApiOwner> {
  const user = await getChatGPTUser();
  if (!user) {
    throw new ApiError(401, "AUTH_REQUIRED", "請先使用 ChatGPT 登入。", {
      signInPath: "/signin-with-chatgpt?return_to=%2Flab",
    });
  }

  return {
    hash: await hashOwnerEmail(user.email),
    displayName: user.displayName,
  };
}

async function hashOwnerEmail(email: string): Promise<string> {
  const normalized = email.trim().toLowerCase();
  const secret = getRuntimeBindings().OWNER_KEY_PEPPER;
  const encoder = new TextEncoder();

  if (secret) {
    const key = await crypto.subtle.importKey(
      "raw",
      encoder.encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    return toHex(await crypto.subtle.sign("HMAC", key, encoder.encode(normalized)));
  }

  // SIWC headers are dispatcher-owned, so this still forms a sound ownership
  // boundary. Configure OWNER_KEY_PEPPER in hosted environments to add a
  // private pepper and prevent offline enumeration of stored hashes.
  return toHex(
    await crypto.subtle.digest(
      "SHA-256",
      encoder.encode(`stance-shift-lab:owner:v1:${normalized}`),
    ),
  );
}

function toHex(value: ArrayBuffer): string {
  return [...new Uint8Array(value)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
