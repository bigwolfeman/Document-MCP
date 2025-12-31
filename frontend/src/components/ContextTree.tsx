/**
 * ContextTree Component
 * Visual tree display for Oracle conversation branches
 *
 * Features:
 * - Collapsible branches
 * - Current node (HEAD) indicator
 * - Checkpoint star marker
 * - Labels display
 * - Right-click context menu for actions
 * - Node count indicator
 */
import { useState, useMemo } from 'react';
import {
  ChevronRight,
  ChevronDown,
  Star,
  GitBranch,
  Plus,
  Scissors,
  Tag,
  CheckCircle2,
  Circle,
  Trash2,
  MoreVertical,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import type { ContextNode, ContextTreeData } from '@/types/context';

export interface ContextTreeProps {
  trees: ContextTreeData[];
  activeTreeId: string | null;
  onCheckout: (nodeId: string) => void;
  onNewRoot: () => void;
  onLabel: (nodeId: string, label: string) => void;
  onCheckpoint: (nodeId: string, isCheckpoint: boolean) => void;
  onPrune: (rootId: string) => void;
  onDeleteTree: (rootId: string) => void;
  onSelectTree: (rootId: string) => void;
  isLoading?: boolean;
}

interface TreeNodeDisplayProps {
  node: ContextNode;
  children: ContextNode[];
  allNodes: ContextNode[];
  currentNodeId: string;
  depth: number;
  onCheckout: (nodeId: string) => void;
  onLabel: (nodeId: string, label: string) => void;
  onCheckpoint: (nodeId: string, isCheckpoint: boolean) => void;
}

/**
 * Build a tree structure from flat node list
 */
function buildNodeTree(nodes: ContextNode[]): Map<string | null, ContextNode[]> {
  const childrenMap = new Map<string | null, ContextNode[]>();

  for (const node of nodes) {
    const parentId = node.parent_id;
    if (!childrenMap.has(parentId)) {
      childrenMap.set(parentId, []);
    }
    childrenMap.get(parentId)!.push(node);
  }

  // Sort children by created_at
  for (const [, children] of childrenMap) {
    children.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  }

  return childrenMap;
}

/**
 * Format timestamp for display
 */
function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Truncate text for display
 */
function truncateText(text: string, maxLength: number = 30): string {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength - 3) + '...';
}

/**
 * Individual tree node display component
 */
function TreeNodeDisplay({
  node,
  children,
  allNodes,
  currentNodeId,
  depth,
  onCheckout,
  onLabel,
  onCheckpoint,
}: TreeNodeDisplayProps) {
  const [isOpen, setIsOpen] = useState(depth < 2);
  const [isLabelDialogOpen, setIsLabelDialogOpen] = useState(false);
  const [labelInput, setLabelInput] = useState(node.label || '');

  const isCurrent = node.id === currentNodeId;
  const hasChildren = children.length > 0;
  const nodeChildren = useMemo(() => {
    const childrenMap = buildNodeTree(allNodes);
    return childrenMap.get(node.id) || [];
  }, [allNodes, node.id]);

  const handleLabelSubmit = () => {
    onLabel(node.id, labelInput);
    setIsLabelDialogOpen(false);
  };

  const displayText = node.label || truncateText(node.question || 'Root');

  return (
    <div className="relative">
      {/* Connection line */}
      {depth > 0 && (
        <div
          className="absolute left-0 top-0 h-4 border-l-2 border-b-2 border-muted-foreground/30 rounded-bl"
          style={{
            width: '12px',
            marginLeft: `${(depth - 1) * 20 + 8}px`,
          }}
        />
      )}

      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <div
          className={cn(
            "group flex items-center gap-1 py-1 px-2 rounded-md hover:bg-accent/50 transition-colors cursor-pointer",
            isCurrent && "bg-accent ring-1 ring-primary/50"
          )}
          style={{ marginLeft: `${depth * 20}px` }}
          onClick={() => onCheckout(node.id)}
        >
          {/* Expand/collapse toggle */}
          {hasChildren ? (
            <CollapsibleTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-5 w-5 p-0">
                {isOpen ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
              </Button>
            </CollapsibleTrigger>
          ) : (
            <span className="w-5" />
          )}

          {/* Node indicator */}
          {isCurrent ? (
            <CheckCircle2 className="h-4 w-4 text-primary shrink-0" />
          ) : (
            <Circle className="h-4 w-4 text-muted-foreground/50 shrink-0" />
          )}

          {/* Checkpoint star */}
          {node.is_checkpoint && (
            <Star className="h-3 w-3 text-yellow-500 fill-yellow-500 shrink-0" />
          )}

          {/* Node label/content */}
          <span className={cn(
            "text-sm truncate flex-1",
            isCurrent && "font-medium"
          )}>
            {displayText}
          </span>

          {/* Current indicator */}
          {isCurrent && (
            <Badge variant="outline" className="text-xs py-0 px-1 h-4">
              HEAD
            </Badge>
          )}

          {/* Timestamp */}
          <span className="text-xs text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
            {formatTimestamp(node.created_at)}
          </span>

          {/* Context menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <MoreVertical className="h-3 w-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem onClick={() => onCheckout(node.id)}>
                <GitBranch className="h-4 w-4 mr-2" />
                Checkout
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setIsLabelDialogOpen(true)}>
                <Tag className="h-4 w-4 mr-2" />
                {node.label ? 'Edit Label' : 'Add Label'}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => onCheckpoint(node.id, !node.is_checkpoint)}>
                <Star className={cn("h-4 w-4 mr-2", node.is_checkpoint && "fill-yellow-500")} />
                {node.is_checkpoint ? 'Remove Checkpoint' : 'Set Checkpoint'}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Children */}
        {hasChildren && (
          <CollapsibleContent>
            {nodeChildren.map((child) => (
              <TreeNodeDisplay
                key={child.id}
                node={child}
                children={allNodes.filter(n => n.parent_id === child.id)}
                allNodes={allNodes}
                currentNodeId={currentNodeId}
                depth={depth + 1}
                onCheckout={onCheckout}
                onLabel={onLabel}
                onCheckpoint={onCheckpoint}
              />
            ))}
          </CollapsibleContent>
        )}
      </Collapsible>

      {/* Label dialog */}
      <Dialog open={isLabelDialogOpen} onOpenChange={setIsLabelDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Label Node</DialogTitle>
            <DialogDescription>
              Add a descriptive label to this conversation point for easy reference.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Input
              placeholder="e.g., Setup complete, Working approach"
              value={labelInput}
              onChange={(e) => setLabelInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleLabelSubmit()}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsLabelDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleLabelSubmit}>
              Save Label
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * Single tree display with header
 */
function TreeDisplay({
  treeData,
  isActive,
  onCheckout,
  onLabel,
  onCheckpoint,
  onPrune,
  onDeleteTree,
  onSelectTree,
}: {
  treeData: ContextTreeData;
  isActive: boolean;
  onCheckout: (nodeId: string) => void;
  onLabel: (nodeId: string, label: string) => void;
  onCheckpoint: (nodeId: string, isCheckpoint: boolean) => void;
  onPrune: (rootId: string) => void;
  onDeleteTree: (rootId: string) => void;
  onSelectTree: (rootId: string) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(isActive);
  const { tree, nodes } = treeData;

  const rootNode = nodes.find(n => n.is_root);
  const rootChildren = nodes.filter(n => n.parent_id === (rootNode?.id || null));

  const warningLevel = tree.node_count / tree.max_nodes;
  const showWarning = warningLevel >= 0.8;

  return (
    <div className={cn(
      "border rounded-lg mb-2",
      isActive ? "border-primary/50 bg-accent/20" : "border-border"
    )}>
      {/* Tree header */}
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <div className="flex items-center justify-between p-2">
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="flex-1 justify-start gap-2 h-8">
              {isExpanded ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
              <GitBranch className="h-4 w-4" />
              <span className="font-medium truncate">
                {tree.label || `Tree ${tree.root_id.slice(0, 8)}`}
              </span>
              {isActive && (
                <Badge variant="default" className="text-xs py-0 px-1 h-4 ml-1">
                  Active
                </Badge>
              )}
            </Button>
          </CollapsibleTrigger>

          <div className="flex items-center gap-2">
            {/* Node count */}
            <Badge
              variant={showWarning ? "destructive" : "secondary"}
              className="text-xs"
            >
              {tree.node_count}/{tree.max_nodes}
            </Badge>

            {/* Tree actions */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-6 w-6">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {!isActive && (
                  <DropdownMenuItem onClick={() => onSelectTree(tree.root_id)}>
                    <CheckCircle2 className="h-4 w-4 mr-2" />
                    Set Active
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem onClick={() => onPrune(tree.root_id)}>
                  <Scissors className="h-4 w-4 mr-2" />
                  Prune Old Nodes
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => onDeleteTree(tree.root_id)}
                  className="text-destructive"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete Tree
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Warning banner */}
        {showWarning && (
          <div className="px-2 pb-2">
            <div className="text-xs text-yellow-600 dark:text-yellow-400 bg-yellow-100 dark:bg-yellow-900/30 rounded px-2 py-1">
              Approaching limit. Consider pruning or starting a new tree.
            </div>
          </div>
        )}

        {/* Tree nodes */}
        <CollapsibleContent>
          <div className="px-2 pb-2">
            {rootNode && (
              <TreeNodeDisplay
                node={rootNode}
                children={rootChildren}
                allNodes={nodes}
                currentNodeId={tree.current_node_id}
                depth={0}
                onCheckout={onCheckout}
                onLabel={onLabel}
                onCheckpoint={onCheckpoint}
              />
            )}
            {!rootNode && nodes.length === 0 && (
              <div className="text-sm text-muted-foreground text-center py-4">
                No conversation nodes yet
              </div>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

/**
 * Main ContextTree component
 */
export function ContextTree({
  trees,
  activeTreeId,
  onCheckout,
  onNewRoot,
  onLabel,
  onCheckpoint,
  onPrune,
  onDeleteTree,
  onSelectTree,
  isLoading,
}: ContextTreeProps) {
  // Sort trees: active first, then by most recent
  const sortedTrees = useMemo(() => {
    return [...trees].sort((a, b) => {
      if (a.tree.root_id === activeTreeId) return -1;
      if (b.tree.root_id === activeTreeId) return 1;
      // Sort by most recent node activity
      const aLatest = Math.max(...a.nodes.map(n => new Date(n.created_at).getTime()));
      const bLatest = Math.max(...b.nodes.map(n => new Date(n.created_at).getTime()));
      return bLatest - aLatest;
    });
  }, [trees, activeTreeId]);

  if (isLoading) {
    return (
      <div className="p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-8 bg-muted rounded" />
          <div className="h-24 bg-muted rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-3 border-b border-border">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold text-sm">Context Trees</h3>
          <Button
            variant="outline"
            size="sm"
            onClick={onNewRoot}
            className="h-7 text-xs"
          >
            <Plus className="h-3 w-3 mr-1" />
            New Tree
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Manage conversation branches and checkpoints
        </p>
      </div>

      {/* Tree list */}
      <ScrollArea className="flex-1">
        <div className="p-2">
          {sortedTrees.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <GitBranch className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No context trees yet</p>
              <p className="text-xs mt-1">Start a conversation to create one</p>
            </div>
          ) : (
            sortedTrees.map((treeData) => (
              <TreeDisplay
                key={treeData.tree.root_id}
                treeData={treeData}
                isActive={treeData.tree.root_id === activeTreeId}
                onCheckout={onCheckout}
                onLabel={onLabel}
                onCheckpoint={onCheckpoint}
                onPrune={onPrune}
                onDeleteTree={onDeleteTree}
                onSelectTree={onSelectTree}
              />
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
