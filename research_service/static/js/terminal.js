// Coordinator shell in the side column: a short rolling log of agent events.
import { $, escape, terminalStamp } from './ui.js';
import { flow } from './flow.js';

const MAX_LINES = 14;
const AGENT_NODES = {TECH: 'da-technical', FUND: 'da-fundamental', SENT: 'da-sentiment', MACRO: 'da-macro', STORE: 'snapshot', CACHE: 'snapshot'};
let events = [];

function render() {
  const output = $('agent-terminal-output');
  if (!output) return;
  output.innerHTML = events.map(item => `<div class="terminal-line ${escape(item.tone)}"><time>${escape(item.at)}</time><b>[${escape(item.agent)}]</b><span>${escape(item.message)}</span></div>`).join('')
    + '<div class="terminal-cursor" aria-hidden="true"><span>›</span><i></i></div>';
  output.scrollTop = output.scrollHeight;
}
export function resetTerminal() { events = []; render(); }
export function terminalLine(agent, message, tone = '') {
  events.push({at: terminalStamp(), agent, message, tone});
  if (events.length > MAX_LINES) events.shift();
  render();
  if (AGENT_NODES[agent]) flow.pulse(AGENT_NODES[agent]);
}
