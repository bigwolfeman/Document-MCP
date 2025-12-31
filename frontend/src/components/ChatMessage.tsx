import type { ChatMessage as ChatMessageType } from '@/types/rag';
import type { OracleMessage } from '@/types/oracle';
import { cn } from '@/lib/utils';
import { User, Bot, FilePlus, Edit, RefreshCw, ChevronDown, ChevronUp, Brain, FileCode, BookOpen, MessageSquare } from 'lucide-react';
import { SourceList } from './SourceList';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { useState } from 'react';

interface ChatMessageProps {
  message: ChatMessageType | OracleMessage;
  onSourceClick: (path: string) => void;
  onRefreshNeeded?: () => void;
  showThinking?: boolean;
  showSources?: boolean;
}

export function ChatMessage({
  message,
  onSourceClick,
  onRefreshNeeded,
  showThinking = true,
  showSources = true,
}: ChatMessageProps) {
  const isUser = message.role === 'user';
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [thinkingExpanded, setThinkingExpanded] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      console.log('[ChatMessage] Manual refresh triggered');
      // Trigger the same refresh mechanism as automatic refresh
      if (onRefreshNeeded) {
        await onRefreshNeeded();
        console.log('[ChatMessage] Refresh completed');
      } else {
        console.error('[ChatMessage] onRefreshNeeded is undefined');
      }
    } catch (err) {
      console.error('[ChatMessage] Refresh failed:', err);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Type guard to check if message is OracleMessage
  const isOracleMessage = (msg: ChatMessageType | OracleMessage): msg is OracleMessage => {
    return 'thinking' in msg || 'model' in msg;
  };

  const oracleMsg = isOracleMessage(message) ? message : null;

  // Get source icon based on source type
  const getSourceIcon = (sourceType: string) => {
    switch (sourceType) {
      case 'vault':
        return <BookOpen className="h-3 w-3" />;
      case 'code':
        return <FileCode className="h-3 w-3" />;
      case 'thread':
      case 'threads':
        return <MessageSquare className="h-3 w-3" />;
      default:
        return <FileCode className="h-3 w-3" />;
    }
  };

  return (
    <div className={cn("flex gap-3 p-4", isUser ? "bg-transparent" : "bg-muted/30")}>
      <div className={cn(
        "h-8 w-8 rounded-full flex items-center justify-center flex-shrink-0",
        isUser ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground"
      )}>
        {isUser ? <User className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
      </div>

      <div className="flex-1 space-y-2 overflow-hidden">
        {/* Thinking Section (Oracle only) */}
        {!isUser && oracleMsg && oracleMsg.thinking && showThinking && (
          <div className="border border-border rounded-lg overflow-hidden bg-muted/20">
            <button
              onClick={() => setThinkingExpanded(!thinkingExpanded)}
              className="flex items-center gap-2 w-full px-3 py-2 hover:bg-muted/40 transition-colors"
            >
              <Brain className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium text-muted-foreground flex-1 text-left">
                Thinking...
              </span>
              {thinkingExpanded ? (
                <ChevronUp className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
            {thinkingExpanded && (
              <div className="px-3 py-2 border-t border-border">
                <div className="prose dark:prose-invert prose-sm max-w-none text-muted-foreground whitespace-pre-wrap">
                  {oracleMsg.thinking}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Main Content */}
        <div className={cn(
          "prose dark:prose-invert text-sm max-w-none whitespace-pre-wrap",
          message.is_error && "text-destructive"
        )}>
          {message.content || (isUser ? '' : '...')}
        </div>

        {/* Model Badge */}
        {!isUser && oracleMsg?.model && (
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              {oracleMsg.model}
            </Badge>
          </div>
        )}

        {/* Notes Written (RAG legacy) */}
        {!isUser && 'notes_written' in message && message.notes_written && message.notes_written.length > 0 && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              {message.notes_written.map((note, i) => (
                <button
                  key={i}
                  onClick={() => onSourceClick(note.path)}
                  className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-green-500/10 text-green-600 dark:text-green-400 border border-green-500/20 hover:bg-green-500/20 text-xs transition-colors"
                >
                  {note.action === 'created' ? <FilePlus className="h-3 w-3" /> : <Edit className="h-3 w-3" />}
                  <span className="font-medium">
                    {note.action === 'created' ? 'Created' : 'Updated'}: {note.title}
                  </span>
                </button>
              ))}
            </div>
            <Button
              onClick={handleRefresh}
              disabled={isRefreshing}
              size="sm"
              variant="outline"
              className="text-xs h-7"
            >
              <RefreshCw className={cn("h-3 w-3 mr-1.5", isRefreshing && "animate-spin")} />
              {isRefreshing ? 'Refreshing...' : 'Refresh Views'}
            </Button>
          </div>
        )}

        {/* Oracle Sources */}
        {!isUser && showSources && oracleMsg?.sources && oracleMsg.sources.length > 0 && (
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground">Sources</div>
            <div className="flex flex-wrap gap-2">
              {oracleMsg.sources.map((source, i) => (
                <button
                  key={i}
                  onClick={() => onSourceClick(source.source_path)}
                  className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 text-xs transition-colors group"
                  title={`${source.source_type}: ${source.source_path} (score: ${source.score.toFixed(3)})`}
                >
                  {getSourceIcon(source.source_type)}
                  <span className="font-medium">{source.source_type}</span>
                  <span className="text-muted-foreground group-hover:text-blue-600 dark:group-hover:text-blue-400">
                    {source.source_path.split('/').pop()}
                  </span>
                  <Badge variant="secondary" className="text-xs px-1 py-0">
                    {source.score.toFixed(2)}
                  </Badge>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Legacy RAG Sources */}
        {!isUser && showSources && !oracleMsg && message.sources && (
          <SourceList sources={message.sources} onSourceClick={onSourceClick} />
        )}
      </div>
    </div>
  );
}
