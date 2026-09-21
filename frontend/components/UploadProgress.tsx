"use client";

import { type UploadProgress as Progress, formatBytes, formatDuration } from "@/lib/upload";

type Stage = "uploading" | "finishing" | "done";

/** Progress card shown while a video uploads: bar, numbers and stage. */
export function UploadProgressCard({
  fileName,
  progress,
  stage,
  onCancel,
}: {
  fileName: string;
  progress: Progress | null;
  stage: Stage;
  onCancel?: () => void;
}) {
  const percent = stage === "uploading" ? (progress?.percent ?? 0) : 100;
  const speed = progress?.bytesPerSecond ?? 0;

  const label =
    stage === "done"
      ? "Published — opening your video…"
      : stage === "finishing"
        ? "Finishing up…"
        : percent === 0
          ? "Starting upload…"
          : `Uploading… ${percent}%`;

  return (
    <section
      aria-live="polite"
      className="mt-4 rounded-xl border border-line bg-surface/60 p-4"
    >
      <div className="flex items-center gap-3">
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-brand/10 text-brand ${
            stage === "done" ? "" : "upload-pulse"
          }`}
        >
          <span className={stage === "done" ? "" : "upload-arrow"}>{stage === "done" ? "✓" : "↑"}</span>
        </span>

        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{fileName}</p>
          <p className="text-xs text-muted">
            {label}
            {stage === "uploading" && progress && (
              <>
                {" · "}
                {formatBytes(progress.uploadedBytes)} of {formatBytes(progress.totalBytes)}
                {speed > 0 && ` · ${formatBytes(speed)}/s`}
                {progress.secondsRemaining !== null && ` · ${formatDuration(progress.secondsRemaining)}`}
              </>
            )}
          </p>
        </div>

        {stage === "uploading" && onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-full px-3 py-1 text-xs font-medium text-muted hover:bg-surface-hover"
          >
            Cancel
          </button>
        )}
      </div>

      <div
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        className="mt-3 h-2 w-full overflow-hidden rounded-full bg-surface-hover"
      >
        <div
          className={`relative h-full rounded-full bg-brand transition-[width] duration-300 ease-out ${
            stage === "done" ? "" : "upload-sheen"
          }`}
          style={{ width: `${Math.max(percent, 2)}%` }}
        />
      </div>

      <p className="mt-2 text-xs text-muted">
        {stage === "uploading"
          ? "Uploading straight to storage — you can keep editing the details below."
          : stage === "finishing"
            ? "Storing the file and publishing…"
            : "Done."}
      </p>
    </section>
  );
}
