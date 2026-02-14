"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/dashboard/app-sidebar";
import { SiteHeader } from "@/components/dashboard/site-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  IconFileTypePdf, IconFileTypeDocx, IconFileText, IconRefresh,
  IconCheck, IconX, IconLoader2, IconCloudUpload,
} from "@tabler/icons-react";

interface DocumentEntry {
  id?: string; doc_id: string; filename: string; content_type: string;
  page_count: number; word_count: number; text_length: number;
  status: string; item_id?: string; error?: string; created_at: string;
}

function FileIcon({ filename }: { filename: string }) {
  const ext = filename.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <IconFileTypePdf className="size-8 text-red-500" />;
  if (ext === "docx" || ext === "doc") return <IconFileTypeDocx className="size-8 text-blue-500" />;
  return <IconFileText className="size-8 text-gray-500" />;
}

function StatusBadge({ status }: { status: string }) {
  if (status === "ingested")
    return <Badge variant="default" className="gap-1"><IconCheck className="size-3" />Ingested</Badge>;
  if (status === "processing")
    return <Badge variant="secondary" className="gap-1"><IconLoader2 className="size-3 animate-spin" />Processing</Badge>;
  if (status === "failed")
    return <Badge variant="destructive" className="gap-1"><IconX className="size-3" />Failed</Badge>;
  return <Badge variant="outline">{status}</Badge>;
}

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/documents");
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.data || []);
        setTotal(data.total || 0);
      }
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { fetchDocuments(); }, [fetchDocuments]);
  useEffect(() => {
    const interval = setInterval(fetchDocuments, 8000);
    return () => clearInterval(interval);
  }, [fetchDocuments]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setUploadError(null);
    setUploadSuccess(null);
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!["pdf", "docx", "doc", "txt"].includes(ext || "")) {
      setUploadError("Unsupported file type. Please upload PDF, DOCX, or TXT files.");
      setUploading(false);
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError("File too large. Maximum size is 10 MB.");
      setUploading(false);
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/documents", { method: "POST", body: formData });
      const data = await res.json();
      if (res.ok) {
        setUploadSuccess(`"${data.filename}" ingested: ${data.word_count} words, ${data.page_count} pages`);
        fetchDocuments();
      } else {
        setUploadError(data.detail || data.error || "Upload failed");
      }
    } catch {
      setUploadError("Network error during upload");
    }
    setUploading(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <SidebarProvider
      style={{ "--sidebar-width": "calc(var(--spacing) * 72)", "--header-height": "calc(var(--spacing) * 12)" } as React.CSSProperties}
    >
      <AppSidebar variant="inset" />
      <SidebarInset>
        <SiteHeader />
        <div className="flex flex-1 flex-col">
          <div className="flex flex-col gap-4 p-4 lg:p-6">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold tracking-tight">Document Ingestion</h1>
                <p className="text-muted-foreground text-sm">
                  Upload PDF, Word, or text documents to ingest into the KOS knowledge pipeline
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={fetchDocuments} disabled={loading} className="gap-1.5">
                <IconRefresh className={`size-4 ${loading ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </div>

            {/* Upload Zone */}
            <Card>
              <CardContent className="p-0">
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleDrop}
                  onClick={() => inputRef.current?.click()}
                  className={`flex flex-col items-center justify-center gap-3 py-12 px-6 cursor-pointer rounded-lg border-2 border-dashed transition-colors ${
                    dragOver ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-muted-foreground/50"
                  } ${uploading ? "pointer-events-none opacity-60" : ""}`}
                >
                  <input
                    ref={inputRef}
                    type="file"
                    accept=".pdf,.docx,.doc,.txt"
                    onChange={handleFileInput}
                    className="hidden"
                  />
                  {uploading ? (
                    <IconLoader2 className="size-10 text-primary animate-spin" />
                  ) : (
                    <IconCloudUpload className="size-10 text-muted-foreground" />
                  )}
                  <div className="text-center">
                    <p className="text-sm font-medium">
                      {uploading ? "Uploading and ingesting..." : "Drop a file here or click to browse"}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Supports PDF, DOCX, and TXT files up to 10 MB
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Upload feedback */}
            {uploadError && (
              <div className="flex items-center gap-2 rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
                <IconX className="size-4 shrink-0" />
                {uploadError}
              </div>
            )}
            {uploadSuccess && (
              <div className="flex items-center gap-2 rounded-md bg-green-500/10 border border-green-500/20 px-4 py-3 text-sm text-green-700 dark:text-green-400">
                <IconCheck className="size-4 shrink-0" />
                {uploadSuccess}
              </div>
            )}

            {/* Documents List */}
            <Card>
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-sm font-medium">
                  Uploaded Documents
                  <span className="text-muted-foreground font-normal ml-2">({total})</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {documents.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                    <IconCloudUpload className="size-12 mb-3 opacity-20" />
                    <p className="text-sm font-medium">No documents uploaded yet</p>
                    <p className="text-xs mt-1">Upload a document above to start ingesting</p>
                  </div>
                ) : (
                  <div className="divide-y">
                    {documents.map((doc) => (
                      <div key={doc.doc_id} className="flex items-center gap-4 px-4 py-3 hover:bg-muted/50 transition-colors">
                        <FileIcon filename={doc.filename} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium truncate">{doc.filename}</p>
                            <StatusBadge status={doc.status} />
                          </div>
                          <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
                            <span>{doc.word_count.toLocaleString()} words</span>
                            <span>{doc.page_count} {doc.page_count === 1 ? "page" : "pages"}</span>
                            {doc.item_id && (
                              <span className="font-mono text-[10px]">item:{doc.item_id.slice(0, 8)}</span>
                            )}
                          </div>
                          {doc.error && (
                            <p className="text-xs text-destructive mt-1 truncate">{doc.error}</p>
                          )}
                        </div>
                        <span className="text-[10px] text-muted-foreground whitespace-nowrap tabular-nums">
                          {formatTime(doc.created_at)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
