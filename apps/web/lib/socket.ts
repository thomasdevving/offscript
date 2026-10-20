import { wsUrl } from "./config";

// Messages are validated loosely on the client; their shapes are defined by the backend
// (apps/api/app/services/live.py). Typed fields used by the store are listed here.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type ServerMessage = { type: string; [k: string]: any };

export class MatchSocket {
  private ws: WebSocket | null = null;
  private closed = false;
  private retry = 0;
  private queue: string[] = [];

  constructor(
    private matchId: string,
    private autoAnalyze: boolean,
    private onMessage: (m: ServerMessage) => void,
    private onState: (s: "connecting" | "open" | "closed") => void,
  ) {}

  connect(): void {
    this.onState("connecting");
    const ws = new WebSocket(wsUrl(`/ws/matches/${this.matchId}?auto_analyze=${this.autoAnalyze}`));
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.onState("open");
      for (const m of this.queue.splice(0)) ws.send(m);
    };
    ws.onmessage = (ev) => {
      try {
        this.onMessage(JSON.parse(ev.data as string));
      } catch (e) {
        console.warn("bad message", e);
      }
    };
    ws.onclose = () => {
      this.onState("closed");
      if (!this.closed) {
        this.retry += 1;
        setTimeout(() => !this.closed && this.connect(), Math.min(8000, 500 * 2 ** this.retry));
      }
    };
  }

  send(msg: Record<string, unknown>): void {
    const text = JSON.stringify(msg);
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(text);
    else this.queue.push(text);
  }

  close(): void {
    this.closed = true;
    this.ws?.close();
  }
}
