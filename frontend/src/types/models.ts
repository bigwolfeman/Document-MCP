/**
 * Model provider types and model selection configuration
 */

export type ModelProvider = 'openrouter' | 'google';

export interface ModelInfo {
  id: string;
  name: string;
  provider: ModelProvider;
  isFree: boolean;
  supportsThinking: boolean;
  contextLength: number;
  description?: string;
}

export interface ModelSettings {
  oracleModel: string;
  oracleProvider: ModelProvider;
  subagentModel: string;
  subagentProvider: ModelProvider;
  thinkingEnabled: boolean;
}

export interface ModelsResponse {
  models: ModelInfo[];
}
