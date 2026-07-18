const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export function parseIsoDate(value: string): Date {
  if (!ISO_DATE_PATTERN.test(value)) {
    throw new TypeError(`Invalid ISO date: ${value}.`);
  }

  const parsed = new Date(`${value}T00:00:00.000Z`);
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) {
    throw new TypeError(`Invalid calendar date: ${value}.`);
  }
  return parsed;
}

export function compareIsoDates(left: string, right: string): number {
  return parseIsoDate(left).getTime() - parseIsoDate(right).getTime();
}

export function addCalendarDays(value: string, days: number): string {
  if (!Number.isInteger(days)) {
    throw new TypeError("Calendar-day offset must be an integer.");
  }
  const date = parseIsoDate(value);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function datePart(value: string): string {
  const date = value.slice(0, 10);
  parseIsoDate(date);
  return date;
}
