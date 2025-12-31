/**
 * Context Tree Types for Oracle conversation branching
 * Matches backend models for context tree management
 */

/**
 * A single node in the context tree
 */
export interface ContextNode {
  id: string;
  root_id: string;
  parent_id: string | null;
  created_at: string;
  question: string;
  answer: string;
  tokens_used: number;
  label: string | null;
  is_checkpoint: boolean;
  is_root: boolean;
}

/**
 * A context tree with metadata
 */
export interface ContextTree {
  root_id: string;
  current_node_id: string;
  node_count: number;
  max_nodes: number;
  label: string | null;
}

/**
 * Full tree data with nodes for visualization
 */
export interface ContextTreeData {
  tree: ContextTree;
  nodes: ContextNode[];
}

/**
 * Response from getting all context trees
 */
export interface ContextTreesResponse {
  trees: ContextTreeData[];
  active_tree_id: string | null;
}

/**
 * Request to create a new context tree
 */
export interface CreateTreeRequest {
  label?: string;
}

/**
 * Request to label a node
 */
export interface LabelNodeRequest {
  label: string;
}

/**
 * Request to set checkpoint status
 */
export interface SetCheckpointRequest {
  is_checkpoint: boolean;
}

/**
 * Response from pruning a tree
 */
export interface PruneResponse {
  pruned: number;
  remaining: number;
}

/**
 * Context settings stored in user preferences
 */
export interface ContextSettings {
  max_context_nodes: number;
}
