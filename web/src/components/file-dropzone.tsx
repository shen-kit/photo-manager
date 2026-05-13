"use client";

import { UploadCloud } from "lucide-react";
import { useRef, useState } from "react";

type FileDropzoneProps = {
  disabled?: boolean;
  onSelect: (files: File[]) => void;
};

export function FileDropzone({ disabled, onSelect }: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isOver, setIsOver] = useState(false);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(event) => {
        if ((event.key === "Enter" || event.key === " ") && !disabled) {
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) {
          setIsOver(true);
        }
      }}
      onDragLeave={() => setIsOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setIsOver(false);
        if (disabled) {
          return;
        }
        const files = Array.from(event.dataTransfer.files);
        if (files.length > 0) {
          onSelect(files);
        }
      }}
      className={`rounded-3xl border border-dashed p-5 transition ${
        isOver
          ? "border-cyan-400 bg-cyan-500/10"
          : "border-white/15 bg-white/[0.03] hover:border-white/30 hover:bg-white/[0.05]"
      } ${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          if (files.length > 0) {
            onSelect(files);
          }
          event.currentTarget.value = "";
        }}
      />
      <div className="flex items-center gap-4">
        <div className="rounded-2xl border border-cyan-400/30 bg-cyan-400/10 p-3 text-cyan-300">
          <UploadCloud className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white">Drop files for direct upload</p>
          <p className="text-xs text-slate-400">Streams multipart uploads through `/api/v1/assets/upload`</p>
        </div>
      </div>
    </div>
  );
}
