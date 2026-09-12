export class ProviderError extends Error {
  constructor(
    message: string,
    readonly httpStatus: number | null,
    readonly responseExcerpt: string | null = null,
    readonly code = "PROVIDER_ERROR",
  ) {
    super(message);
    this.name = "ProviderError";
  }
}
