const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

/** Minimal fetch wrapper for future API routes; no product endpoint is called yet. */
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(new URL(path, API_BASE_URL), init);
  if (!response.ok) {
    throw new ApiError("The API request could not be completed.", response.status);
  }
  return (await response.json()) as T;
}
