/** The experiment universe fixed by the project report. */
export const SUPPORTED_TICKERS = [
  "AAPL",
  "NVDA",
  "GOOGL",
  "MSFT",
  "AMZN",
  "JPM",
  "MCD",
  "LLY",
  "ASTS",
  "GE",
] as const;

export type SupportedTicker = (typeof SUPPORTED_TICKERS)[number];

/**
 * Calendar-quarter anchors used by v1.  They are deliberately explicit so a
 * run cannot silently drift to a different sampling calendar.
 */
export const QUARTERLY_ANALYSIS_DATES = [
  "2021-03-31",
  "2021-06-30",
  "2021-09-30",
  "2021-12-31",
  "2022-03-31",
  "2022-06-30",
  "2022-09-30",
  "2022-12-31",
  "2023-03-31",
  "2023-06-30",
  "2023-09-30",
  "2023-12-31",
  "2024-03-31",
  "2024-06-30",
  "2024-09-30",
  "2024-12-31",
  "2025-03-31",
  "2025-06-30",
  "2025-09-30",
  "2025-12-31",
] as const;

export type QuarterlyAnalysisDate = (typeof QUARTERLY_ANALYSIS_DATES)[number];

export interface ExperimentSelection {
  ticker: SupportedTicker;
  analysisDate: QuarterlyAnalysisDate;
}

export function isSupportedTicker(value: string): value is SupportedTicker {
  return (SUPPORTED_TICKERS as readonly string[]).includes(value.toUpperCase());
}

export function isQuarterlyAnalysisDate(
  value: string,
): value is QuarterlyAnalysisDate {
  return (QUARTERLY_ANALYSIS_DATES as readonly string[]).includes(value);
}

export function assertExperimentSelection(
  ticker: string,
  analysisDate: string,
): asserts ticker is SupportedTicker {
  if (!isSupportedTicker(ticker)) {
    throw new RangeError(
      `Unsupported ticker ${ticker}. Expected one of: ${SUPPORTED_TICKERS.join(", ")}.`,
    );
  }

  if (!isQuarterlyAnalysisDate(analysisDate)) {
    throw new RangeError(
      `Unsupported analysis date ${analysisDate}. Use a 2021-2025 calendar-quarter anchor.`,
    );
  }
}

export function normalizeExperimentSelection(
  ticker: string,
  analysisDate: string,
): ExperimentSelection {
  const normalizedTicker = ticker.trim().toUpperCase();
  assertExperimentSelection(normalizedTicker, analysisDate);
  return {
    ticker: normalizedTicker,
    analysisDate: analysisDate as QuarterlyAnalysisDate,
  };
}
