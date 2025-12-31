export type SourceType = 'vault' | 'code' | 'thread';
export type StreamEventType = 'status' | 'thinking' | 'content' | 'source' | 'done' | 'error';

/**
 * Oracle API request payload
 */
export interface OracleRequest {
  question: string;
  sources?: SourceType[];
  explain?: boolean;
  max_results?: number;
}

/**
 * Retrieval result from any knowledge source
 */
export interface RetrievalResult {
  content: string;
  source_type: SourceType;
  source_path: string;
  score: number;
  metadata?: Record<string, unknown>;
}

/**
 * Stream event chunks from Oracle SSE endpoint
 */
export interface OracleStreamChunk {
  type: StreamEventType;
  message?: string;          // for status events
  content?: string;          // for content/thinking tokens
  source?: RetrievalResult;  // for source events
  tokens?: number;           // for done event
  duration_ms?: number;      // for done event
  model?: string;            // for done event
  error?: string;            // for error events
}

/**
 * Slash command definition
 */
export interface SlashCommand {
  name: string;
  description: string;
  shortcut?: string;
  handler: () => void | Promise<void>;
}

/**
 * Oracle conversation message (extends ChatMessage)
 */
export interface OracleMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  thinking?: string;         // Optional thinking/reasoning content
  sources?: RetrievalResult[];
  model?: string;
  is_error?: boolean;
}

/**
 * Oracle session settings
 */
export interface OracleSettings {
  model?: string;
  sources?: SourceType[];
  show_thinking?: boolean;
  show_sources?: boolean;
  max_results?: number;
}
