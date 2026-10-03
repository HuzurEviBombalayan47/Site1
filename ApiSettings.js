import { useState } from "react";

export default function ApiSettings() {
  const [apis, setApis] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("site1_apis") || "[]");
    } catch {
      return [];
    }
  });

  const [name, setName] = useState("");
  const [key, setKey] = useState("");

  const saveApis = (next) => {
    setApis(next);
    localStorage.setItem("site1_apis", JSON.stringify(next));
  };

  const addApi = () => {
    const trimmedName = name.trim();
    const trimmedKey = key.trim();

    if (!trimmedName || !trimmedKey) {
      alert("API adı ve API anahtarı gerekli.");
      return;
    }

    const newApi = {
      id: crypto.randomUUID(),
      name: trimmedName,
      key: trimmedKey,
      createdAt: new Date().toISOString(),
    };

    saveApis([...apis, newApi]);

    setName("");
    setKey("");
  };

  const removeApi = (id) => {
    const next = apis.filter((api) => api.id !== id);
    saveApis(next);
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#0b0b0d",
        color: "#fff",
        padding: "40px 20px",
        fontFamily: "Arial, sans-serif",
      }}
    >
      <div
        style={{
          maxWidth: "700px",
          margin: "0 auto",
        }}
      >
        <h1 style={{ marginBottom: "8px" }}>
          API Ayarları
        </h1>

        <p
          style={{
            color: "#999",
            marginBottom: "30px",
          }}
        >
          API anahtarlarını buradan ekleyebilir veya silebilirsin.
        </p>

        <div
          style={{
            background: "#151519",
            border: "1px solid #29292f",
            borderRadius: "14px",
            padding: "20px",
            marginBottom: "25px",
          }}
        >
          <h2 style={{ marginTop: 0 }}>
            Yeni API Ekle
          </h2>

          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="API adı (ör. OpenAI)"
            style={inputStyle}
          />

          <input
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="API anahtarı"
            type="password"
            style={inputStyle}
          />

          <button
            onClick={addApi}
            style={buttonStyle}
          >
            + API Ekle
          </button>
        </div>

        <div>
          <h2>
            Eklenen API'ler ({apis.length})
          </h2>

          {apis.length === 0 ? (
            <div
              style={{
                color: "#777",
                padding: "20px 0",
              }}
            >
              Henüz API eklenmedi.
            </div>
          ) : (
            apis.map((api) => (
              <div
                key={api.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "15px",
                  background: "#151519",
                  border: "1px solid #29292f",
                  borderRadius: "12px",
                  padding: "16px",
                  marginTop: "12px",
                }}
              >
                <div>
                  <div
                    style={{
                      fontWeight: "bold",
                      fontSize: "16px",
                    }}
                  >
                    {api.name}
                  </div>

                  <div
                    style={{
                      color: "#777",
                      marginTop: "5px",
                      fontFamily: "monospace",
                    }}
                  >
                    ••••••••••••••••
                  </div>
                </div>

                <button
                  onClick={() => removeApi(api.id)}
                  style={deleteButtonStyle}
                >
                  Sil
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

const inputStyle = {
  width: "100%",
  boxSizing: "border-box",
  padding: "13px",
  marginBottom: "12px",
  borderRadius: "9px",
  border: "1px solid #333",
  background: "#0d0d10",
  color: "#fff",
  outline: "none",
};

const buttonStyle = {
  width: "100%",
  padding: "13px",
  borderRadius: "9px",
  border: "none",
  background: "#aaff00",
  color: "#000",
  fontWeight: "bold",
  cursor: "pointer",
};

const deleteButtonStyle = {
  padding: "9px 14px",
  borderRadius: "8px",
  border: "1px solid #552222",
  background: "#251313",
  color: "#ff7777",
  cursor: "pointer",
};
