import type { ChatMessage as ChatMessageType } from '@/types/rag';
import { cn } from '@/lib/utils';
import { User, Bot, FilePlus, Edit } from 'lucide-react';
import { SourceList } from './SourceList';

interface ChatMessageProps {
  message: ChatMessageType;
  onSourceClick: (path: string) => void;
}

export function ChatMessage({ message, onSourceClick }: ChatMessageProps) {
  const isUser = message.role === 'user';

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
          <div className="flex flex-wrap gap-2 mt-2">
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
        )}

        {!isUser && message.sources && (
          <SourceList sources={message.sources} onSourceClick={onSourceClick} />
        )}
      </div>
    </div>
  );
}
