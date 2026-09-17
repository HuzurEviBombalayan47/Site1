import { useState, useCallback } from "react";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import UploadScreen from "@/components/UploadScreen";
import AnalyzingScreen from "@/components/AnalyzingScreen";
import Editor from "@/components/Editor";

export default function App() {
  const [view, setView] = useState("upload"); // upload | analyzing | editor
  const [jobId, setJobId] = useState(null);

  const handleCreated = useCallback((id) => {
    setJobId(id);
    setView("analyzing");
  }, []);

  const handleReady = useCallback(() => setView("editor"), []);

  const handleReset = useCallback(() => {
    setJobId(null);
    setView("upload");
  }, []);

  return (
    <div className="studio-root grain" data-testid="studio-root">
      {view === "upload" && <UploadScreen onCreated={handleCreated} />}
      {view === "analyzing" && (
        <AnalyzingScreen jobId={jobId} onReady={handleReady} onReset={handleReset} />
      )}
      {view === "editor" && <Editor jobId={jobId} onReset={handleReset} />}
      <Toaster
        theme="dark"
        position="top-center"
        toastOptions={{ style: { background: "#111", border: "1px solid #2a2a2e", color: "#fff" } }}
      />
    </div>
  );
}
