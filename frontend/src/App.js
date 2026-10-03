import { useState, useCallback } from "react";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import UploadScreen from "@/components/UploadScreen";
import AnalyzingScreen from "@/components/AnalyzingScreen";
import Editor from "@/components/Editor";
import ApiSettings from "./ApiSettings";

export default function App() {
  const [showApiSettings, setShowApiSettings] = useState(false);
  const [view, setView] = useState("upload");
  const [jobId, setJobId] = useState(null);

  const handleCreated = useCallback((id) => {
    setJobId(id);
    setView("analyzing");
  }, []);

  const handleReady = useCallback(() => {
    setView("editor");
  }, []);

  const handleReset = useCallback(() => {
    setJobId(null);
    setView("upload");
  }, []);

  // API AYARLARI EKRANI
  if (showApiSettings) {
    return (
      <div className="studio-root grain">
        <button
          onClick={() => setShowApiSettings(false)}
          style={{
            position: "fixed",
            top: "15px",
            left: "15px",
            zIndex: 99999,
            padding: "10px 15px",
            borderRadius: "8px",
            border: "1px solid #333",
            background: "#151519",
            color: "#fff",
            cursor: "pointer",
            fontSize: "14px",
          }}
        >
          ← Geri
        </button>

        <ApiSettings />

        <Toaster
          theme="dark"
          position="top-center"
          toastOptions={{
            style: {
              background: "#111",
              border: "1px solid #2a2a2e",
              color: "#fff",
            },
          }}
        />
      </div>
    );
  }

  // NORMAL UYGULAMA
  return (
    <div
      className="studio-root grain"
      data-testid="studio-root"
    >
      {view === "upload" && (
        <>
          <button
            onClick={() => setShowApiSettings(true)}
            style={{
              position: "fixed",
              top: "15px",
              right: "15px",
              zIndex: 99999,
              padding: "10px 15px",
              borderRadius: "8px",
              border: "1px solid #333",
              background: "#151519",
              color: "#fff",
              cursor: "pointer",
              fontSize: "14px",
            }}
          >
            ⚙️ API Ayarları
          </button>

          <UploadScreen onCreated={handleCreated} />
        </>
      )}

      {view === "analyzing" && (
        <AnalyzingScreen
          jobId={jobId}
          onReady={handleReady}
          onReset={handleReset}
        />
      )}

      {view === "editor" && (
        <Editor
          jobId={jobId}
          onReset={handleReset}
        />
      )}

      <Toaster
        theme="dark"
        position="top-center"
        toastOptions={{
          style: {
            background: "#111",
            border: "1px solid #2a2a2e",
            color: "#fff",
          },
        }}
      />
    </div>
  );
              }
