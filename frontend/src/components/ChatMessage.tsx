import type { ChatMessage as ChatMessageType } from '@/types/rag';
import { cn } from '@/lib/utils';
import { User, Bot, FilePlus, Edit, RefreshCw } from 'lucide-react';
import { SourceList } from './SourceList';
import { Button } from './ui/button';
import { useState } from 'react';

interface ChatMessageProps {
  message: ChatMessageType;
  onSourceClick: (path: string) => void;
  onRefreshNeeded?: () => void;
}

export function ChatMessage({ message, onSourceClick, onRefreshNeeded }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const [isRefreshing, setIsRefreshing] = useState(false);

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

  return (
    <div className={cn("flex gap-3 p-4", isUser ? "bg-transparent" : "bg-muted/30")}>
      <div className={cn(
        "h-8 w-8 rounded-full flex items-center justify-center flex-shrink-0",
        isUser ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground"
      )}>
        {isUser ? <User className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
      </div>

      <div className="flex-1 space-y-2 overflow-hidden">
        <div className="prose dark:prose-invert text-sm max-w-none whitespace-pre-wrap">
          {message.content}
        </div>

        {!isUser && message.notes_written && message.notes_written.length > 0 && (
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

        {!isUser && message.sources && (
          <SourceList sources={message.sources} onSourceClick={onSourceClick} />
        )}
      </div>
    </div>
  );
}
