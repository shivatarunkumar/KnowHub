/**
 * Resumable upload straight from the browser to Google Cloud Storage.
 *
 * The API hands us a session URL, then we PUT the file in chunks. Bytes never pass
 * through Next.js or the API, so there's no 10 MB proxy limit and no server memory
 * pressure, and a failed chunk is retried from where it stopped rather than restarting
 * the whole file.
 */

export type UploadMetadata = {
  title: string;
  description: string;
  type: string;
  category: string;
  topic_slug: string;
  team_slug: string;
  visibility: string;
  duration_sec?: number | null;
  width?: number | null;
  height?: number | null;
  links?: { kind: string; url: string; label: string | null }[];
  snippets?: { title: string | null; language: string; code: string }[];
};

export type UploadProgress = {
  uploadedBytes: number;
  totalBytes: number;
  percent: number;
  bytesPerSecond: number;
  secondsRemaining: number | null;
};

export class UploadError extends Error {}

const MAX_CHUNK_RETRIES = 4;

async function readApiError(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  const detail = body?.detail;
  if (Array.isArray(detail)) return detail[0]?.msg ?? fallback;
  return detail?.message ?? fallback;
}

/** PUT one chunk. Returns how many bytes GCS has confirmed so far. */
async function putChunk(
  uploadUrl: string,
  file: File,
  start: number,
  end: number,
  contentType: string,
): Promise<{ confirmed: number; done: boolean }> {
  const res = await fetch(uploadUrl, {
    method: "PUT",
    headers: {
      "Content-Type": contentType,
      "Content-Range": `bytes ${start}-${end - 1}/${file.size}`,
    },
    body: file.slice(start, end),
  });

  if (res.status === 200 || res.status === 201) return { confirmed: file.size, done: true };

  // 308 = "keep going"; the Range header says what GCS actually stored
  if (res.status === 308) {
    const range = res.headers.get("Range");
    const confirmed = range ? Number(range.split("-")[1]) + 1 : end;
    return { confirmed, done: false };
  }

  throw new UploadError(`Storage rejected the upload (HTTP ${res.status}).`);
}

export async function uploadVideo({
  file,
  metadata,
  onProgress,
  signal,
}: {
  file: File;
  metadata: UploadMetadata;
  onProgress: (progress: UploadProgress) => void;
  signal?: AbortSignal;
}): Promise<{ id: string }> {
  // 1. ask the API for an upload session (this also creates the video record)
  const startRes = await fetch("/api/v1/videos/uploads/start", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      filename: file.name,
      content_type: file.type || "video/mp4",
      size: file.size,
      ...metadata,
    }),
  });
  if (!startRes.ok) {
    throw new UploadError(await readApiError(startRes, "Could not start the upload."));
  }
  const { video_id: videoId, upload_url: uploadUrl, chunk_size: chunkSize } = await startRes.json();

  // 2. send the file in chunks
  const startedAt = Date.now();
  let uploaded = 0;
  let failures = 0;

  while (uploaded < file.size) {
    if (signal?.aborted) throw new UploadError("Upload cancelled.");
    const end = Math.min(uploaded + chunkSize, file.size);
    try {
      const { confirmed, done } = await putChunk(uploadUrl, file, uploaded, end, file.type || "video/mp4");
      uploaded = Math.max(confirmed, uploaded);
      failures = 0;
      const seconds = (Date.now() - startedAt) / 1000;
      const bytesPerSecond = seconds > 0 ? uploaded / seconds : 0;
      onProgress({
        uploadedBytes: uploaded,
        totalBytes: file.size,
        percent: Math.min(100, Math.round((uploaded / file.size) * 100)),
        bytesPerSecond,
        secondsRemaining: bytesPerSecond > 0 ? (file.size - uploaded) / bytesPerSecond : null,
      });
      if (done) break;
    } catch (error) {
      failures += 1;
      if (failures >= MAX_CHUNK_RETRIES) {
        throw error instanceof UploadError
          ? error
          : new UploadError("Connection lost during upload. Please try again.");
      }
      await new Promise((resolve) => setTimeout(resolve, 2 ** failures * 500)); // back off, then retry
    }
  }

  // 3. tell the API the file is there, which publishes the video
  const completeRes = await fetch(`/api/v1/videos/${videoId}/complete`, { method: "POST" });
  if (!completeRes.ok) {
    throw new UploadError(await readApiError(completeRes, "The upload didn't finish."));
  }
  return { id: videoId };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "";
  if (seconds < 60) return `${Math.ceil(seconds)}s left`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${Math.round(seconds % 60)}s left`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m left`;
}
