import React, { useEffect, useState, Component, type ErrorInfo } from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
// import { NoteViewer } from '@/components/NoteViewer';
// import { SearchWidget } from '@/components/SearchWidget';
// import type { Note } from '@/types/note';
// import type { SearchResult } from '@/types/search';
import { Loader2, AlertTriangle } from 'lucide-react';

// Mock window.openai for development
if (!window.openai) {
  window.openai = {
    toolOutput: null
  };
}

// Extend window interface
declare global {
  interface Window {
    openai: {
      toolOutput: any;
    };
  }
}

class WidgetErrorBoundary extends Component<{ children: React.ReactNode }, { hasError: boolean, error: Error | null }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Widget Error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-background text-destructive p-4 flex flex-col items-center justify-center text-center">
          <AlertTriangle className="h-8 w-8 mb-2" />
          <h2 className="font-bold text-lg">Something went wrong</h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-xs">
            {this.state.error?.message || "The widget could not be displayed."}
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}

const WidgetApp = () => {
  const [debugInfo, setDebugInfo] = useState<string>("Initializing...");

  useEffect(() => {
    console.log("Widget mounted");
    const toolOutput = window.openai?.toolOutput;
    setDebugInfo(`Tool Output: ${JSON.stringify(toolOutput, null, 2)}`);
  }, []);

  return (
    <div className="dark min-h-screen bg-background text-foreground flex flex-col p-4">
        <h1 className="text-2xl font-bold text-green-500">Widget Hello World</h1>
        <pre className="bg-muted p-4 rounded mt-4 overflow-auto text-xs font-mono">
            {debugInfo}
        </pre>
    </div>
  );
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <WidgetErrorBoundary>
      <WidgetApp />
    </WidgetErrorBoundary>
  </React.StrictMode>
);
