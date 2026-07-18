// @ts-expect-error Node's native type-strip runner requires explicit .ts specifiers.
import { compareIsoDates, datePart, parseIsoDate } from "./date.ts";
import type { EvidenceItem, ResearchDomain } from "./types.ts";

export type EvidenceIssueCode =
  | "duplicate_evidence_id"
  | "analysis_date_mismatch"
  | "invalid_published_at"
  | "invalid_available_at"
  | "published_after_available"
  | "future_leakage"
  | "invalid_citation"
  | "missing_license"
  | "invalid_uncertainty"
  | "missing_claim"
  | "checksum_missing";

export interface EvidenceIssue {
  evidenceId: string;
  code: EvidenceIssueCode;
  message: string;
}

export interface EvidenceAudit {
  analysisDate: string;
  total: number;
  valid: number;
  passRate: number;
  validDomains: readonly ResearchDomain[];
  issues: readonly EvidenceIssue[];
  hasFutureLeakage: boolean;
  hasCriticalMetadataIssue: boolean;
}

export class FutureLeakageError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FutureLeakageError";
  }
}

function isValidCitation(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function issue(
  evidenceId: string,
  code: EvidenceIssueCode,
  message: string,
): EvidenceIssue {
  return { evidenceId, code, message };
}

export function auditEvidence(
  evidence: readonly EvidenceItem[],
  analysisDate: string,
): EvidenceAudit {
  parseIsoDate(analysisDate);
  const issues: EvidenceIssue[] = [];
  const issuesByItem = new Map<string, number>();
  const ids = new Set<string>();

  const record = (entry: EvidenceIssue) => {
    issues.push(entry);
    issuesByItem.set(entry.evidenceId, (issuesByItem.get(entry.evidenceId) ?? 0) + 1);
  };

  for (const item of evidence) {
    if (ids.has(item.evidenceId)) {
      record(
        issue(item.evidenceId, "duplicate_evidence_id", "Evidence IDs must be unique."),
      );
    }
    ids.add(item.evidenceId);

    if (item.analysisDate !== analysisDate) {
      record(
        issue(
          item.evidenceId,
          "analysis_date_mismatch",
          `Evidence belongs to ${item.analysisDate}, not ${analysisDate}.`,
        ),
      );
    }

    let publishedDate: string | undefined;
    let availableDate: string | undefined;
    try {
      publishedDate = datePart(item.publishedAt);
    } catch {
      record(
        issue(item.evidenceId, "invalid_published_at", "publishedAt is not a valid date."),
      );
    }
    try {
      availableDate = datePart(item.availableAt);
    } catch {
      record(
        issue(item.evidenceId, "invalid_available_at", "availableAt is not a valid date."),
      );
    }

    if (
      publishedDate &&
      availableDate &&
      compareIsoDates(publishedDate, availableDate) > 0
    ) {
      record(
        issue(
          item.evidenceId,
          "published_after_available",
          "Evidence cannot be available before it is published.",
        ),
      );
    }
    if (availableDate && compareIsoDates(availableDate, analysisDate) > 0) {
      record(
        issue(
          item.evidenceId,
          "future_leakage",
          `${item.availableAt} is later than the ${analysisDate} decision boundary.`,
        ),
      );
    }
    if (!isValidCitation(item.sourceUrl)) {
      record(
        issue(item.evidenceId, "invalid_citation", "sourceUrl must be an HTTP(S) URL."),
      );
    }
    if (!item.license.trim()) {
      record(issue(item.evidenceId, "missing_license", "Evidence needs a license label."));
    }
    if (
      !Number.isFinite(item.uncertainty) ||
      item.uncertainty < 0 ||
      item.uncertainty > 1
    ) {
      record(
        issue(item.evidenceId, "invalid_uncertainty", "uncertainty must be between 0 and 1."),
      );
    }
    if (!item.claim.trim()) {
      record(issue(item.evidenceId, "missing_claim", "Evidence claim is empty."));
    }
    if (!item.checksum.trim()) {
      record(issue(item.evidenceId, "checksum_missing", "Evidence checksum is empty."));
    }
  }

  const validItems = evidence.filter((item) => !issuesByItem.has(item.evidenceId));
  const validDomains = [...new Set(validItems.map((item) => item.domain))].sort();
  const criticalCodes = new Set<EvidenceIssueCode>([
    "analysis_date_mismatch",
    "invalid_published_at",
    "invalid_available_at",
    "published_after_available",
    "future_leakage",
    "invalid_citation",
    "missing_license",
  ]);

  return {
    analysisDate,
    total: evidence.length,
    valid: validItems.length,
    passRate: evidence.length === 0 ? 0 : validItems.length / evidence.length,
    validDomains,
    issues,
    hasFutureLeakage: issues.some((item) => item.code === "future_leakage"),
    hasCriticalMetadataIssue: issues.some((item) => criticalCodes.has(item.code)),
  };
}

export function assertEvidenceAvailable(
  evidence: readonly EvidenceItem[],
  analysisDate: string,
): void {
  const audit = auditEvidence(evidence, analysisDate);
  const boundaryIssues = audit.issues.filter((item) =>
    [
      "analysis_date_mismatch",
      "invalid_published_at",
      "invalid_available_at",
      "published_after_available",
      "future_leakage",
    ].includes(item.code),
  );
  if (boundaryIssues.length > 0) {
    throw new FutureLeakageError(
      `Evidence boundary rejected: ${boundaryIssues.map((item) => `${item.evidenceId}:${item.code}`).join(", ")}.`,
    );
  }
}
