/**
 * Poster frames are captured in the browser: the file is already here, so there's no
 * need for the server to download and decode it. We draw a frame onto a canvas and
 * send the JPEG alongside the upload.
 */

export type VideoProbe = {
  durationSec: number;
  width: number;
  height: number;
};

const THUMBNAIL_MAX_WIDTH = 1280;
const JPEG_QUALITY = 0.82;

function loadVideo(file: File): Promise<HTMLVideoElement> {
  return new Promise((resolve, reject) => {
    const video = document.createElement("video");
    video.preload = "metadata";
    video.muted = true;
    video.playsInline = true;
    video.src = URL.createObjectURL(file);
    video.onloadedmetadata = () => resolve(video);
    video.onerror = () => reject(new Error("Couldn't read that video file"));
  });
}

export async function probeVideo(file: File): Promise<VideoProbe> {
  const video = await loadVideo(file);
  const probe = {
    durationSec: Number.isFinite(video.duration) ? Math.round(video.duration) : 0,
    width: video.videoWidth,
    height: video.videoHeight,
  };
  URL.revokeObjectURL(video.src);
  return probe;
}

/** Grab the frame at `atSeconds` as a JPEG, scaled down to at most 1280px wide. */
export async function captureFrame(file: File, atSeconds: number): Promise<Blob | null> {
  const video = await loadVideo(file);
  try {
    await new Promise<void>((resolve, reject) => {
      video.onseeked = () => resolve();
      video.onerror = () => reject(new Error("seek failed"));
      // a hair inside the duration: seeking to the very end often yields a blank frame
      video.currentTime = Math.min(Math.max(atSeconds, 0), Math.max(0, (video.duration || 1) - 0.1));
    });

    const scale = Math.min(1, THUMBNAIL_MAX_WIDTH / (video.videoWidth || THUMBNAIL_MAX_WIDTH));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round((video.videoWidth || 1280) * scale);
    canvas.height = Math.round((video.videoHeight || 720) * scale);
    const context = canvas.getContext("2d");
    if (!context) return null;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    return await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
  } catch {
    return null; // a codec the browser can't decode: the UI falls back to a drawn cover
  } finally {
    URL.revokeObjectURL(video.src);
  }
}

export async function uploadThumbnail(videoId: string, blob: Blob): Promise<void> {
  const form = new FormData();
  form.set("file", blob, "thumbnail.jpg");
  await fetch(`/api/v1/videos/${videoId}/thumbnail`, { method: "POST", body: form });
}

export function formatDurationBadge(seconds: number | null): string {
  if (!seconds || seconds <= 0) return "";
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  if (minutes < 60) return `${minutes}:${String(rest).padStart(2, "0")}`;
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}
