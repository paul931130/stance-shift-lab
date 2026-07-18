import type { DebateRole, ExperimentGroup } from "./types.ts";

export type LogicalCallKind = "decision" | "sample" | "debate" | "adjudication";

export interface LogicalCall {
  sequence: number;
  groupSequence: number;
  group: ExperimentGroup;
  kind: LogicalCallKind;
  participant: string;
  round?: 1 | 2 | 3;
  role?: DebateRole;
  roleSwitched: boolean;
  instruction: string;
}

export const LOGICAL_CALL_COUNTS = {
  A: 1,
  B: 5,
  C: 7,
  D: 7,
} as const satisfies Record<ExperimentGroup, number>;

function debateCalls(group: "C" | "D", startSequence: number): LogicalCall[] {
  const calls: LogicalCall[] = [];
  const originalRoles: Record<string, DebateRole> = {
    "Agent-A": "Bull",
    "Agent-B": "Bear",
  };

  for (const round of [1, 2, 3] as const) {
    for (const participant of ["Agent-A", "Agent-B"] as const) {
      const shouldSwitch = group === "D" && round === 2;
      const originalRole = originalRoles[participant];
      const role: DebateRole = shouldSwitch
        ? originalRole === "Bull"
          ? "Bear"
          : "Bull"
        : originalRole;
      calls.push({
        sequence: startSequence + calls.length,
        groupSequence: calls.length + 1,
        group,
        kind: "debate",
        participant,
        round,
        role,
        roleSwitched: shouldSwitch,
        instruction:
          round === 1
            ? "提出原始立場，逐項引用證據。"
            : round === 2 && group === "D"
              ? "強制採取對方立場，提出該立場最強論據；本輪不得提前收斂。"
              : round === 2
                ? "維持固定立場，回應對方最強反證；本輪不得提前收斂。"
                : "回到原始角色，整合對方最強證據並說明仍存在的不確定性。",
      });
    }
  }

  calls.push({
    sequence: startSequence + calls.length,
    groupSequence: 7,
    group,
    kind: "adjudication",
    participant: "Adjudicator",
    roleSwitched: false,
    instruction: "六次辯論發言全部完成後，依證據帳本作出獨立裁決。",
  });
  return calls;
}

export function buildLogicalCallPlan(): readonly LogicalCall[] {
  const calls: LogicalCall[] = [
    {
      sequence: 1,
      groupSequence: 1,
      group: "A",
      kind: "decision",
      participant: "Single-LLM",
      roleSwitched: false,
      instruction: "依中立研究報告作出單次決策。",
    },
  ];

  for (let sample = 1; sample <= 5; sample += 1) {
    calls.push({
      sequence: calls.length + 1,
      groupSequence: sample,
      group: "B",
      kind: "sample",
      participant: `Sample-${sample}`,
      roleSwitched: false,
      instruction: "在相同輸入下獨立抽樣，不讀取其他樣本；最後採多數決。",
    });
  }

  calls.push(...debateCalls("C", calls.length + 1));
  calls.push(...debateCalls("D", calls.length + 1));
  assertLogicalCallPlan(calls);
  return calls;
}

export function countLogicalCalls(
  calls: readonly LogicalCall[],
): Record<ExperimentGroup, number> {
  return calls.reduce<Record<ExperimentGroup, number>>(
    (counts, call) => {
      counts[call.group] += 1;
      return counts;
    },
    { A: 0, B: 0, C: 0, D: 0 },
  );
}

export function assertLogicalCallPlan(calls: readonly LogicalCall[]): void {
  const counts = countLogicalCalls(calls);
  for (const group of ["A", "B", "C", "D"] as const) {
    if (counts[group] !== LOGICAL_CALL_COUNTS[group]) {
      throw new Error(
        `Group ${group} has ${counts[group]} logical calls; expected ${LOGICAL_CALL_COUNTS[group]}.`,
      );
    }
  }
  if (calls.length !== 20) {
    throw new Error(`A complete comparison requires 20 logical calls, got ${calls.length}.`);
  }
  calls.forEach((call, index) => {
    if (call.sequence !== index + 1) {
      throw new Error("Logical call sequence must be contiguous and one-based.");
    }
  });

  for (const group of ["C", "D"] as const) {
    const groupCalls = calls.filter((call) => call.group === group);
    if (
      groupCalls.slice(0, 6).some((call) => call.kind !== "debate") ||
      groupCalls[6]?.kind !== "adjudication"
    ) {
      throw new Error(`Group ${group} must complete six turns before adjudication.`);
    }
  }

  const groupC = calls.filter((call) => call.group === "C" && call.kind === "debate");
  if (groupC.some((call) => call.roleSwitched)) {
    throw new Error("Group C roles must remain fixed.");
  }

  const groupD = calls.filter((call) => call.group === "D" && call.kind === "debate");
  if (
    groupD.some((call) => call.roleSwitched !== (call.round === 2)) ||
    groupD.filter((call) => call.round === 2).length !== 2
  ) {
    throw new Error("Group D must switch both roles in round 2 only.");
  }
}
