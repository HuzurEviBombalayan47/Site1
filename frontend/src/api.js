import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API });

export const api = {
  getConfig: () => client.get("/config").then((r) => r.data),
  getSfx: () => client.get("/sfx").then((r) => r.data.sfx),
  createJob: (formData, onUploadProgress) =>
    client
      .post("/jobs", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress,
      })
      .then((r) => r.data),
  getJob: (id) => client.get(`/jobs/${id}`).then((r) => r.data),
  renderJob: (id) => client.post(`/jobs/${id}/render`).then((r) => r.data),
  regenerate: (id, body) =>
    client.post(`/jobs/${id}/regenerate`, body).then((r) => r.data),
  patchJob: (id, body) => client.patch(`/jobs/${id}`, body).then((r) => r.data),
  searchMedia: (kind, q) =>
    client.get(`/search`, { params: { kind, q } }).then((r) => r.data.results),
  audioUrl: (id) => `${API}/jobs/${id}/audio`,
  downloadUrl: (id) => `${API}/jobs/${id}/download`,
  sfxUrl: (name) => `${API}/sfx/${name}`,
};

export default api;
