export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Defer revocation to give the browser time to initiate the download
  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 100);
}

