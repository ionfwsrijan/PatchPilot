import { useState, useCallback } from "react";

export function useDragAndDrop(onDropFile: (file: File) => void, disabled: boolean) {
  const [dragActive, setDragActive] = useState(false);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;

    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, [disabled]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;

    setDragActive(false);

    const file = e.dataTransfer.files?.[0];
    if (!file) return;

    onDropFile(file);
  }, [disabled, onDropFile]);

  return {
    dragActive,
    handleDrag,
    handleDrop
  };
}