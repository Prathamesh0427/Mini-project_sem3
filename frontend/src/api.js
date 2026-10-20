async function request(url, options) {
  let res;
  try {
    res = await fetch(url, options);
  } catch {
    throw new Error("Cannot reach the backend. Is it running on port 8000?");
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail?.message) message = body.detail.message;
      else if (typeof body.detail === "string") message = body.detail;
    } catch { /* keep default message */ }
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const api = {
  config: () => request("/api/config"),
  stats: () => request("/api/stats"),
  list: (params) => request("/api/analyses?" + new URLSearchParams(params)),
  get: (id) => request(`/api/analyses/${id}`),
  remove: (id) => request(`/api/analyses/${id}`, { method: "DELETE" }),
};

/** Upload with real byte-level progress (fetch cannot report upload progress). */
export function uploadVideo(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/analyses");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onerror = () => reject(new Error("Cannot reach the backend. Is it running on port 8000?"));
    xhr.onload = () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body.detail?.message || `Upload failed (${xhr.status})`));
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
