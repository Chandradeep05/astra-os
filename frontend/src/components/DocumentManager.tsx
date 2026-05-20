"use client";

import React, { useEffect, useState, useRef } from "react";
import { 
  FileText, 
  Upload, 
  Trash2, 
  Loader2, 
  AlertCircle, 
  Search, 
  Database,
  CheckCircle2,
  FileCode,
  FileSpreadsheet,
  XCircle,
  FileDown
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { api, Document } from "@/lib/api";

interface DocumentManagerProps {
  projectId: string;
}

interface IngestionStatus {
  fileId: string;
  filename: string;
  status: "pending" | "processing" | "done" | "error";
  stage: string;
  chunks: number;
  error?: string;
}

export const DocumentManager = ({ projectId }: DocumentManagerProps) => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  
  // File upload state
  const [isDragging, setIsDragging] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState<Record<string, IngestionStatus>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await api.listDocuments(projectId);
      setDocuments(data.documents || []);
    } catch (err: any) {
      console.error(err);
      setError("Failed to load documents for this workspace.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
    // Cleanup SSE connections on unmount or project change
    return () => {
      activeSSEs.current.forEach(es => es.close());
      activeSSEs.current.clear();
    };
  }, [projectId]);

  const activeSSEs = useRef<Map<string, EventSource>>(new Map());

  const startIngestionStream = (fileId: string, filename: string) => {
    if (activeSSEs.current.has(fileId)) return;

    const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";
    const es = new EventSource(`${API_BASE_URL}/documents/ingestion-stream/${fileId}`);
    activeSSEs.current.set(fileId, es);

    // Add to state
    setUploadingFiles(prev => ({
      ...prev,
      [fileId]: {
        fileId,
        filename,
        status: "pending",
        stage: "Initializing...",
        chunks: 0
      }
    }));

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const { status, stage, chunks, error } = data;

        setUploadingFiles(prev => ({
          ...prev,
          [fileId]: {
            fileId,
            filename,
            status,
            stage,
            chunks,
            error
          }
        }));

        if (status === "done" || status === "error") {
          es.close();
          activeSSEs.current.delete(fileId);
          // Refresh document list after indexing completes
          fetchDocuments();
          
          // Clear active upload item from list after 5s if successful
          if (status === "done") {
            setTimeout(() => {
              setUploadingFiles(prev => {
                const copy = { ...prev };
                delete copy[fileId];
                return copy;
              });
            }, 5000);
          }
        }
      } catch (err) {
        console.error("SSE parse error", err);
      }
    };

    es.onerror = () => {
      es.close();
      activeSSEs.current.delete(fileId);
      setUploadingFiles(prev => ({
        ...prev,
        [fileId]: {
          fileId,
          filename,
          status: "error",
          stage: "Ingestion Connection Error",
          chunks: 0,
          error: "Lost stream connection to server."
        }
      }));
    };
  };

  const handleFileUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      formData.append("file", file);
      formData.append("project_id", projectId);

      try {
        const response = await fetch(`${API_BASE_URL}/documents/upload`, {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          const errText = await response.text();
          throw new Error(errText || "Upload failed");
        }

        const data = await response.json();
        if (data.file_id) {
          startIngestionStream(data.file_id, file.name);
        }
      } catch (err: any) {
        console.error("Failed to upload", file.name, err);
        const tempId = `err_${Date.now()}_${i}`;
        setUploadingFiles(prev => ({
          ...prev,
          [tempId]: {
            fileId: tempId,
            filename: file.name,
            status: "error",
            stage: "Upload Failed",
            chunks: 0,
            error: err.message || "Unknown error during upload."
          }
        }));
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFileUpload(e.dataTransfer.files);
  };

  const handleToggleRag = async (fileId: string, currentVal: boolean) => {
    try {
      // Optimistic update
      setDocuments(prev => prev.map(doc => 
        doc.file_id === fileId ? { ...doc, rag_enabled: !currentVal } : doc
      ));

      await api.toggleDocument(fileId, !currentVal);
    } catch (err) {
      console.error(err);
      // Revert optimistic update
      setDocuments(prev => prev.map(doc => 
        doc.file_id === fileId ? { ...doc, rag_enabled: currentVal } : doc
      ));
    }
  };

  const handleDeleteDoc = async (fileId: string) => {
    if (!window.confirm("Are you sure you want to delete this document? This will remove all its text chunks from the vector database.")) return;

    try {
      setDocuments(prev => prev.filter(doc => doc.file_id !== fileId));
      await api.deleteDocument(fileId);
    } catch (err) {
      console.error(err);
      alert("Failed to delete document.");
      fetchDocuments();
    }
  };

  const getFileIcon = (filename: string) => {
    const ext = filename.split(".").pop()?.toLowerCase();
    if (["xlsx", "xls", "csv"].includes(ext || "")) return <FileSpreadsheet className="text-emerald-400" size={20} />;
    if (["py", "js", "ts", "json", "html", "css", "rs", "cpp", "c", "go"].includes(ext || "")) return <FileCode className="text-blue-400" size={20} />;
    return <FileText className="text-zinc-400" size={20} />;
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  const filteredDocs = documents.filter(doc => 
    doc.original_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="h-full w-full overflow-y-auto bg-[#09090b] p-8 lg:p-12 space-y-12">
      {/* Title */}
      <header className="space-y-2">
        <div className="flex items-center gap-2 text-emerald-500">
          <Database size={16} />
          <span className="text-[10px] font-black uppercase tracking-[0.3em]">Knowledge Base</span>
        </div>
        <h1 className="text-4xl font-black text-white tracking-tight italic uppercase">
          Document <span className="text-zinc-500 not-italic font-light">Manager</span>
        </h1>
        <p className="text-zinc-400 text-sm max-w-2xl">
          Upload reference text, PDFs, code files, or spreadsheets. ASTRA OS automatically parses, chunks, and indexes them into the local vector database.
        </p>
      </header>

      {/* Upload & Search Area */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
        
        {/* Upload Zone */}
        <div className="xl:col-span-2">
          <div 
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              "w-full h-48 border-2 border-dashed rounded-[2rem] flex flex-col items-center justify-center gap-4 transition-all duration-300 cursor-pointer text-center px-6 relative overflow-hidden group",
              isDragging 
                ? "border-emerald-500 bg-emerald-500/5 shadow-[0_0_30px_rgba(16,185,129,0.1)]" 
                : "border-white/10 bg-white/[0.01] hover:border-white/20 hover:bg-white/[0.02]"
            )}
          >
            <input 
              type="file" 
              ref={fileInputRef} 
              onChange={(e) => handleFileUpload(e.target.files)} 
              multiple 
              className="hidden" 
            />
            
            <div className="w-12 h-12 rounded-2xl bg-white/[0.02] border border-white/5 flex items-center justify-center group-hover:scale-110 transition-transform duration-300">
              <Upload size={24} className="text-zinc-400 group-hover:text-emerald-400 transition-colors" />
            </div>
            
            <div>
              <p className="text-sm font-semibold text-white">Drag & drop files or click to upload</p>
              <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest mt-1">PDF, DOCX, XLSX, CSV, PY, JS, TXT (MAX 10MB)</p>
            </div>
          </div>
        </div>

        {/* Search & Actions */}
        <div className="glass p-6 rounded-[2rem] border border-white/5 flex flex-col justify-center space-y-4">
          <div className="relative">
            <Search className="absolute left-4 top-3.5 text-zinc-500" size={18} />
            <input 
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search documents..."
              className="w-full bg-white/5 border border-white/5 rounded-2xl pl-12 pr-4 py-3.5 text-sm text-white placeholder:text-zinc-600 focus:ring-0 focus:border-white/10 transition-all font-medium"
            />
          </div>
          
          <div className="flex items-center justify-between text-xs text-zinc-500 px-1">
            <span>Total: {documents.length} document(s)</span>
            <span>RAG Enabled: {documents.filter(d => d.rag_enabled).length}</span>
          </div>
        </div>

      </div>

      {/* Ingestion In-Progress List */}
      {Object.keys(uploadingFiles).length > 0 && (
        <div className="space-y-4">
          <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Ingestion Pipeline</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <AnimatePresence>
              {Object.values(uploadingFiles).map((file) => (
                <motion.div 
                  key={file.fileId}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  className={cn(
                    "glass border p-5 rounded-2xl flex items-center justify-between gap-4",
                    file.status === "error" ? "border-red-500/30 bg-red-500/[0.02]" : "border-emerald-500/20 bg-emerald-500/[0.01]"
                  )}
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    {file.status === "processing" || file.status === "pending" ? (
                      <Loader2 className="animate-spin text-emerald-500 shrink-0" size={20} />
                    ) : file.status === "done" ? (
                      <CheckCircle2 className="text-emerald-500 shrink-0" size={20} />
                    ) : (
                      <AlertCircle className="text-red-500 shrink-0" size={20} />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-white truncate">{file.filename}</p>
                      <p className="text-xs text-zinc-500 capitalize">{file.stage} {file.chunks > 0 && `(${file.chunks} chunks)`}</p>
                      {file.error && (
                        <p className="text-[10px] text-red-400 mt-1 truncate">{file.error}</p>
                      )}
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Document Inventory */}
      <section className="space-y-6">
        <h2 className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Document Inventory</h2>
        
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <Loader2 className="animate-spin text-zinc-600" size={32} />
            <span className="text-sm text-zinc-500 font-medium">Scanning workspace storage...</span>
          </div>
        ) : filteredDocs.length === 0 ? (
          <div className="glass border border-white/5 rounded-[2rem] p-16 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-white/[0.02] border border-white/5 flex items-center justify-center mx-auto">
              <FileText className="text-zinc-600" size={28} />
            </div>
            <div className="space-y-1">
              <p className="text-white font-bold">No documents found</p>
              <p className="text-sm text-zinc-500">
                {searchQuery ? "No documents match your search query." : "Upload documents to feed facts into ASTRA's long term memory."}
              </p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <AnimatePresence>
              {filteredDocs.map((doc) => (
                <motion.div
                  key={doc.file_id}
                  layout
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  className={cn(
                    "glass p-6 rounded-[2rem] border border-white/5 flex flex-col justify-between gap-6 hover:border-white/10 transition-all group relative overflow-hidden",
                    !doc.rag_enabled && "opacity-60 hover:opacity-80"
                  )}
                >
                  {/* Top: Icon, title, delete */}
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-10 h-10 rounded-xl bg-white/[0.02] border border-white/5 flex items-center justify-center shrink-0">
                        {getFileIcon(doc.original_name)}
                      </div>
                      <div className="min-w-0">
                        <h4 className="text-sm font-semibold text-white truncate pr-2" title={doc.original_name}>
                          {doc.original_name}
                        </h4>
                        <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest">
                          {doc.file_type.substring(1)} • {formatSize(doc.file_size_bytes)}
                        </span>
                      </div>
                    </div>
                    
                    <button 
                      onClick={() => handleDeleteDoc(doc.file_id)}
                      className="p-2 hover:bg-red-500/10 rounded-xl text-zinc-500 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 duration-200"
                      title="Delete document"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>

                  {/* Middle: Details */}
                  <div className="grid grid-cols-2 gap-4 bg-white/[0.01] border border-white/5 rounded-2xl p-4 text-xs">
                    <div>
                      <span className="text-zinc-500 block mb-1">Vector Chunks</span>
                      <span className="text-white font-bold flex items-center gap-1.5">
                        <Database size={12} className="text-emerald-500" />
                        {doc.chunk_count} chunks
                      </span>
                    </div>
                    <div>
                      <span className="text-zinc-500 block mb-1">Uploaded</span>
                      <span className="text-zinc-300 font-medium block truncate">
                        {new Date(doc.uploaded_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>

                  {/* Bottom: RAG retrieval Toggle */}
                  <div className="flex items-center justify-between pt-2 border-t border-white/5">
                    <span className="text-xs font-semibold text-zinc-400">RAG Retrieval</span>
                    <button
                      onClick={() => handleToggleRag(doc.file_id, doc.rag_enabled)}
                      className={cn(
                        "w-10 h-6 rounded-full p-1 transition-all duration-300 flex items-center cursor-pointer",
                        doc.rag_enabled ? "bg-emerald-500 justify-end" : "bg-zinc-800 justify-start"
                      )}
                    >
                      <motion.div 
                        layout 
                        className="w-4 h-4 rounded-full bg-white shadow-md"
                        transition={{ type: "spring", stiffness: 500, damping: 30 }}
                      />
                    </button>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </section>
    </div>
  );
};
